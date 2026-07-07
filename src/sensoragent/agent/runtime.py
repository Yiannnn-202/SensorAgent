"""Minimal Agent runtime for Phase 1."""

from __future__ import annotations

from sensoragent.logger import TaskLogger
from sensoragent.schemas import AgentRequest, AgentResponse
from sensoragent.skills import SkillRuntime


class AgentRuntime:
  """Dispatches Agent requests to skills."""

  def __init__(self, skill_runtime: SkillRuntime, logger: TaskLogger) -> None:
    self._skill_runtime = skill_runtime
    self._logger = logger

  def handle(self, request: AgentRequest) -> AgentResponse:
    self._logger.log(
      "agent_request_started",
      request.trace,
      {"skill": request.skill, "input": request.input},
    )
    result = self._skill_runtime.invoke(request.skill, request.input, request.trace)
    response = AgentResponse(
      success=result.success,
      result=result.output,
      error=result.error,
      trace=request.trace,
    )
    self._logger.log(
      "agent_request_finished",
      request.trace,
      {
        "skill": request.skill,
        "success": response.success,
        "result": response.result,
        "error": response.error,
      },
    )
    return response
