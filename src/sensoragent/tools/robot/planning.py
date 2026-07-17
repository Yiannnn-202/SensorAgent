"""Robot planning tools that produce backend-neutral pick/place plans."""

from __future__ import annotations

from sensoragent.schemas import RobotPose, ToolCall, ToolResult, ToolSpec
from sensoragent.skills.robot import (
  build_oriented_pick_plan_from_points,
  build_place_plan,
  build_top_down_pick_plan,
)


DEFAULT_TOP_DOWN_ORIENTATION = (0.0, 1.0, 0.0, 0.0)


def _number_list(value, field: str, minimum_size: int) -> list[float]:
  if not isinstance(value, (list, tuple)) or len(value) < minimum_size:
    raise ValueError(f"{field} must contain at least {minimum_size} numeric values")
  result = []
  for item in value:
    if not isinstance(item, (int, float)) or isinstance(item, bool):
      raise ValueError(f"{field} must contain numeric values")
    result.append(float(item))
  return result


def _grasp_pose_from_input(input_data: dict) -> RobotPose:
  """Build a grasp pose from full pose or simple vision-returned 3D position."""

  if input_data.get("grasp_pose") is not None:
    return RobotPose.from_dict(input_data.get("grasp_pose"))

  position_value = (
    input_data.get("position")
    or input_data.get("point_3d")
    or input_data.get("pose_3d")
  )
  position = _number_list(position_value, "position/point_3d/pose_3d", 3)[:3]
  offset = input_data.get("position_offset", [0.0, 0.0, 0.0])
  offset_xyz = _number_list(offset, "position_offset", 3)[:3]
  orientation = input_data.get("orientation", DEFAULT_TOP_DOWN_ORIENTATION)
  orientation_xyzw = _number_list(orientation, "orientation", 4)[:4]
  return RobotPose(
    position=tuple(position[index] + offset_xyz[index] for index in range(3)),
    orientation=tuple(orientation_xyzw),
    frame_id=str(input_data.get("frame_id", "base_link")),
  )


class RobotPlanTopDownPickTool:
  """Generate a simple top-down PickPlan from a pose or vision 3D position."""

  spec = ToolSpec(
    name="robot.plan_top_down_pick",
    description="Generate pick waypoints from a grasp pose or a simple vision-returned 3D position.",
    tags=("robot", "planning", "pick"),
  )

  def run(self, call: ToolCall) -> ToolResult:
    grasp = _grasp_pose_from_input(call.input)
    plan = build_top_down_pick_plan(
      grasp,
      approach_distance=float(call.input.get("approach_distance", 0.10)),
      pregrasp_distance=float(call.input.get("pregrasp_distance", 0.03)),
      lift_height=float(call.input.get("lift_height", 0.10)),
    )
    return ToolResult(
      tool=self.spec.name,
      success=True,
      output={
        "grasp_pose": grasp.to_dict(),
        "plan": plan.to_dict(),
      },
    )


class RobotPlanOrientedPickTool:
  """Generate an oriented PickPlan from object point-cloud samples."""

  spec = ToolSpec(
    name="robot.plan_oriented_pick",
    description="Generate an oriented pick plan from base-frame object point samples.",
    tags=("robot", "planning", "pick", "point-cloud"),
  )

  def run(self, call: ToolCall) -> ToolResult:
    tcp_offset = tuple(float(value) for value in call.input.get("tcp_offset", [0.0, 0.0, 0.0]))
    if len(tcp_offset) != 3:
      raise ValueError("tcp_offset must contain three numbers")
    plan = build_oriented_pick_plan_from_points(
      call.input.get("points", []),
      frame_id=str(call.input.get("frame_id", "base_link")),
      approach_distance=float(call.input.get("approach_distance", 0.10)),
      pregrasp_distance=float(call.input.get("pregrasp_distance", 0.03)),
      lift_height=float(call.input.get("lift_height", 0.10)),
      tcp_offset=tcp_offset,
    )
    return ToolResult(
      tool=self.spec.name,
      success=True,
      output={"plan": plan.to_dict()},
    )


class RobotPlanPlaceTool:
  """Generate a simple PlacePlan from a target place pose."""

  spec = ToolSpec(
    name="robot.plan_place",
    description="Generate approach, place, and retreat waypoints from a place pose.",
    tags=("robot", "planning", "place"),
  )

  def run(self, call: ToolCall) -> ToolResult:
    place = RobotPose.from_dict(call.input.get("place_pose"))
    plan = build_place_plan(
      place,
      clearance=float(call.input.get("clearance", 0.08)),
    )
    return ToolResult(
      tool=self.spec.name,
      success=True,
      output={"plan": plan.to_dict()},
    )
