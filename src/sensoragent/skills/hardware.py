"""Physical hardware startup skill."""
from sensoragent.schemas import SkillCall, SkillResult, SkillSpec
from sensoragent.skills.base import SkillContext


class HardwareStartupSkill:
  spec = SkillSpec(name="hardware.startup", description="Start the SensorAgent-owned physical hardware stack.", tags=("hardware", "startup"))

  def run(self, call: SkillCall, context: SkillContext) -> SkillResult:
    result = context.tool_runtime.invoke("hardware.start_stack", {}, call.trace)
    return SkillResult(skill=self.spec.name, success=result.success, output=result.output or {}, error=result.error)
