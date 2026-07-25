"""Vision-side verification tools for failure detection."""

from __future__ import annotations

from math import dist, isfinite
from typing import Any, Mapping

from sensoragent.schemas import ToolCall, ToolResult, ToolSpec
from sensoragent.schemas.robot import RobotPose


class VisionVerifyObjectInBinTool:
  """Verify that an observed object pose is inside the requested bin target."""

  spec = ToolSpec(
    name="vision.verify_object_in_bin",
    description="Check whether an observed object position lies in a named place target.",
    tags=("vision", "verify", "place"),
  )

  def __init__(self, place_targets: Mapping[str, dict] | None = None) -> None:
    self._targets: dict[str, RobotPose] = {}
    for key, value in (place_targets or {}).items():
      self._targets[key] = RobotPose.from_dict(value)

  def run(self, call: ToolCall) -> ToolResult:
    target = call.input.get("target")
    if not isinstance(target, str) or not target:
      return ToolResult(tool=self.spec.name, success=False, error="target must be a non-empty string")
    target_pose = _target_pose(call.input, target, self._targets)
    if target_pose is None:
      return ToolResult(tool=self.spec.name, success=False, error=f"TARGET_NOT_FOUND: {target}")
    object_position = _position_from_input(call.input.get("object_pose") or call.input.get("pose_3d") or call.input.get("object"))
    if object_position is None:
      return ToolResult(
        tool=self.spec.name,
        success=False,
        error="POSE_INVALID: object_pose/pose_3d must contain at least 3 numeric coordinates",
      )
    tolerance_xy = float(call.input.get("tolerance_xy", 0.08))
    max_z_error = float(call.input.get("max_z_error", 0.25))
    target_position = list(target_pose.position)
    distance_xy = dist(object_position[:2], target_position[:2])
    z_error = abs(object_position[2] - target_position[2])
    in_target = distance_xy <= tolerance_xy and z_error <= max_z_error
    output = {
      "target": target,
      "in_target": in_target,
      "object_position": object_position,
      "target_position": target_position,
      "distance_xy": distance_xy,
      "z_error": z_error,
      "tolerance_xy": tolerance_xy,
      "max_z_error": max_z_error,
    }
    return ToolResult(
      tool=self.spec.name,
      success=in_target,
      output=output,
      error=None if in_target else "WRONG_BIN: object is outside the requested target cell",
    )


class VisionVerifyObjectLiftedTool:
  """Verify that an object moved upward after grasping."""

  spec = ToolSpec(
    name="vision.verify_object_lifted",
    description="Compare before/after object poses to detect an empty grasp or drop.",
    tags=("vision", "verify", "grasp"),
  )

  def run(self, call: ToolCall) -> ToolResult:
    before = _position_from_input(call.input.get("before_pose"))
    after = _position_from_input(call.input.get("after_pose") or call.input.get("current_pose"))
    if before is None or after is None:
      return ToolResult(
        tool=self.spec.name,
        success=False,
        error="POSE_INVALID: before_pose and after_pose/current_pose must contain 3 numeric coordinates",
      )
    min_lift_delta = float(call.input.get("min_lift_delta", 0.04))
    max_xy_drift = float(call.input.get("max_xy_drift", 0.18))
    lift_delta = after[2] - before[2]
    xy_drift = dist(before[:2], after[:2])
    lifted = lift_delta >= min_lift_delta and xy_drift <= max_xy_drift
    output = {
      "lifted": lifted,
      "before_position": before,
      "after_position": after,
      "lift_delta": lift_delta,
      "xy_drift": xy_drift,
      "min_lift_delta": min_lift_delta,
      "max_xy_drift": max_xy_drift,
    }
    return ToolResult(
      tool=self.spec.name,
      success=lifted,
      output=output,
      error=None if lifted else "DROPPED_OBJECT: object did not move with the gripper",
    )


def _target_pose(input_data: dict[str, Any], target: str, targets: dict[str, RobotPose]) -> RobotPose | None:
  inline = input_data.get("target_pose") or input_data.get("place_pose")
  if isinstance(inline, dict):
    return RobotPose.from_dict(inline)
  return targets.get(target)


def _position_from_input(value: Any) -> list[float] | None:
  if isinstance(value, dict):
    for key in ("position", "position_base", "pose_3d"):
      position = _position_from_input(value.get(key))
      if position is not None:
        return position
    return None
  if not isinstance(value, list) or len(value) < 3:
    return None
  position: list[float] = []
  for item in value[:3]:
    if not isinstance(item, (int, float)) or isinstance(item, bool):
      return None
    number = float(item)
    if not isfinite(number):
      return None
    position.append(number)
  return position
