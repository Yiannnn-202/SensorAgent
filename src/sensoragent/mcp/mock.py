"""MCP-shaped local entry point used by Phase 1 tests."""

from sensoragent.agent import AgentRuntime
from sensoragent.schemas import AgentRequest, AgentResponse


class MockMcpEndpoint:
  """Tiny MCP/API-shaped wrapper around the Agent runtime."""

  def __init__(self, agent: AgentRuntime) -> None:
    self._agent = agent

  def call_skill(self, skill: str, input_data: dict) -> AgentResponse:
    return self._agent.handle(AgentRequest(skill=skill, input=input_data))

  def call_actionlist(self, actionlist: str, input_data: dict) -> AgentResponse:
    return self._agent.handle(AgentRequest(actionlist=actionlist, input=input_data))
