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
    return ToolResult(
      tool=self.spec.name,
      success=True,
      output={"target": target, "place_pose": pose.to_dict()},
    )


def default_place_target_registry() -> dict[str, dict]:
  """Static bin-cell layout for the industrial demo."""

  def pose(x: float, y: float, z: float) -> dict:
    return {
      "position": [x, y, z],
      "orientation": list(DEFAULT_PLACE_ORIENTATION),
      "frame_id": "base_link",
    }

  return {
    "bin_cell_1": pose(0.40, -0.20, 0.05),
    "bin_cell_2": pose(0.40, 0.00, 0.05),
    "bin_cell_3": pose(0.40, 0.20, 0.05),
    "conveyor": pose(0.55, 0.00, 0.05),
  }
