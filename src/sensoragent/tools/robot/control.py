"""Atomic robot and gripper control tools."""

from __future__ import annotations

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
