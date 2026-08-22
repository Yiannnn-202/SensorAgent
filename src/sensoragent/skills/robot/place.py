"""Deterministic robot place skill."""

from __future__ import annotations

from sensoragent.schemas import SkillCall, SkillResult, SkillSpec
from sensoragent.schemas.robot import PlacePlan
from sensoragent.skills.base import SkillContext


class RobotPlaceSkill:
  """Execute a precomputed place plan using atomic robot tools."""

  spec = SkillSpec(
    name="robot.place",
    description="Approach, place, release, and retreat.",
    tags=("robot", "place"),
  )

  def run(self, call: SkillCall, context: SkillContext) -> SkillResult:
    plan = PlacePlan.from_dict(call.input.get("plan"))
    speed = call.input.get("speed", 0.2)
    post_release_lift = float(call.input.get("post_release_lift", 0.06))
    completed_steps: list[str] = []
    steps = []
    pre_approach_joints = call.input.get("pre_approach_joints")
    retreat_joints = call.input.get("retreat_joints")
    if pre_approach_joints is not None:
      steps.append(
        (
          "move_pre_approach_joints",
          "robot.move_joints",
          {"joints": pre_approach_joints, "speed": speed},
        )
      )
    steps.extend([
      ("move_approach", "robot.move_pose", {"pose": plan.approach.to_dict(), "speed": speed}),
      ("move_place", "robot.move_linear", {"pose": plan.place.to_dict(), "speed": speed}),
      (
        "open_gripper",
        "gripper.open",
        {
          "opening": call.input.get("open_opening", 0.0848),
          "speed": call.input.get("gripper_speed", 0.5),
        },
      ),
    ])
    lifted_retreat = plan.retreat
    if post_release_lift > 0.0:
      lifted_retreat = type(lifted_retreat)(
        position=(
          lifted_retreat.position[0],
          lifted_retreat.position[1],
          max(lifted_retreat.position[2], plan.place.position[2] + post_release_lift),
        ),
        orientation=lifted_retreat.orientation,
        frame_id=lifted_retreat.frame_id,
      )
      steps.append(("post_release_lift", "robot.move_linear", {"pose": lifted_retreat.to_dict(), "speed": speed}))
    if retreat_joints is None:
      steps.append(("retreat", "robot.move_linear", {"pose": lifted_retreat.to_dict(), "speed": speed}))
    else:
      steps.append(("retreat_joints", "robot.move_joints", {"joints": retreat_joints, "speed": speed}))

    for step_name, tool_name, input_data in steps:
      result = context.tool_runtime.invoke(tool_name, input_data, call.trace)
      if not result.success and step_name == "open_gripper":
        state_result = context.tool_runtime.invoke("gripper.get_state", {}, call.trace)
        opening = (state_result.output or {}).get("state", {}).get("opening") if state_result.success else None
        target_opening = float(input_data.get("opening", 0.0848))
        if isinstance(opening, (int, float)) and float(opening) >= target_opening - 0.003:
          result = state_result
      if (
        not result.success
        and tool_name == "robot.move_linear"
        and str(result.error or "").startswith("INCOMPLETE_CARTESIAN_PATH")
        and step_name in {"move_place", "post_release_lift", "retreat"}
      ):
        # The object is already released; mirror the pick skill and finish the
        # descent or retreat with a joint-space motion instead of failing.
        result = context.tool_runtime.invoke("robot.move_pose", input_data, call.trace)
      if (
        not result.success
        and tool_name == "robot.move_joints"
        and step_name == "retreat_joints"
      ):
        # Planning to the staging pose can abort with the gripper inside the
        # bin; fall back to the lifted retreat pose, then continue.
        result = context.tool_runtime.invoke(
          "robot.move_linear",
          {"pose": lifted_retreat.to_dict(), "speed": speed},
          call.trace,
        )
        if not result.success and str(result.error or "").startswith("INCOMPLETE_CARTESIAN_PATH"):
          result = context.tool_runtime.invoke(
            "robot.move_pose",
            {"pose": lifted_retreat.to_dict(), "speed": speed},
            call.trace,
          )
      if not result.success:
        return SkillResult(
          skill=self.spec.name,
          success=False,
          output={"completed_steps": completed_steps, "failed_step": step_name},
          error=f"{step_name}: {result.error}",
        )
      completed_steps.append(step_name)

    return SkillResult(
      skill=self.spec.name,
      success=True,
      output={
        "placed": True,
        "object_id": call.input.get("object_id"),
        "target": call.input.get("target"),
        "completed_steps": completed_steps,
      },
    )
