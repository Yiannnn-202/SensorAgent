"""Skill invocation runtime."""

from __future__ import annotations

from sensoragent.logger import TaskLogger
from sensoragent.schemas import SkillCall, SkillResult, TraceContext
from sensoragent.skills.base import SkillContext, SkillRegistry
from sensoragent.tools import ToolRuntime


class SkillRuntime:
  """Invokes registered skills with structured logging."""

  def __init__(
    self,
    registry: SkillRegistry,
    tool_runtime: ToolRuntime,
    logger: TaskLogger,
  ) -> None:
    self._registry = registry
    self._tool_runtime = tool_runtime
    self._logger = logger

  def invoke(self, skill_name: str, input_data: dict, trace: TraceContext) -> SkillResult:
    self._logger.log(
      "skill_call_started",
      trace,
      {"skill": skill_name, "input": input_data},
    )
    try:
      skill = self._registry.get(skill_name)
      result = skill.run(
        SkillCall(skill=skill_name, input=input_data, trace=trace),
        SkillContext(tool_runtime=self._tool_runtime, logger=self._logger),
      )
    except Exception as exc:  # Keep the minimal runtime failure-safe for Phase 1.
      result = SkillResult(skill=skill_name, success=False, error=str(exc))
    self._logger.log(
      "skill_call_finished",
      trace,
      {
        "skill": skill_name,
        "success": result.success,
        "output": result.output,
        "error": result.error,
      },
    )
    return result
