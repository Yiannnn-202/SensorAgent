"""Tests for the physical hardware bridge gripper fallbacks."""

from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest import TestCase

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
ROS2_PACKAGE_ROOT = ROOT / "ros2_ws" / "src" / "sensoragent_hardware_bridge"
for path in (SRC, ROS2_PACKAGE_ROOT):
  if str(path) not in sys.path:
    sys.path.insert(0, str(path))


def _install_ros_stubs() -> None:
  import types

  rclpy = ModuleType("rclpy")
  rclpy.init = lambda *args, **kwargs: None
  rclpy.shutdown = lambda *args, **kwargs: None
  rclpy.spin = lambda *args, **kwargs: None

  node = ModuleType("rclpy.node")

  class _Node:
    def __init__(self, *args, **kwargs) -> None:
      del args, kwargs

  node.Node = _Node
  rclpy.node = node

  geometry_msgs = ModuleType("geometry_msgs")
  geometry_msgs_msg = ModuleType("geometry_msgs.msg")

  class _Pose:
    def __init__(self) -> None:
      self.position = types.SimpleNamespace(x=0.0, y=0.0, z=0.0)
      self.orientation = types.SimpleNamespace(x=0.0, y=0.0, z=0.0, w=1.0)

  geometry_msgs_msg.Pose = _Pose
  geometry_msgs.msg = geometry_msgs_msg

  std_msgs = ModuleType("std_msgs")
  std_msgs_msg = ModuleType("std_msgs.msg")
  std_msgs_msg.Empty = type("Empty", (), {})
  std_msgs.msg = std_msgs_msg

  arm_control_interfaces = ModuleType("arm_control_interfaces")
  arm_control_interfaces_srv = ModuleType("arm_control_interfaces.srv")
  for name in ("GetCurrentPose", "MoveJDeg", "MoveL", "MoveToPose"):
    setattr(arm_control_interfaces_srv, name, type(name, (), {"Request": type("Request", (), {})}))
  arm_control_interfaces.srv = arm_control_interfaces_srv

  op_control_interfaces = ModuleType("op_control_interfaces")
  op_control_interfaces_msg = ModuleType("op_control_interfaces.msg")
  op_control_interfaces_msg.OmniPickerState = type("OmniPickerState", (), {})
  op_control_interfaces_srv = ModuleType("op_control_interfaces.srv")
  for name in ("Close", "Open", "SetPosition"):
    setattr(op_control_interfaces_srv, name, type(name, (), {"Request": type("Request", (), {})}))
  op_control_interfaces.msg = op_control_interfaces_msg
  op_control_interfaces.srv = op_control_interfaces_srv

  sys.modules.setdefault("rclpy", rclpy)
  sys.modules.setdefault("rclpy.node", node)
  sys.modules.setdefault("geometry_msgs", geometry_msgs)
  sys.modules.setdefault("geometry_msgs.msg", geometry_msgs_msg)
  sys.modules.setdefault("std_msgs", std_msgs)
  sys.modules.setdefault("std_msgs.msg", std_msgs_msg)
  sys.modules.setdefault("arm_control_interfaces", arm_control_interfaces)
  sys.modules.setdefault("arm_control_interfaces.srv", arm_control_interfaces_srv)
  sys.modules.setdefault("op_control_interfaces", op_control_interfaces)
  sys.modules.setdefault("op_control_interfaces.msg", op_control_interfaces_msg)
  sys.modules.setdefault("op_control_interfaces.srv", op_control_interfaces_srv)


try:
  from sensoragent_hardware_bridge.bridge_node import HardwareBridge
except ModuleNotFoundError:
  _install_ros_stubs()
  from sensoragent_hardware_bridge.bridge_node import HardwareBridge


class HardwareBridgeGripperStateTest(TestCase):
  def test_open_target_is_detected_from_state(self) -> None:
    bridge = object.__new__(HardwareBridge)
    bridge._gripper_state = {"opening": 0.0848, "grasped": False}

    self.assertTrue(bridge._gripper_reached_target(0.0848, False))

  def test_full_close_requires_contact_stall_feedback(self) -> None:
    bridge = object.__new__(HardwareBridge)
    bridge._gripper_state = {"opening": 0.001, "force": 0.8, "grasped": False}

    self.assertFalse(bridge._gripper_reached_target(0.0, True))

  def test_open_command_is_clamped_below_full_open(self) -> None:
    bridge = object.__new__(HardwareBridge)
    bridge._max_gripper_opening = 0.120
    bridge._max_gripper_open_command = 254.0 / 255.0

    position, target_opening = bridge._gripper_position_command(0.120, True)

    self.assertLess(position, 1.0)
    self.assertAlmostEqual(position, 254.0 / 255.0)
    self.assertAlmostEqual(target_opening, 0.120 * (254.0 / 255.0))

  def test_open_command_uses_meter_target_for_reach_check(self) -> None:
    bridge = object.__new__(HardwareBridge)
    bridge._max_gripper_opening = 0.120
    bridge._gripper_state = {"opening": 0.1196, "grasped": False}

    self.assertTrue(bridge._gripper_reached_target(0.1195, False))

  def test_full_open_request_uses_open_service_not_position_service(self) -> None:
    bridge = object.__new__(HardwareBridge)
    bridge._max_gripper_opening = 0.120
    bridge._max_gripper_open_command = 254.0 / 255.0
    bridge._open = object()
    bridge._close = object()
    bridge._set_position = object()
    bridge._gripper_state = {"status": "unknown"}
    bridge._motion_allowed = lambda: None
    calls = []

    def wait(client, request, timeout, code):
      calls.append((client, request, timeout, code))
      return {"success": True, "error_code": "OK", "message": "OK"}

    bridge._wait = wait
    bridge._finish_gripper_response = lambda response, *args, **kwargs: response

    response = bridge.handle_request(
      "POST",
      "/gripper/open",
      {"opening": 0.120, "speed": 0.5},
    )

    self.assertTrue(response["success"])
    self.assertEqual(calls[0][3], "GRIPPER_OPEN")

  def test_partial_open_request_uses_position_service(self) -> None:
    bridge = object.__new__(HardwareBridge)
    bridge._max_gripper_opening = 0.120
    bridge._max_gripper_open_command = 254.0 / 255.0
    bridge._open = object()
    bridge._close = object()
    bridge._set_position = object()
    bridge._gripper_state = {"status": "unknown"}
    bridge._motion_allowed = lambda: None
    calls = []

    def wait(client, request, timeout, code):
      calls.append((client, request, timeout, code))
      return {"success": True, "error_code": "OK", "message": "OK"}

    bridge._wait = wait
    bridge._finish_gripper_response = lambda response, *args, **kwargs: response

    response = bridge.handle_request(
      "POST",
      "/gripper/open",
      {"opening": 0.0848, "speed": 0.5},
    )

    self.assertTrue(response["success"])
    self.assertEqual(calls[0][3], "GRIPPER_POSITION")
    self.assertAlmostEqual(calls[0][1].position, 0.0848 / 0.120)

  def test_open_request_requires_feedback_after_driver_completion(self) -> None:
    bridge = object.__new__(HardwareBridge)
    bridge._max_gripper_opening = 0.120
    bridge._max_gripper_open_command = 254.0 / 255.0
    bridge._gripper_state = {"opening": 0.0696, "status": 1, "status_label": "moving", "fault_code": 0}
    bridge._motion_allowed = lambda: None
    bridge._open = object()
    bridge._close = object()
    bridge._set_position = object()
    bridge._wait_for_gripper_reach = lambda *args, **kwargs: False
    bridge._wait = lambda *args: {"success": True, "error_code": "OK", "message": "0"}

    response = bridge.handle_request("POST", "/gripper/open", {"opening": 0.084, "speed": 0.5})

    self.assertFalse(response["success"])
    self.assertEqual(response["error_code"], "GRIPPER_MOTION_INCOMPLETE")
    self.assertIn("status=1(moving)", response["message"])
    self.assertEqual(response["state"], bridge._gripper_state)

  def test_open_request_returns_success_when_current_opening_is_enough(self) -> None:
    bridge = object.__new__(HardwareBridge)
    bridge._max_gripper_opening = 0.120
    bridge._max_gripper_open_command = 254.0 / 255.0
    bridge._gripper_state = {"opening": 0.040, "status": 1, "status_label": "moving", "fault_code": 0}
    bridge._motion_allowed = lambda: None
    bridge._open = object()
    bridge._close = object()
    bridge._set_position = object()
    calls = []
    bridge._wait = lambda *args: calls.append(args) or {"success": False}

    response = bridge.handle_request("POST", "/gripper/open", {"opening": 0.040, "speed": 0.5})

    self.assertTrue(response["success"])
    self.assertEqual(calls, [])

  def test_position_open_code_3_uses_open_service_recovery(self) -> None:
    bridge = object.__new__(HardwareBridge)
    bridge._max_gripper_opening = 0.120
    bridge._max_gripper_open_command = 254.0 / 255.0
    bridge._gripper_state = {"opening": 0.0386, "status": 1, "status_label": "moving", "fault_code": 0}
    bridge._motion_allowed = lambda: None
    bridge._open = object()
    bridge._close = object()
    bridge._set_position = object()
    calls = []

    def wait(client, request, timeout, code):
      del client, request, timeout
      calls.append(code)
      if code == "GRIPPER_POSITION":
        return {"success": False, "error_code": "GRIPPER_POSITION_3", "message": "3"}
      bridge._gripper_state = {"opening": 0.091, "status": 1, "status_label": "moving", "fault_code": 0}
      return {"success": True, "error_code": "OK", "message": "0"}

    bridge._wait = wait

    response = bridge.handle_request("POST", "/gripper/open", {"opening": 0.090, "speed": 0.5})

    self.assertTrue(response["success"])
    self.assertEqual(calls, ["GRIPPER_POSITION", "GRIPPER_OPEN_RECOVERY"])

  def test_release_open_code_3_skips_open_service_recovery(self) -> None:
    bridge = object.__new__(HardwareBridge)
    bridge._max_gripper_opening = 0.120
    bridge._max_gripper_open_command = 254.0 / 255.0
    bridge._gripper_state = {"opening": 0.035, "status": 1, "status_label": "moving", "fault_code": 0}
    bridge._motion_allowed = lambda: None
    bridge._open = object()
    bridge._close = object()
    bridge._set_position = object()
    calls = []
    bridge._wait = lambda *args: calls.append(args[3]) or {
      "success": False, "error_code": "GRIPPER_POSITION_3", "message": "3"
    }
    def finish(*args, **kwargs):
      del args, kwargs
      bridge._gripper_state = {"opening": 0.040, "status": 2, "status_label": "stalled", "fault_code": 0}
      return {"success": False, "error_code": "GRIPPER_MOTION_INCOMPLETE", "message": "partial open incomplete"}

    bridge._finish_gripper_response = finish

    response = bridge.handle_request(
      "POST", "/gripper/open", {"opening": 0.040, "speed": 0.5, "release": True}
    )

    self.assertTrue(response["success"])
    self.assertEqual(calls, ["GRIPPER_POSITION"])
    self.assertIn("without full-open recovery", response["message"])

  def test_incomplete_partial_open_uses_open_service_recovery(self) -> None:
    bridge = object.__new__(HardwareBridge)
    bridge._max_gripper_opening = 0.120
    bridge._max_gripper_open_command = 254.0 / 255.0
    bridge._gripper_state = {"opening": 0.060, "status": 1, "status_label": "moving", "fault_code": 0}
    bridge._motion_allowed = lambda: None
    bridge._open = object()
    bridge._close = object()
    bridge._set_position = object()
    calls = []

    def wait(client, request, timeout, code):
      del client, request, timeout
      calls.append(code)
      if code == "GRIPPER_OPEN_RECOVERY":
        bridge._gripper_state = {"opening": 0.120, "status": 0, "status_label": "target_reached", "fault_code": 0}
      return {"success": True, "error_code": "OK", "message": "0"}

    def finish(response, *args, **kwargs):
      del args, kwargs
      if response["error_code"] == "OK" and calls[-1] == "GRIPPER_OPEN_RECOVERY":
        return response
      return {"success": False, "error_code": "GRIPPER_MOTION_INCOMPLETE", "message": "partial open incomplete"}

    bridge._wait = wait
    bridge._finish_gripper_response = finish

    response = bridge.handle_request("POST", "/gripper/open", {"opening": 0.070, "speed": 0.6})

    self.assertTrue(response["success"])
    self.assertEqual(calls, ["GRIPPER_POSITION", "GRIPPER_OPEN_RECOVERY"])
    self.assertIn("Recovered incomplete gripper open", response["message"])

  def test_release_open_does_not_trigger_full_open_recovery(self) -> None:
    bridge = object.__new__(HardwareBridge)
    bridge._max_gripper_opening = 0.120
    bridge._max_gripper_open_command = 254.0 / 255.0
    bridge._gripper_state = {"opening": 0.035, "status": 1, "status_label": "moving", "fault_code": 0}
    bridge._motion_allowed = lambda: None
    bridge._open = object()
    bridge._close = object()
    bridge._set_position = object()
    calls = []
    bridge._wait = lambda *args: calls.append(args[3]) or {"success": True, "error_code": "OK", "message": "0"}
    bridge._finish_gripper_response = lambda *args, **kwargs: {"success": False, "error_code": "GRIPPER_MOTION_INCOMPLETE", "message": "partial open incomplete"}

    response = bridge.handle_request("POST", "/gripper/open", {"opening": 0.040, "speed": 0.5, "release": True})

    self.assertTrue(response["success"])
    self.assertEqual(calls, ["GRIPPER_POSITION"])
    self.assertIn("without full-open recovery", response["message"])

  def test_gripper_state_decodes_manual_fault_and_status_codes(self) -> None:
    bridge = object.__new__(HardwareBridge)
    bridge._max_gripper_opening = 0.120
    message = SimpleNamespace(
      pos=3.0 / 255.0,
      force=0.52,
      status=2,
      raw_frame=[0x41, 0x41, 0x01, 0x04, 0x02, 0x03, 0x00, 0x85, 0x7F, 0x00, 0x00, 0xF5],
    )

    bridge._on_gripper_state(message)

    self.assertAlmostEqual(bridge._gripper_state["opening"], 0.120 * (3.0 / 255.0))
    self.assertEqual(bridge._gripper_state["fault_code"], 4)
    self.assertEqual(bridge._gripper_state["fault_label"], "over_limit")
    self.assertEqual(bridge._gripper_state["status"], 2)
    self.assertEqual(bridge._gripper_state["status_label"], "stalled")
    self.assertTrue(bridge._gripper_state["grasped"])

  def test_successful_service_response_requires_feedback_reaching_target(self) -> None:
    bridge = object.__new__(HardwareBridge)
    bridge._gripper_state = {
      "opening": 0.0715,
      "status": 1,
      "status_label": "moving",
      "fault_code": 0,
      "fault_label": "no_fault",
      "grasped": False,
    }
    bridge._wait_for_gripper_reach = lambda *args, **kwargs: False

    response = bridge._finish_gripper_response({"success": True, "error_code": "OK", "message": "0"}, 0.1195, False)

    self.assertFalse(response["success"])
    self.assertEqual(response["error_code"], "GRIPPER_MOTION_INCOMPLETE")
    self.assertIn("status=1(moving)", response["message"])

  def test_failed_service_response_is_tolerated_when_feedback_reaches_target(self) -> None:
    bridge = object.__new__(HardwareBridge)
    bridge._gripper_state = {
      "opening": 0.1196,
      "status": 0,
      "status_label": "target_reached",
      "fault_code": 0,
      "fault_label": "no_fault",
      "grasped": False,
    }
    bridge._wait_for_gripper_reach = lambda *args, **kwargs: True

    response = bridge._finish_gripper_response({"success": False, "error_code": "GRIPPER_POSITION_3", "message": "3"}, 0.1195, False)

    self.assertTrue(response["success"])
    self.assertEqual(response["error_code"], "OK")

  def test_successful_close_service_requires_contact_stall_feedback(self) -> None:
    bridge = object.__new__(HardwareBridge)
    bridge._gripper_state = {
      "opening": 0.0612,
      "status": 1,
      "status_label": "moving",
      "fault_code": 0,
      "fault_label": "no_fault",
      "grasped": False,
    }
    bridge._wait_for_gripper_reach = lambda *args, **kwargs: False

    response = bridge._finish_gripper_response(
      {"success": True, "error_code": "OK", "message": "0"},
      0.0,
      True,
    )

    self.assertFalse(response["success"])
    self.assertEqual(response["error_code"], "GRIPPER_CONTACT_NOT_DETECTED")

  def test_dedicated_open_rejects_non_terminal_feedback_below_target(self) -> None:
    bridge = object.__new__(HardwareBridge)
    bridge._gripper_state = {
      "opening": 0.0419,
      "status": 1,
      "status_label": "moving",
      "fault_code": 0,
      "fault_label": "no_fault",
      "grasped": False,
    }

    response = bridge._finish_gripper_response(
      {"success": False, "error_code": "GRIPPER_OPEN_3", "message": "3"},
      0.1195,
      False,
      require_feedback_target=True,
      tolerate_non_terminal_failure=True,
    )

    self.assertFalse(response["success"])
    self.assertEqual(response["error_code"], "GRIPPER_OPEN_3")
    self.assertIn("opening=0.0419m", response["message"])

  def test_motion_timeout_is_tolerated_when_pose_was_reached(self) -> None:
    bridge = object.__new__(HardwareBridge)
    target = SimpleNamespace(
      position=SimpleNamespace(x=-0.3589559, y=0.1132794, z=0.290121),
      orientation=SimpleNamespace(x=0.9897993, y=-0.1347532, z=-0.0458249, w=-0.0062387),
    )
    state = {
      "arm": {
        "pose": {
          "position": [-0.358957, 0.113286, 0.290125],
          "orientation": [0.989922, -0.133939, -0.045608, -0.005873],
        }
      }
    }
    bridge._state = lambda: {"success": True, "state": state}

    bridge._motion_completion_timeout = 1.0
    bridge._motion_poll_interval = 0.0
    response = bridge._finish_motion_response({"success": False, "error_code": "MOVEPOSE_TIMEOUT", "message": "timeout"}, target, True)

    self.assertTrue(response["success"])
    self.assertEqual(response["error_code"], "OK")
    self.assertEqual(response["state"], state)

  def test_motion_timeout_remains_failure_when_pose_was_not_reached(self) -> None:
    bridge = object.__new__(HardwareBridge)
    target = SimpleNamespace(
      position=SimpleNamespace(x=-0.3589559, y=0.1132794, z=0.290121),
      orientation=SimpleNamespace(x=0.9897993, y=-0.1347532, z=-0.0458249, w=-0.0062387),
    )
    state = {"arm": {"pose": {"position": [-0.30, 0.05, 0.30], "orientation": [0.0, 0.0, 0.0, 1.0]}}}
    bridge._state = lambda: {"success": True, "state": state}

    bridge._motion_completion_timeout = 0.0
    bridge._motion_poll_interval = 0.0
    response = bridge._finish_motion_response({"success": False, "error_code": "MOVEPOSE_TIMEOUT", "message": "timeout"}, target, True)

    self.assertFalse(response["success"])
    self.assertEqual(response["error_code"], "MOVEPOSE_TIMEOUT")
    self.assertEqual(response["state"], state)

  def test_successful_nonblocking_motion_waits_for_measured_pose(self) -> None:
    bridge = object.__new__(HardwareBridge)
    target = SimpleNamespace(
      position=SimpleNamespace(x=-0.3589559, y=0.1132794, z=0.290121),
      orientation=SimpleNamespace(x=0.9897993, y=-0.1347532, z=-0.0458249, w=-0.0062387),
    )
    pending = {"arm": {"pose": {"position": [-0.30, 0.05, 0.30], "orientation": [0.0, 0.0, 0.0, 1.0]}}}
    reached = {"arm": {"pose": {"position": [-0.358957, 0.113286, 0.290125], "orientation": [0.989922, -0.133939, -0.045608, -0.005873]}}}
    states = iter([pending, reached])
    bridge._state = lambda: {"success": True, "state": next(states)}
    bridge._motion_completion_timeout = 1.0
    bridge._motion_poll_interval = 0.0

    response = bridge._finish_motion_response({"success": True, "error_code": "OK", "message": "accepted"}, target, True)

    self.assertTrue(response["success"])
    self.assertEqual(response["state"], reached)
