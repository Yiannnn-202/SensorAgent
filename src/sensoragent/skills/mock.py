"""Mock skills for the first end-to-end SensorAgent chain."""

from sensoragent.schemas import SkillCall, SkillResult, SkillSpec
from sensoragent.skills.base import SkillContext


class MockPickAndPlaceSkill:
  """Mock industrial pick-and-place skill using mock vision and robot tools."""

  spec = SkillSpec(
    name="mock.pick_and_place",
    description="Mock pick-and-place skill calling vision and robot tools.",
  )

  def run(self, call: SkillCall, context: SkillContext) -> SkillResult:
    object_query = call.input.get("object_query", "silver roller")
    target = call.input.get("target", "third bin cell")

    detection = context.tool_runtime.invoke(
      "vision.mock_detect",
      {"query": object_query},
      call.trace,
    )
    if not detection.success or not detection.output:
      return SkillResult(skill=self.spec.name, success=False, error=detection.error)

    object_id = detection.output["object_id"]
    pick = context.tool_runtime.invoke(
      "robot.mock_pick",
      {"object_id": object_id, "pose_3d": detection.output["pose_3d"]},
      call.trace,
    )
    if not pick.success:
      return SkillResult(skill=self.spec.name, success=False, error=pick.error)

    place = context.tool_runtime.invoke(
      "robot.mock_place",
      {"object_id": object_id, "target": target},
      call.trace,
    )
    if not place.success:
      return SkillResult(skill=self.spec.name, success=False, error=place.error)

    return SkillResult(
      skill=self.spec.name,
      success=True,
      output={
        "object": detection.output,
        "pick": pick.output,
        "place": place.output,
        "summary": f"Placed {object_query} into {target}.",
      },
    )
