"""Grasp and place verification skills."""

from __future__ import annotations

from sensoragent.schemas import SkillCall, SkillResult, SkillSpec
from sensoragent.skills.base import SkillContext


def _read_gripper_opening(context: SkillContext, call: SkillCall) -> tuple[bool, float, str | None]:
  result = context.tool_runtime.invoke("gripper.get_state", {}, call.trace)
  if not result.success or not result.output:
    return False, 0.0, result.error or "gripper.get_state returned no output"
  state = result.output.get("state") or {}
  opening = state.get("opening")
  if not isinstance(opening, (int, float)):
    return False, 0.0, "gripper.get_state did not report a numeric opening"
  return True, float(opening), None


class RobotVerifyGraspSkill:
  """Confirm an object is held by reading gripper state."""

  spec = SkillSpec(
    name="robot.verify_grasp",
    description="Read gripper state and confirm an object is held.",
    tags=("robot", "verify", "grasp"),
  )

  def run(self, call: SkillCall, context: SkillContext) -> SkillResult:
    min_opening = float(call.input.get("min_opening", 0.002))
    max_opening = float(call.input.get("max_opening", 0.08))
    ok, opening, error = _read_gripper_opening(context, call)
    if not ok:
      return SkillResult(skill=self.spec.name, success=False, error=error)
    held = min_opening <= opening <= max_opening
    return SkillResult(
      skill=self.spec.name,
      success=held,
      output={"held": held, "opening": opening},
      error=None if held else f"grasp not detected (opening={opening:.4f})",
    )


class RobotVerifyPlaceSkill:
  """Confirm the object was released by reading gripper state."""

  spec = SkillSpec(
    name="robot.verify_place",
    description="Read gripper state and confirm the object was released.",
    tags=("robot", "verify", "place"),
  )

  def run(self, call: SkillCall, context: SkillContext) -> SkillResult:
    open_threshold = float(call.input.get("open_threshold", 0.05))
    ok, opening, error = _read_gripper_opening(context, call)
    if not ok:
      return SkillResult(skill=self.spec.name, success=False, error=error)
    released = opening >= open_threshold
    return SkillResult(
      skill=self.spec.name,
      success=released,
      output={"released": released, "opening": opening},
      error=None if released else f"place not confirmed (opening={opening:.4f})",
    )
