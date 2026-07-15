"""Simple deterministic grasp and place planning helpers."""

from sensoragent.schemas.robot import PickPlan, PlacePlan, RobotPose


def build_top_down_pick_plan(
  grasp: RobotPose,
  *,
  approach_distance: float = 0.10,
  pregrasp_distance: float = 0.03,
  lift_height: float = 0.10,
) -> PickPlan:
  """Build vertical approach, pregrasp, grasp, and lift waypoints."""

  return PickPlan(
    approach=grasp.offset_z(approach_distance),
    pregrasp=grasp.offset_z(pregrasp_distance),
    grasp=grasp,
    lift=grasp.offset_z(lift_height),
  )


def build_place_plan(place: RobotPose, *, clearance: float = 0.08) -> PlacePlan:
  """Build vertical approach, place, and retreat waypoints."""

  safe_pose = place.offset_z(clearance)
  return PlacePlan(approach=safe_pose, place=place, retreat=safe_pose)
