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
    completed_steps: list[str] = []
    steps = []
    pre_approach_joints = call.input.get("pre_approach_joints")
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
      ("retreat", "robot.move_linear", {"pose": plan.retreat.to_dict(), "speed": speed}),
    ])

    for step_name, tool_name, input_data in steps:
      result = context.tool_runtime.invoke(tool_name, input_data, call.trace)
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
