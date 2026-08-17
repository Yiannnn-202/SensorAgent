"""Configuration-driven hardware pick profile selection."""

from __future__ import annotations

from collections.abc import Mapping

from sensoragent.schemas import ToolCall, ToolResult, ToolSpec


class RobotSelectPickProfileTool:
  """Select a safe, named pick profile for a detected object."""

  spec = ToolSpec(
    name="robot.select_pick_profile",
    description="Select configured pick planner, geometry, and gripper settings.",
    tags=("robot", "planning", "pick", "profile"),
  )

  def __init__(self, profiles: Mapping[str, Mapping[str, object]] | None = None) -> None:
    self._profiles = {str(name).casefold(): dict(value) for name, value in (profiles or {}).items()}

  def run(self, call: ToolCall) -> ToolResult:
    requested = str(call.input.get("profile") or call.input.get("label") or "default").casefold()
    requested = requested.split(".", 1)[0].strip().replace(" ", "_")
    profile = self._profiles.get(requested, self._profiles.get("default", {}))
    if not profile:
      return ToolResult(tool=self.spec.name, success=False, error="PICK_PROFILE_NOT_FOUND: default")
    output = {
      "name": requested if requested in self._profiles else "default",
      "planner": str(profile.get("planner", "robot.plan_top_down_pick")),
      "orientation": profile.get("orientation", [0.0, 1.0, 0.0, 0.0]),
      "position_offset": profile.get("position_offset", [0.0, 0.0, 0.02]),
      "approach_distance": float(profile.get("approach_distance", 0.10)),
      "pregrasp_distance": float(profile.get("pregrasp_distance", 0.04)),
      "lift_height": float(profile.get("lift_height", 0.12)),
      "lift_speed": float(profile.get("lift_speed", profile.get("motion_speed", 1.2))),
      "open_opening": float(profile.get("open_opening", 0.120)),
      "close_opening": float(profile.get("close_opening", 0.032)),
      "gripper_force": float(profile.get("gripper_force", 0.5)),
      "gripper_speed": float(profile.get("gripper_speed", 0.5)),
      "motion_speed": float(profile.get("motion_speed", 1.2)),
      "descent_speed": float(profile.get("descent_speed", 1.2)),
      "tcp_offset": profile.get("tcp_offset", [0.0, 0.0, 0.161]),
      "headward_offset": float(profile.get("headward_offset", 0.015)),
      "camera_left_offset_px": float(profile.get("camera_left_offset_px", 0.0)),
      "camera_left_offset_m": float(profile.get("camera_left_offset_m", 0.0)),
      "minimum_safe_z": float(profile.get("minimum_safe_z", 0.14)),
      "workspace_min": profile.get("workspace_min", [-0.55, -0.18, 0.0]),
      "workspace_max": profile.get("workspace_max", [-0.20, 0.18, 0.35]),
    }
    return ToolResult(tool=self.spec.name, success=True, output=output)
