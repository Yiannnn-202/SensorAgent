"""Build SensorAgent runtimes from configuration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from sensoragent.agent.runtime import AgentRuntime
from sensoragent.config import SensorAgentConfig, load_config, resolve_config_path
from sensoragent.contracts import ContractValidator
from sensoragent.logger import TaskLogger
from sensoragent.skills import SkillRegistry, SkillRuntime
from sensoragent.skills.mock import MockPickAndPlaceSkill
from sensoragent.tools import ToolRegistry, ToolRuntime
from sensoragent.tools.audio.mock import MockTranscribeTool
from sensoragent.tools.robot.mock import MockPickTool, MockPlaceTool
from sensoragent.tools.vision.mock import MockDetectTool
from sensoragent.workflows import ActionListRuntime, build_mock_pick_place_actionlist


ToolFactory = Callable[[], object]
SkillFactory = Callable[[], object]


AVAILABLE_TOOLS: dict[str, ToolFactory] = {
  "vision.mock_detect": MockDetectTool,
  "audio.mock_transcribe": MockTranscribeTool,
  "robot.mock_pick": MockPickTool,
  "robot.mock_place": MockPlaceTool,
}

AVAILABLE_SKILLS: dict[str, SkillFactory] = {
  "mock.pick_and_place": MockPickAndPlaceSkill,
}


@dataclass(frozen=True)
class AgentBundle:
  """Runtime objects assembled from configuration."""

  agent: AgentRuntime
  logger: TaskLogger
  tool_registry: ToolRegistry
  tool_runtime: ToolRuntime
  skill_registry: SkillRegistry
  skill_runtime: SkillRuntime
  actionlist_runtime: ActionListRuntime
  actionlists: dict[str, object]


def build_agent(config: SensorAgentConfig, log_path: Path | None = None) -> AgentBundle:
  """Build SensorAgent runtime objects from a loaded config."""

  logger = TaskLogger(log_path)

  tool_registry = ToolRegistry()
  for tool_name in config.tools.enabled:
    try:
      tool_factory = AVAILABLE_TOOLS[tool_name]
    except KeyError as exc:
      raise KeyError(f"Configured tool is not available: {tool_name}") from exc
    tool_registry.register(tool_factory())

  tool_runtime = ToolRuntime(tool_registry, logger, ContractValidator())

  skill_registry = SkillRegistry()
  for skill_name in config.skills.enabled:
    try:
      skill_factory = AVAILABLE_SKILLS[skill_name]
    except KeyError as exc:
      raise KeyError(f"Configured skill is not available: {skill_name}") from exc
    skill_registry.register(skill_factory())

  skill_runtime = SkillRuntime(skill_registry, tool_runtime, logger)
  actionlist_runtime = ActionListRuntime(tool_runtime, skill_runtime, logger)
  actionlists = {
    "mock.pick_place_actionlist": build_mock_pick_place_actionlist(),
  }
  agent = AgentRuntime(
    skill_runtime,
    logger,
    actionlist_runtime=actionlist_runtime,
    actionlists=actionlists,
  )

  return AgentBundle(
    agent=agent,
    logger=logger,
    tool_registry=tool_registry,
    tool_runtime=tool_runtime,
    skill_registry=skill_registry,
    skill_runtime=skill_runtime,
    actionlist_runtime=actionlist_runtime,
    actionlists=actionlists,
  )


def build_agent_from_config(path: str | Path, log_path: Path | None = None) -> AgentBundle:
  """Load a YAML config and build SensorAgent runtime objects."""

  return build_agent(load_config(path), log_path=log_path)


def build_agent_from_env(
  explicit_path: str | Path | None = None,
  *,
  log_path: Path | None = None,
) -> AgentBundle:
  """Resolve configuration from arguments/environment and build SensorAgent."""

  return build_agent_from_config(resolve_config_path(explicit_path), log_path=log_path)
