"""Resolve place-target identifiers into concrete place poses."""

from __future__ import annotations

from typing import Mapping

from sensoragent.schemas import ToolCall, ToolResult, ToolSpec
from sensoragent.schemas.robot import RobotPose


DEFAULT_PLACE_ORIENTATION = (0.0, 1.0, 0.0, 0.0)


class RobotResolvePlaceTargetTool:
  """Look up a preconfigured place pose by target identifier."""

  spec = ToolSpec(
    name="robot.resolve_place_target",
    description="Resolve a place-target identifier (e.g. bin_cell_3) into a place pose.",
    tags=("robot", "planning", "place"),
  )

  def __init__(self, registry: Mapping[str, dict] | None = None) -> None:
    self._registry: dict[str, RobotPose] = {}
    for key, value in (registry or {}).items():
      self._registry[key] = RobotPose.from_dict(value)

  def register(self, target: str, pose: RobotPose) -> None:
    self._registry[target] = pose

  def run(self, call: ToolCall) -> ToolResult:
    target = call.input.get("target")
    if not isinstance(target, str) or not target:
      return ToolResult(
        tool=self.spec.name,
        success=False,
        error="target must be a non-empty string",
      )
    pose = self._registry.get(target)
    if pose is None:
      return ToolResult(
        tool=self.spec.name,
        success=False,
        error=f"unknown place target: {target}",
      )
    release_z = call.input.get("release_z")
    if release_z is not None:
      try:
        pose = RobotPose(
          position=(pose.position[0], pose.position[1], float(release_z)),
          orientation=pose.orientation,
          frame_id=pose.frame_id,
        )
      except (TypeError, ValueError):
        return ToolResult(tool=self.spec.name, success=False, error="release_z must be numeric")
    place_offset = call.input.get("place_offset")
    if place_offset is not None:
      if (
        not isinstance(place_offset, list)
        or len(place_offset) < 3
        or not all(isinstance(item, (int, float)) and not isinstance(item, bool) for item in place_offset[:3])
      ):
        return ToolResult(tool=self.spec.name, success=False, error="place_offset must contain three numeric values")
      pose = RobotPose(
        position=(
          pose.position[0] + float(place_offset[0]),
          pose.position[1] + float(place_offset[1]),
          pose.position[2] + float(place_offset[2]),
        ),
        orientation=pose.orientation,
        frame_id=pose.frame_id,
      )
    return ToolResult(
      tool=self.spec.name,
      success=True,
      output={"target": target, "place_pose": pose.to_dict()},
    )


def default_place_target_registry() -> dict[str, dict]:
  """Static bin-cell layout for the industrial demo.

  Coordinates are TCP release poses in base_link. Workbench top sits at
  base_link z ≈ 0.12; z = 0.22 keeps the gripper TCP roughly 0.10 m above the
  workbench when releasing, matching the sim scripts' default place clearance.
  """

  def pose(x: float, y: float, z: float) -> dict:
    return {
      "position": [x, y, z],
      "orientation": list(DEFAULT_PLACE_ORIENTATION),
      "frame_id": "base_link",
    }

  return {
    "bin_cell_1": pose(0.42, -0.15, 0.22),
    "bin_cell_2": pose(0.42, 0.00, 0.22),
    "bin_cell_3": pose(0.42, 0.15, 0.22),
    "conveyor": pose(0.50, 0.10, 0.22),
  }
