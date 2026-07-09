"""Build SensorAgent runtimes from configuration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from sensoragent.agent.runtime import AgentRuntime
from sensoragent.config import SensorAgentConfig, load_config, resolve_config_path
from sensoragent.contracts import ContractValidator
from sensoragent.integrations import (
  FakeAudioClient,
  FakeMicrophoneRecorder,
  LocalAudioClient,
  OpenAICompatibleClient,
  SoundDeviceRecorder,
  load_llm_config_from_env,
)
from sensoragent.logger import TaskLogger
from sensoragent.skills import SkillRegistry, SkillRuntime
from sensoragent.skills.mock import MockPickAndPlaceSkill
from sensoragent.state import InMemoryEventStream, InMemoryTaskStore
from sensoragent.tools import ToolRegistry, ToolRuntime
from sensoragent.tools.audio.mock import MockTranscribeTool
from sensoragent.tools.audio import (
  AudioListenTranscribeTool,
  AudioSpeakTool,
  AudioTranscribeTool,
)
from sensoragent.tools.robot.mock import MockPickTool, MockPlaceTool
from sensoragent.tools.vision.mock import MockDetectTool
from sensoragent.workflows import ActionListRuntime, build_mock_pick_place_actionlist
from sensoragent.workflows import DecisionTreeRuntime
from sensoragent.agent.llm_planner import LLMPlanner


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


def _build_audio_client(config: SensorAgentConfig):
  audio_config = config.integrations.audio
  backend = str(audio_config.get("backend", "fake"))
  if backend == "fake":
    return FakeAudioClient()
  if backend == "local":
    return LocalAudioClient(
      asr_model_dir=str(audio_config.get("asr_model_dir", "models/asr/sense-voice")),
      tts_model_dir=str(audio_config.get("tts_model_dir", "models/tts")),
      asr_provider=str(audio_config.get("asr_provider", "cpu")),
      asr_num_threads=int(audio_config.get("asr_num_threads", 4)),
    )
  raise ValueError(f"Unknown audio backend: {backend}")


def _build_microphone_recorder(config: SensorAgentConfig):
  microphone_config = config.integrations.microphone
  backend = str(microphone_config.get("backend", "fake"))
  if backend == "fake":
    return FakeMicrophoneRecorder(
      str(microphone_config.get("fixture_path", "tests/fixtures/audio/command.wav"))
    )
  if backend == "sounddevice":
    return SoundDeviceRecorder()
  raise ValueError(f"Unknown microphone backend: {backend}")


def _build_tool(tool_name: str, config: SensorAgentConfig):
  if tool_name in AVAILABLE_TOOLS:
    return AVAILABLE_TOOLS[tool_name]()
  if tool_name in {"audio.listen_transcribe", "audio.transcribe", "audio.speak"}:
    client = _build_audio_client(config)
    if tool_name == "audio.listen_transcribe":
      return AudioListenTranscribeTool(_build_microphone_recorder(config), client)
    if tool_name == "audio.transcribe":
      return AudioTranscribeTool(client)
    return AudioSpeakTool(client)
  raise KeyError(f"Configured tool is not available: {tool_name}")


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
  decision_tree_runtime: DecisionTreeRuntime
  decision_trees: dict[str, object]
  task_store: InMemoryTaskStore
  event_stream: InMemoryEventStream


def build_agent(
  config: SensorAgentConfig,
  log_path: Path | None = None,
  *,
  planner_mode: str = "static",
) -> AgentBundle:
  """Build SensorAgent runtime objects from a loaded config."""

  logger = TaskLogger(log_path)

  tool_registry = ToolRegistry()
  for tool_name in config.tools.enabled:
    try:
      tool_registry.register(_build_tool(tool_name, config))
    except KeyError as exc:
      raise KeyError(f"Configured tool is not available: {tool_name}") from exc

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
  decision_tree_runtime = DecisionTreeRuntime(
    tool_runtime,
    skill_runtime,
    actionlist_runtime,
    actionlists,
    logger,
  )
  decision_trees: dict[str, object] = {}
  task_store = InMemoryTaskStore()
  event_stream = InMemoryEventStream()
  planner = None
  if planner_mode == "llm":
    planner = LLMPlanner(OpenAICompatibleClient(load_llm_config_from_env()))
  elif planner_mode != "static":
    raise ValueError(f"Unknown planner mode: {planner_mode}")
  agent = AgentRuntime(
    skill_runtime,
    logger,
    actionlist_runtime=actionlist_runtime,
    actionlists=actionlists,
    decision_tree_runtime=decision_tree_runtime,
    decision_trees=decision_trees,
    task_store=task_store,
    event_stream=event_stream,
    planner=planner,
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
    decision_tree_runtime=decision_tree_runtime,
    decision_trees=decision_trees,
    task_store=task_store,
    event_stream=event_stream,
  )


def build_agent_from_config(
  path: str | Path,
  log_path: Path | None = None,
  *,
  planner_mode: str = "static",
) -> AgentBundle:
  """Load a YAML config and build SensorAgent runtime objects."""

  return build_agent(load_config(path), log_path=log_path, planner_mode=planner_mode)


def build_agent_from_env(
  explicit_path: str | Path | None = None,
  *,
  log_path: Path | None = None,
  planner_mode: str = "static",
) -> AgentBundle:
  """Resolve configuration from arguments/environment and build SensorAgent."""

  return build_agent_from_config(
    resolve_config_path(explicit_path),
    log_path=log_path,
    planner_mode=planner_mode,
  )
