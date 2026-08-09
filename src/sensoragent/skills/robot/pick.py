"""Deterministic robot pick skill."""

from __future__ import annotations

from sensoragent.schemas import SkillCall, SkillResult, SkillSpec
from sensoragent.schemas.robot import PickPlan
from sensoragent.skills.base import SkillContext


class RobotPickSkill:
  """Execute a precomputed pick plan using atomic robot tools."""

  spec = SkillSpec(
    name="robot.pick",
    description="Open, approach, grasp, close, and lift an object.",
    tags=("robot", "pick"),
  )

  def run(self, call: SkillCall, context: SkillContext) -> SkillResult:
    plan = PickPlan.from_dict(call.input.get("plan"))
    speed = call.input.get("speed", 0.2)
    descent_speed = call.input.get("descent_speed", speed)
    completed_steps: list[str] = []
    stage_results: list[dict] = []
    plan_output = plan.to_dict()
    steps = [
      (
        "open_gripper",
        "gripper.open",
        {
          "opening": call.input.get("open_opening", 0.0848),
          "speed": call.input.get("gripper_speed", 0.5),
        },
      ),
      ("move_approach", "robot.move_pose", {"pose": plan.approach.to_dict(), "speed": speed}),
      (
        "move_pregrasp",
        "robot.move_linear",
        {"pose": plan.pregrasp.to_dict(), "speed": descent_speed},
      ),
      ("move_grasp", "robot.move_linear", {"pose": plan.grasp.to_dict(), "speed": descent_speed}),
      (
        "close_gripper",
        "gripper.close",
        {
          "opening": call.input.get("close_opening", 0.0),
          "force": call.input.get("gripper_force", 0.5),
          "speed": call.input.get("gripper_speed", 0.5),
        },
      ),
      ("lift", "robot.move_linear", {"pose": plan.lift.to_dict(), "speed": speed}),
    ]

    for step_name, tool_name, input_data in steps:
      result = context.tool_runtime.invoke(tool_name, input_data, call.trace)
      if not result.success and step_name == "open_gripper":
        state_result = context.tool_runtime.invoke("gripper.get_state", {}, call.trace)
        opening = (state_result.output or {}).get("state", {}).get("opening") if state_result.success else None
        target_opening = float(input_data.get("opening", 0.0848))
        if isinstance(opening, (int, float)) and float(opening) >= target_opening - 0.003:
          result = state_result
      if not result.success and step_name == "close_gripper":
        state_result = context.tool_runtime.invoke("gripper.get_state", {}, call.trace)
        state = (state_result.output or {}).get("state", {}) if state_result.success else {}
        opening = state.get("opening") if isinstance(state, dict) else None
        min_opening = float(call.input.get("verify_min_opening", 0.002))
        max_opening = float(call.input.get("verify_max_opening", 0.08))
        if isinstance(opening, (int, float)) and min_opening <= float(opening) <= max_opening:
          stage_results.append(
            {
              "step": "close_gripper_state_check",
              "tool": "gripper.get_state",
              "input": {},
              "success": True,
              "output": state_result.output,
              "tolerated_error": result.error,
            }
          )
          result = state_result
      if (
        not result.success
        and step_name in {"move_pregrasp", "move_grasp", "lift"}
        and tool_name == "robot.move_linear"
      ):
        stage_results.append(
          {
            "step": f"{step_name}_cartesian",
            "tool": tool_name,
            "input": input_data,
            "success": False,
            "output": result.output,
            "error": result.error,
          }
        )
        result = context.tool_runtime.invoke("robot.move_pose", input_data, call.trace)
      stage_results.append(
        {
          "step": step_name,
          "tool": result.tool,
          "input": input_data,
          "success": result.success,
          "output": result.output,
          "error": result.error,
        }
      )
      if not result.success:
        return SkillResult(
          skill=self.spec.name,
          success=False,
          output={
            "completed_steps": completed_steps,
            "failed_step": step_name,
            "plan": plan_output,
            "stages": stage_results,
          },
          error=f"{step_name}: {result.error}",
        )
      completed_steps.append(step_name)

    return SkillResult(
      skill=self.spec.name,
      success=True,
      output={
        "picked": True,
        "object_id": call.input.get("object_id"),
        "completed_steps": completed_steps,
        "plan": plan_output,
        "stages": stage_results,
      },
    )
