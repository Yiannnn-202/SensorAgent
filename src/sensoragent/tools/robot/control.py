"""Atomic robot and gripper control tools."""

from __future__ import annotations

import time
from typing import Any

from sensoragent.integrations.robot import RobotCommandResult, RobotControlClient
from sensoragent.schemas import ToolCall, ToolResult, ToolSpec
from sensoragent.schemas.robot import RobotPose


def _number(value: Any, field: str, default: float) -> float:
  if value is None:
    return default
  if not isinstance(value, (int, float)) or isinstance(value, bool):
    raise ValueError(f"{field} must be numeric")
  return float(value)


def _result(tool_name: str, backend_result: RobotCommandResult) -> ToolResult:
  if not backend_result.success:
    return ToolResult(
      tool=tool_name,
      success=False,
      error=f"{backend_result.error_code}: {backend_result.message}",
    )
  return ToolResult(
    tool=tool_name,
    success=True,
    output={
      "completed": True,
      "message": backend_result.message,
      "state": backend_result.state,
    },
  )


class RobotGetStateTool:
  spec = ToolSpec(
    name="robot.get_state",
    description="Get current arm and gripper state.",
    tags=("robot", "state"),
    timeout_seconds=5.0,
  )

  def __init__(self, client: RobotControlClient) -> None:
    self._client = client

  def run(self, call: ToolCall) -> ToolResult:
    del call
    return _result(self.spec.name, self._client.get_state())


class RobotMoveJointsTool:
  spec = ToolSpec(
    name="robot.move_joints",
    description="Move the arm to absolute joint positions in radians.",
    tags=("robot", "motion"),
    timeout_seconds=125.0,
  )

  def __init__(self, client: RobotControlClient) -> None:
    self._client = client

  def run(self, call: ToolCall) -> ToolResult:
    joints = call.input.get("joints")
    if not isinstance(joints, list) or not joints:
      raise ValueError("joints must be a non-empty list")
    if not all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in joints):
      raise ValueError("joints must contain numeric values")
    result = self._client.move_joints(
      [float(value) for value in joints],
      speed=_number(call.input.get("speed"), "speed", 0.2),
      wait=bool(call.input.get("wait", True)),
    )
    return _result(self.spec.name, result)


class RobotEnsureObservePoseTool:
  spec = ToolSpec(
    name="robot.ensure_observe_pose",
    description="Move to observe joints only when the TCP is not already at observe pose.",
    tags=("robot", "motion", "observe"),
    timeout_seconds=125.0,
  )

  def __init__(self, client: RobotControlClient) -> None:
    self._client = client

  @staticmethod
  def _observe_distance(state: dict, observe_pose: dict, tolerance: float) -> float | None:
    current_pose = state.get("arm", {}).get("pose", {}) if isinstance(state, dict) else {}
    current_position = current_pose.get("position") if isinstance(current_pose, dict) else None
    target_position = observe_pose.get("position") if isinstance(observe_pose, dict) else None
    if not isinstance(current_position, list) or not isinstance(target_position, list):
      return None
    if len(current_position) < 3 or len(target_position) < 3:
      return None
    distance = sum((float(current_position[index]) - float(target_position[index])) ** 2 for index in range(3)) ** 0.5
    return distance if distance <= tolerance else None

  @staticmethod
  def _observe_orientation_matches(state: dict, observe_pose: dict, tolerance: float = 0.01) -> bool:
    current_pose = state.get("arm", {}).get("pose", {}) if isinstance(state, dict) else {}
    current_orientation = current_pose.get("orientation") if isinstance(current_pose, dict) else None
    target_orientation = observe_pose.get("orientation") if isinstance(observe_pose, dict) else None
    if not isinstance(current_orientation, list) or not isinstance(target_orientation, list):
      return False
    if len(current_orientation) < 4 or len(target_orientation) < 4:
      return False
    current_norm = sum(float(value) ** 2 for value in current_orientation[:4]) ** 0.5
    target_norm = sum(float(value) ** 2 for value in target_orientation[:4]) ** 0.5
    if current_norm < 1e-9 or target_norm < 1e-9:
      return False
    dot = abs(sum(
      float(current_orientation[index]) * float(target_orientation[index])
      for index in range(4)
    ) / (current_norm * target_norm))
    return 1.0 - min(1.0, dot) <= tolerance

  def _wait_for_observe_pose(self, observe_pose: dict, tolerance: float, timeout_seconds: float = 90.0) -> tuple[float, dict] | None:
    deadline = time.monotonic() + timeout_seconds
    while True:
      state_result = self._client.get_state()
      if state_result.success:
        distance = self._observe_distance(state_result.state, observe_pose, tolerance)
        if distance is not None and self._observe_orientation_matches(state_result.state, observe_pose):
          return distance, state_result.state
      if time.monotonic() >= deadline:
        return None
      time.sleep(0.2)

  def run(self, call: ToolCall) -> ToolResult:
    joints = call.input.get("joints")
    if not isinstance(joints, list) or len(joints) != 6:
      raise ValueError("joints must contain six numeric values")
    if not all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in joints):
      raise ValueError("joints must contain numeric values")
    observe_pose = call.input.get("pose")
    state_result = self._client.get_state()
    if state_result.success and isinstance(observe_pose, dict):
      tolerance = _number(call.input.get("position_tolerance"), "position_tolerance", 0.015)
      distance = self._observe_distance(state_result.state, observe_pose, tolerance)
      if distance is not None and self._observe_orientation_matches(state_result.state, observe_pose):
        return ToolResult(
          tool=self.spec.name,
          success=True,
          output={"completed": True, "skipped": True, "distance": distance, "state": state_result.state},
        )
    result = self._client.move_joints(
      [float(value) for value in joints],
      speed=_number(call.input.get("speed"), "speed", 0.2),
      wait=bool(call.input.get("wait", True)),
    )
    if not result.success and isinstance(observe_pose, dict):
      tolerance = _number(call.input.get("position_tolerance"), "position_tolerance", 0.015)
      timed_out = "timeout" in str(result.message).lower() or "timed out" in str(result.message).lower()
      completed = self._wait_for_observe_pose(observe_pose, tolerance) if timed_out else None
      if completed is not None:
        distance, state = completed
        return ToolResult(
          tool=self.spec.name,
          success=True,
          output={
            "completed": True,
            "reached_after_motion_error": True,
            "distance": distance,
            "message": result.message,
            "state": state,
          },
        )
    return _result(self.spec.name, result)


class _RobotMovePoseTool:
  linear = False

  def __init__(self, client: RobotControlClient) -> None:
    self._client = client

  def run(self, call: ToolCall) -> ToolResult:
    pose = RobotPose.from_dict(call.input.get("pose"))
    result = self._client.move_pose(
      pose,
      speed=_number(call.input.get("speed"), "speed", 0.2),
      linear=self.linear,
      wait=bool(call.input.get("wait", True)),
      avoid_collisions=bool(call.input.get("avoid_collisions", True)),
    )
    return _result(self.spec.name, result)


class RobotMovePoseTool(_RobotMovePoseTool):
  spec = ToolSpec(
    name="robot.move_pose",
    description="Move the arm to a Cartesian pose using planned motion.",
    tags=("robot", "motion"),
    timeout_seconds=125.0,
  )


class RobotMoveLinearTool(_RobotMovePoseTool):
  linear = True
  spec = ToolSpec(
    name="robot.move_linear",
    description="Move the end effector linearly to a Cartesian pose.",
    tags=("robot", "motion"),
    timeout_seconds=125.0,
  )


class RobotStopTool:
  spec = ToolSpec(
    name="robot.stop",
    description="Stop active robot and gripper motion.",
    tags=("robot", "safety"),
    timeout_seconds=10.0,
  )

  def __init__(self, client: RobotControlClient) -> None:
    self._client = client

  def run(self, call: ToolCall) -> ToolResult:
    del call
    return _result(self.spec.name, self._client.stop())


class GripperOpenTool:
  spec = ToolSpec(
    name="gripper.open",
    description="Open the gripper to a requested opening in metres.",
    tags=("robot", "gripper"),
    timeout_seconds=25.0,
  )

  def __init__(self, client: RobotControlClient) -> None:
    self._client = client

  def run(self, call: ToolCall) -> ToolResult:
    result = self._client.open_gripper(
      opening=_number(call.input.get("opening"), "opening", 0.0848),
      speed=_number(call.input.get("speed"), "speed", 0.5),
      release=bool(call.input.get("release", False)),
    )
    return _result(self.spec.name, result)


class GripperCloseTool:
  spec = ToolSpec(
    name="gripper.close",
    description="Close the gripper to a requested opening and force.",
    tags=("robot", "gripper"),
    timeout_seconds=25.0,
  )

  def __init__(self, client: RobotControlClient) -> None:
    self._client = client

  def run(self, call: ToolCall) -> ToolResult:
    result = self._client.close_gripper(
      opening=_number(call.input.get("opening"), "opening", 0.0),
      force=_number(call.input.get("force"), "force", 0.5),
      speed=_number(call.input.get("speed"), "speed", 0.5),
      require_contact=bool(call.input.get("require_contact", True)),
    )
    return _result(self.spec.name, result)


class GripperGetStateTool:
  spec = ToolSpec(
    name="gripper.get_state",
    description="Get current gripper state.",
    tags=("robot", "gripper", "state"),
    timeout_seconds=5.0,
  )

  def __init__(self, client: RobotControlClient) -> None:
    self._client = client

  def run(self, call: ToolCall) -> ToolResult:
    del call
    return _result(self.spec.name, self._client.get_gripper_state())
