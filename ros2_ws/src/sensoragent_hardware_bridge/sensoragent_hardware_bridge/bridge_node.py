#!/usr/bin/env python3
"""Expose configured physical ROS services through SensorAgent's HTTP protocol."""

from __future__ import annotations

import json
import math
import threading
import time
from math import degrees
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import rclpy
from arm_control_interfaces.srv import GetCurrentPose, MoveJDeg, MoveL, MoveToPose
from geometry_msgs.msg import Pose
from op_control_interfaces.msg import OmniPickerState
from op_control_interfaces.srv import Close, Open, SetPosition
from rclpy.node import Node
from std_msgs.msg import Empty


def _response(success: bool, error_code: str = "OK", message: str = "OK", state: dict | None = None) -> dict:
  return {"success": success, "error_code": error_code, "message": message, "state": state or {}}


_FAULT_LABELS = {
  0: "no_fault",
  1: "over_temperature",
  2: "over_speed",
  3: "initialization_fault",
  4: "over_limit",
}

_STATUS_LABELS = {
  0: "target_reached",
  1: "moving",
  2: "stalled",
  3: "object_dropped",
}


class HardwareBridge(Node):
  """HTTP bridge with a deliberate opt-in gate for all physical motion."""

  def __init__(self) -> None:
    super().__init__("sensoragent_hardware_bridge")
    for name, default in (
        ("bind_host", "127.0.0.1"), ("bind_port", 8766), ("allow_motion", False),
        ("base_frame", "base_link"), ("tool_frame", "Link6"),
        ("arm_service_prefix", "/task/arm"), ("gripper_service_prefix", "/task/op"),
        ("gripper_state_topic", "/omnipicker_state"), ("max_speed", 4),
        ("max_gripper_opening_m", 0.120),
        ("max_gripper_open_command", 254.0 / 255.0),
        ("workspace_min", [-0.55, -0.18, 0.0]), ("workspace_max", [-0.20, 0.18, 0.35]),
        ("approach_position_tolerance_m", 0.002), ("approach_orientation_tolerance", 0.01),
        ("motion_completion_timeout_sec", 90.0), ("motion_poll_interval_sec", 0.2),
    ):
      self.declare_parameter(name, default)
    # A NaN placeholder fixes the ROS parameter type while remaining unusable
    # until an exact three/four-value approval is explicitly registered.
    self.declare_parameter("approved_approach_position", [math.nan])
    self.declare_parameter("approved_approach_orientation", [math.nan])
    self._base_frame = str(self.get_parameter("base_frame").value)
    self._max_speed = int(self.get_parameter("max_speed").value)
    self._lower = [float(item) for item in self.get_parameter("workspace_min").value]
    self._upper = [float(item) for item in self.get_parameter("workspace_max").value]
    self._approach_position_tolerance = float(self.get_parameter("approach_position_tolerance_m").value)
    self._approach_orientation_tolerance = float(self.get_parameter("approach_orientation_tolerance").value)
    self._motion_completion_timeout = float(self.get_parameter("motion_completion_timeout_sec").value)
    self._motion_poll_interval = float(self.get_parameter("motion_poll_interval_sec").value)
    arm_prefix = str(self.get_parameter("arm_service_prefix").value).rstrip("/")
    gripper_prefix = str(self.get_parameter("gripper_service_prefix").value).rstrip("/")
    self._move_joints = self.create_client(MoveJDeg, f"{arm_prefix}/movej_deg")
    self._move_pose = self.create_client(MoveToPose, f"{arm_prefix}/move_to_pose")
    self._move_linear = self.create_client(MoveL, f"{arm_prefix}/movel")
    self._current_pose = self.create_client(GetCurrentPose, f"{arm_prefix}/get_current_pose")
    self._open = self.create_client(Open, f"{gripper_prefix}/open")
    self._close = self.create_client(Close, f"{gripper_prefix}/close")
    self._set_position = self.create_client(SetPosition, f"{gripper_prefix}/set_position")
    self._stop = self.create_publisher(Empty, "/rm_driver/move_stop_cmd", 1)
    self._max_gripper_opening = float(self.get_parameter("max_gripper_opening_m").value)
    self._max_gripper_open_command = min(1.0, max(0.0, float(self.get_parameter("max_gripper_open_command").value)))
    self._gripper_state: dict[str, Any] = {"status": "unknown"}
    self.create_subscription(OmniPickerState, str(self.get_parameter("gripper_state_topic").value), self._on_gripper_state, 10)
    self._server: ThreadingHTTPServer | None = None

  def _on_gripper_state(self, message: OmniPickerState) -> None:
    position = float(message.pos)
    raw_frame = list(getattr(message, "raw_frame", []))
    fault_code = int(raw_frame[3]) if len(raw_frame) > 3 else 0
    status = int(message.status)
    # A stalled finger pair near its open limit is a controller fault, not a grasp.
    self._gripper_state = {
      "opening": position * self._max_gripper_opening,
      "force": float(message.force),
      "status": status,
      "status_label": _STATUS_LABELS.get(status, "unknown"),
      "fault_code": fault_code,
      "fault_label": _FAULT_LABELS.get(fault_code, "unknown"),
      "grasped": status == 2 and position < (220.0 / 255.0),
    }
    if raw_frame:
      self._gripper_state["raw_frame_hex"] = " ".join(f"{value:02X}" for value in raw_frame)

  def ready(self) -> dict:
    return {"allow_motion": bool(self.get_parameter("allow_motion").value), "movej": self._move_joints.service_is_ready(), "move_to_pose": self._move_pose.service_is_ready(), "movel": self._move_linear.service_is_ready(), "get_current_pose": self._current_pose.service_is_ready(), "gripper_open": self._open.service_is_ready(), "gripper_close": self._close.service_is_ready(), "gripper_position": self._set_position.service_is_ready()}

  def _motion_allowed(self) -> dict | None:
    if not bool(self.get_parameter("allow_motion").value):
      return _response(False, "MOTION_DISABLED", "Physical motion is disabled; set allow_motion:=true only after dry-run approval.")
    return None

  def _pose(self, payload: dict) -> Pose:
    value = payload.get("pose")
    if not isinstance(value, dict) or value.get("frame_id", self._base_frame) != self._base_frame:
      raise ValueError(f"pose must be in {self._base_frame}")
    position, orientation = value.get("position"), value.get("orientation")
    if not isinstance(position, list) or len(position) != 3 or not isinstance(orientation, list) or len(orientation) != 4:
      raise ValueError("pose requires position[3] and orientation[4]")
    coordinates = [float(item) for item in position]
    if any(coordinates[index] < self._lower[index] or coordinates[index] > self._upper[index] for index in range(3)):
      raise ValueError("pose is outside configured workspace")
    pose = Pose()
    pose.position.x, pose.position.y, pose.position.z = coordinates
    pose.orientation.x, pose.orientation.y, pose.orientation.z, pose.orientation.w = (float(item) for item in orientation)
    if not math.isclose(sum(value * value for value in orientation), 1.0, abs_tol=0.01):
      raise ValueError("pose orientation must be a normalized quaternion")
    return pose

  def _approved_approach(self, payload: dict, pose: Pose) -> dict | None:
    if payload.get("approval") != "EXECUTE_APPROACH_ONLY":
      return _response(False, "APPROVAL_REQUIRED", "Set approval to EXECUTE_APPROACH_ONLY for the registered approach pose.")
    approved_position = [float(item) for item in self.get_parameter("approved_approach_position").value]
    approved_orientation = [float(item) for item in self.get_parameter("approved_approach_orientation").value]
    if len(approved_position) != 3 or len(approved_orientation) != 4 or not all(math.isfinite(item) for item in approved_position + approved_orientation):
      return _response(False, "APPROACH_NOT_REGISTERED", "No approved approach pose is configured.")
    actual_position = [pose.position.x, pose.position.y, pose.position.z]
    if any(abs(actual_position[index] - approved_position[index]) > self._approach_position_tolerance for index in range(3)):
      return _response(False, "APPROACH_MISMATCH", "Requested position differs from the registered approach pose.")
    actual_orientation = [pose.orientation.x, pose.orientation.y, pose.orientation.z, pose.orientation.w]
    dot = abs(sum(actual_orientation[index] * approved_orientation[index] for index in range(4)))
    if 1.0 - dot > self._approach_orientation_tolerance:
      return _response(False, "APPROACH_MISMATCH", "Requested orientation differs from the registered approach pose.")
    return None

  def _gripper_reached_target(self, target_opening_m: float, closing: bool) -> bool:
    opening = self._gripper_state.get("opening")
    if not isinstance(opening, (int, float)):
      return False
    opening_value = float(opening)
    if closing:
      # A full close at zero aperture is an empty grasp, not a completed pick.
      # Hardware picks need a non-zero contact opening plus force, unless the
      # controller has already explicitly reported a stalled grasp.
      if target_opening_m <= 0.005:
        force = self._gripper_state.get("force")
        has_force_contact = isinstance(force, (int, float)) and float(force) >= 0.2 and opening_value > 0.003
        return bool(self._gripper_state.get("grasped")) or has_force_contact
      return bool(self._gripper_state.get("grasped")) or opening_value <= target_opening_m + 0.003
    return opening_value >= target_opening_m - 0.003

  def _wait_for_gripper_reach(self, target_opening_m: float, closing: bool, timeout_sec: float = 1.5) -> bool:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
      if self._gripper_reached_target(target_opening_m, closing):
        return True
      time.sleep(0.05)
    return self._gripper_reached_target(target_opening_m, closing)

  def _describe_gripper_state(self) -> str:
    opening = self._gripper_state.get("opening")
    opening_text = f"{float(opening):.4f}m" if isinstance(opening, (int, float)) else "unknown"
    status = self._gripper_state.get("status")
    status_label = self._gripper_state.get("status_label", "unknown")
    fault = self._gripper_state.get("fault_code")
    fault_label = self._gripper_state.get("fault_label", "unknown")
    return f"opening={opening_text}, status={status}({status_label}), fault={fault}({fault_label})"

  def _gripper_moving_without_fault(self) -> bool:
    status = self._gripper_state.get("status")
    status_label = self._gripper_state.get("status_label")
    fault_code = int(self._gripper_state.get("fault_code", 0) or 0)
    return fault_code == 0 and (status == 1 or status_label == "moving")

  def _gripper_stalled_without_fault(self) -> bool:
    status = self._gripper_state.get("status")
    status_label = self._gripper_state.get("status_label")
    fault_code = int(self._gripper_state.get("fault_code", 0) or 0)
    return fault_code == 0 and (status == 2 or status_label == "stalled")

  def _finish_gripper_response(self, response: dict, target_opening_m: float, closing: bool, require_feedback_target: bool = True, tolerate_non_terminal_failure: bool = False, feedback_timeout_sec: float = 8.0) -> dict:
    if response.get("success"):
      if not require_feedback_target:
        response["state"] = self._gripper_state
        return response
      if self._wait_for_gripper_reach(target_opening_m, closing, feedback_timeout_sec):
        response["state"] = self._gripper_state
        return response
      if closing and target_opening_m <= 0.005:
        return _response(
          False,
          "GRIPPER_CONTACT_NOT_DETECTED",
          f"Full-close command did not report object contact; last state: {self._describe_gripper_state()}.",
          state=self._gripper_state,
        )
      return _response(
        False,
        "GRIPPER_MOTION_INCOMPLETE",
        f"Gripper service returned success, but feedback did not reach target {target_opening_m:.4f} m; last state: {self._describe_gripper_state()}.",
        state=self._gripper_state,
      )
    if self._wait_for_gripper_reach(target_opening_m, closing, feedback_timeout_sec):
      return _response(
        True,
        "OK",
        "Gripper reached the requested state after a late controller failure.",
        state=self._gripper_state,
      )
    if tolerate_non_terminal_failure and int(self._gripper_state.get("fault_code", 0) or 0) == 0 and self._gripper_reached_target(target_opening_m, closing):
      return _response(
        True,
        "OK",
        f"Gripper command completed with non-terminal feedback tolerated: {response.get('message', 'unknown')}; last state: {self._describe_gripper_state()}.",
        state=self._gripper_state,
      )
    response["state"] = self._gripper_state
    response["message"] = f"{response.get('message', 'Gripper command failed')}; last state: {self._describe_gripper_state()}."
    return response

  def _gripper_position_command(self, requested_opening_m: float, opening: bool) -> tuple[float, float]:
    requested = min(self._max_gripper_opening, max(0.0, requested_opening_m))
    position = requested / self._max_gripper_opening if self._max_gripper_opening > 0.0 else 0.0
    if opening:
      # OmniPicker manual: position is a normalized 0.0-1.0 command, equivalent
      # to CAN 0x00-0xFF. Avoid commanding the full-open 0xFF endpoint because
      # fault code 0x04 is the device's over-limit detection warning.
      position = min(position, self._max_gripper_open_command)
    return position, position * self._max_gripper_opening

  def _call_approach(self, pose: Pose, speed: int) -> dict:
    if not self._move_pose.wait_for_service(timeout_sec=2.0):
      return _response(False, "ARM_SERVICE_UNAVAILABLE", "move_to_pose service is unavailable.")
    request = MoveToPose.Request()
    request.pose = pose
    request.speed = speed
    request.block = True
    completed = threading.Event()
    future = self._move_pose.call_async(request)
    future.add_done_callback(lambda _: completed.set())
    if not completed.wait(65.0):
      return _response(False, "ARM_TIMEOUT", "Approach request exceeded 65 seconds.")
    result = future.result()
    if result is None:
      return _response(False, "ARM_NO_RESPONSE", "move_to_pose returned no response.")
    return _response(bool(result.success), "OK" if result.success else f"ARM_{result.error_code}", result.message)

  def _speed(self, value: object) -> int:
    raw = float(value)
    if not math.isfinite(raw) or raw <= 0:
      raise ValueError("speed must be positive")
    return min(self._max_speed, max(1, round(raw * self._max_speed) if raw <= 1 else round(raw)))

  @staticmethod
  def _wait(client: Any, request: Any, timeout: float, code: str) -> dict:
    if not client.wait_for_service(timeout_sec=2.0):
      return _response(False, f"{code}_UNAVAILABLE", "Required ROS service is unavailable.")
    done = threading.Event(); future = client.call_async(request); future.add_done_callback(lambda _: done.set())
    if not done.wait(timeout): return _response(False, f"{code}_TIMEOUT", "ROS service response timed out.")
    result = future.result()
    if result is None: return _response(False, f"{code}_NO_RESPONSE", "ROS service returned no response.")
    success = bool(result.success)
    error = getattr(result, "error_code", getattr(result, "result_code", 0))
    return _response(success, "OK" if success else f"{code}_{error}", getattr(result, "message", str(error)))

  def _state(self) -> dict:
    if not self._current_pose.wait_for_service(timeout_sec=2.0):
      return _response(False, "ARM_STATE_UNAVAILABLE", "get_current_pose service is unavailable.")
    done = threading.Event(); future = self._current_pose.call_async(GetCurrentPose.Request()); future.add_done_callback(lambda _: done.set())
    if not done.wait(5.0): return _response(False, "ARM_STATE_TIMEOUT", "get_current_pose timed out.")
    result = future.result()
    if result is None or not result.valid: return _response(False, "ARM_STATE_INVALID", getattr(result, "message", "invalid pose"))
    pose = result.pose
    return _response(True, state={"arm": {"status": "idle", "pose": {"frame_id": self._base_frame, "position": [pose.position.x, pose.position.y, pose.position.z], "orientation": [pose.orientation.x, pose.orientation.y, pose.orientation.z, pose.orientation.w]}}, "gripper": self._gripper_state})

  @staticmethod
  def _pose_reached(target: Pose, state: dict, position_tolerance: float = 0.001, orientation_tolerance: float = 0.02) -> bool:
    pose = state.get("arm", {}).get("pose", {}) if isinstance(state, dict) else {}
    position = pose.get("position") if isinstance(pose, dict) else None
    orientation = pose.get("orientation") if isinstance(pose, dict) else None
    if not isinstance(position, list) or len(position) < 3:
      return False
    target_position = [target.position.x, target.position.y, target.position.z]
    position_error = sum((float(position[index]) - target_position[index]) ** 2 for index in range(3)) ** 0.5
    if position_error > position_tolerance:
      return False
    if not isinstance(orientation, list) or len(orientation) < 4:
      return True
    target_orientation = [target.orientation.x, target.orientation.y, target.orientation.z, target.orientation.w]
    dot = abs(sum(float(orientation[index]) * target_orientation[index] for index in range(4)))
    return 1.0 - min(1.0, dot) <= orientation_tolerance

  def _wait_for_pose_reach(self, pose: Pose) -> dict:
    deadline = time.monotonic() + self._motion_completion_timeout
    last_state: dict = {}
    while True:
      state_response = self._state()
      if state_response.get("success"):
        last_state = state_response.get("state", {})
        if self._pose_reached(pose, last_state):
          return _response(True, "OK", "Motion reached the requested pose.", state=last_state)
      if time.monotonic() >= deadline:
        break
      time.sleep(self._motion_poll_interval)
    return _response(
      False,
      "MOTION_INCOMPLETE",
      f"Motion did not reach the requested pose within {self._motion_completion_timeout:.1f} seconds.",
      state=last_state,
    )

  def _finish_motion_response(self, response: dict, pose: Pose, wait: bool) -> dict:
    if response.get("success"):
      if not wait:
        state_response = self._state()
        response["state"] = state_response.get("state", {})
        return response
      return self._wait_for_pose_reach(pose)
    # The arm-control server reports its internal completion timeout as error
    # code 4 but leaves the command active. Confirm the physical pose instead
    # of treating that stale service result as a failed motion.
    if "timeout" in str(response.get("message", "")).lower():
      completed = self._wait_for_pose_reach(pose)
      if completed.get("success"):
        completed["message"] = "Motion reached the requested pose after the driver completion timeout."
        return completed
      response["state"] = completed.get("state", {})
    return response

  def handle_request(self, method: str, path: str, payload: dict) -> dict:
    if method == "GET" and path == "/health": return _response(True, state={"allow_motion": bool(self.get_parameter("allow_motion").value)})
    if method == "GET" and path == "/ready": return _response(True, state=self.ready())
    if method == "GET" and path == "/gripper/state": return _response(True, state=self._gripper_state)
    if method == "GET" and path == "/state": return self._state()
    if method == "POST" and path == "/stop": self._stop.publish(Empty()); return _response(True, message="Stop command published.")
    if method == "POST" and path == "/dry-run/approach":
      blocked = self._motion_allowed()
      if blocked: return blocked
      try: pose = self._pose(payload)
      except (TypeError, ValueError) as exc: return _response(False, "POSE_INVALID", str(exc))
      denied = self._approved_approach(payload, pose)
      if denied: return denied
      speed = min(self._max_speed, max(1, int(payload.get("speed", self._max_speed))))
      return self._call_approach(pose, speed)
    if method == "POST" and path in {"/move-joints", "/move-pose", "/move-linear", "/gripper/open", "/gripper/close"}:
      blocked = self._motion_allowed()
      if blocked: return blocked
      try:
        if path == "/move-joints":
          joints = payload.get("joints")
          if not isinstance(joints, list) or len(joints) != 6: raise ValueError("joints requires six radians")
          request = MoveJDeg.Request(); request.joints = [degrees(float(value)) for value in joints]; request.speed = self._speed(payload.get("speed", 1)); request.block = bool(payload.get("wait", True))
          return self._wait(self._move_joints, request, 65.0, "MOVEJ")
        if path in {"/move-pose", "/move-linear"}:
          pose = self._pose(payload); request = (MoveL.Request() if path == "/move-linear" else MoveToPose.Request()); request.pose = pose; request.speed = self._speed(payload.get("speed", 1)); wait = bool(payload.get("wait", True)); request.block = wait
          response = self._wait(self._move_linear if path == "/move-linear" else self._move_pose, request, 65.0, "MOVEL" if path == "/move-linear" else "MOVEPOSE")
          return self._finish_motion_response(response, pose, wait)
        requested_opening_m = float(payload.get("opening", self._max_gripper_opening))
        opening, target_opening_m = self._gripper_position_command(requested_opening_m, path == "/gripper/open"); speed = min(1.0, max(0.0, float(payload.get("speed", 0.7))))
        release = bool(payload.get("release", False))
        require_contact = bool(payload.get("require_contact", True))
        if path == "/gripper/open" and target_opening_m >= self._max_gripper_opening * self._max_gripper_open_command - 1e-6:
          request = Open.Request(); request.speed = speed
          return self._finish_gripper_response(
            self._wait(self._open, request, 12.0, "GRIPPER_OPEN"),
            target_opening_m,
            False,
            require_feedback_target=False,
            tolerate_non_terminal_failure=True,
          )
        if path == "/gripper/open" and self._gripper_reached_target(target_opening_m, False):
          return _response(True, "OK", "Gripper is already open enough for the requested target.", state=self._gripper_state)
        request = SetPosition.Request(); request.position = opening if path == "/gripper/open" else max(0.0, opening); request.speed = speed
        if path == "/gripper/close" and opening <= 0.005:
          close = Close.Request(); close.force = min(1.0, max(0.0, float(payload.get("force", 0.6)))); close.speed = speed
          return self._finish_gripper_response(
            self._wait(self._close, close, 12.0, "GRIPPER_CLOSE"),
            target_opening_m,
            True,
            require_feedback_target=require_contact,
          )
        response = self._wait(self._set_position, request, 12.0, "GRIPPER_POSITION")
        if path == "/gripper/open" and not release and not response.get("success") and response.get("error_code") == "GRIPPER_POSITION_3" and self._gripper_moving_without_fault():
          open_request = Open.Request(); open_request.speed = speed
          retry = self._finish_gripper_response(
            self._wait(self._open, open_request, 12.0, "GRIPPER_OPEN_RECOVERY"),
            target_opening_m,
            False,
            require_feedback_target=True,
            tolerate_non_terminal_failure=True,
          )
          if retry.get("success"):
            retry["message"] = f"Recovered gripper open after {response.get('error_code')}: {retry.get('message', 'OK')}"
            return retry
        result = self._finish_gripper_response(
          response,
          target_opening_m,
          path == "/gripper/close",
          require_feedback_target=True,
        )
        if path == "/gripper/open" and release and not result.get("success") and (self._gripper_moving_without_fault() or self._gripper_stalled_without_fault()):
          return _response(
            True,
            "OK",
            "Release opening command remains in motion; continuing without full-open recovery.",
            state=self._gripper_state,
          )
        if path == "/gripper/open" and not release and not result.get("success") and (self._gripper_moving_without_fault() or self._gripper_stalled_without_fault()):
          open_request = Open.Request(); open_request.speed = speed
          retry = self._finish_gripper_response(
            self._wait(self._open, open_request, 12.0, "GRIPPER_OPEN_RECOVERY"),
            target_opening_m,
            False,
            require_feedback_target=True,
            tolerate_non_terminal_failure=True,
          )
          if retry.get("success"):
            retry["message"] = f"Recovered incomplete gripper open after partial-position command: {retry.get('message', 'OK')}"
            return retry
        return result
      except (TypeError, ValueError) as exc:
        return _response(False, "REQUEST_INVALID", str(exc))
    return _response(False, "NOT_FOUND", f"Unknown endpoint: {method} {path}")

  def start_http(self) -> None:
    bridge = self
    class Handler(BaseHTTPRequestHandler):
      def _serve(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        try: payload = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError: payload = {}
        body = json.dumps(bridge.handle_request(self.command, self.path, payload)).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
      do_GET = _serve
      do_POST = _serve
      def log_message(self, *_: Any) -> None: pass
    self._server = ThreadingHTTPServer((str(self.get_parameter("bind_host").value), int(self.get_parameter("bind_port").value)), Handler)
    threading.Thread(target=self._server.serve_forever, daemon=True).start()


def main() -> None:
  rclpy.init()
  node = HardwareBridge(); node.start_http()
  try: rclpy.spin(node)
  finally:
    if node._server: node._server.shutdown()
    node.destroy_node(); rclpy.shutdown()
