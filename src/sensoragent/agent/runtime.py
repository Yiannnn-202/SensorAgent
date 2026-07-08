"""Agent runtime for dispatching skills and workflows."""

from __future__ import annotations

from sensoragent.logger import TaskLogger
from sensoragent.schemas import ActionList, AgentRequest, AgentResponse
from sensoragent.skills import SkillRuntime
from sensoragent.workflows import ActionListRuntime


class AgentRuntime:
  """Dispatches Agent requests to skills or ActionList workflows."""

  def __init__(
    self,
    skill_runtime: SkillRuntime,
    logger: TaskLogger,
    actionlist_runtime: ActionListRuntime | None = None,
    actionlists: dict[str, ActionList] | None = None,
  ) -> None:
    self._skill_runtime = skill_runtime
    self._logger = logger
    self._actionlist_runtime = actionlist_runtime
    self._actionlists = actionlists or {}

  def _handle_skill(self, request: AgentRequest) -> AgentResponse:
    if request.skill is None:
      return AgentResponse(
        success=False,
        result=None,
        error="AgentRequest.skill is required for skill dispatch",
        trace=request.trace,
      )
    result = self._skill_runtime.invoke(request.skill, request.input, request.trace)
    return AgentResponse(
      success=result.success,
      result=result.output,
      error=result.error,
      trace=request.trace,
    )

  def _handle_actionlist(self, request: AgentRequest) -> AgentResponse:
    if request.actionlist is None:
      return AgentResponse(
        success=False,
        result=None,
        error="AgentRequest.actionlist is required for ActionList dispatch",
        trace=request.trace,
      )
    if self._actionlist_runtime is None:
      return AgentResponse(
        success=False,
        result=None,
        error="ActionList runtime is not configured",
        trace=request.trace,
      )
    actionlist = self._actionlists.get(request.actionlist)
    if actionlist is None:
      return AgentResponse(
        success=False,
        result=None,
        error=f"Unknown actionlist: {request.actionlist}",
        trace=request.trace,
      )
    result = self._actionlist_runtime.run(actionlist, request.input, request.trace)
    return AgentResponse(
      success=result.success,
      result=result.output,
      error=result.error,
      trace=request.trace,
    )

  def handle(self, request: AgentRequest) -> AgentResponse:
    self._logger.log(
      "agent_request_started",
      request.trace,
      {
        "skill": request.skill,
        "actionlist": request.actionlist,
        "input": request.input,
      },
    )

    if request.skill and request.actionlist:
      response = AgentResponse(
        success=False,
        result=None,
        error="AgentRequest cannot specify both skill and actionlist",
        trace=request.trace,
      )
    elif request.actionlist:
      response = self._handle_actionlist(request)
    else:
      response = self._handle_skill(request)

    self._logger.log(
      "agent_request_finished",
      request.trace,
      {
        "skill": request.skill,
        "actionlist": request.actionlist,
        "success": response.success,
        "result": response.result,
        "error": response.error,
      },
    )
    return response
