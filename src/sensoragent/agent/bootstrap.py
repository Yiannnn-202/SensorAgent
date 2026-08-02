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
  SileroVadSegmenter,
  SoundDeviceVadRecorder,
  SoundDeviceRecorder,
  load_llm_config_from_env,
)
from sensoragent.integrations.robot import FakeRobotControlClient, HttpRobotControlClient
from sensoragent.logger import TaskLogger
from sensoragent.skills import SkillRegistry, SkillRuntime
from sensoragent.skills.audio import AudioAnnounceSkill, AudioListenCommandSkill
from sensoragent.skills.mock import MockPickAndPlaceSkill
from sensoragent.skills.robot import (
  RobotPickSkill,
  RobotPlaceSkill,
  RobotVerifyGraspSkill,
  RobotVerifyPlaceSkill,
)
from sensoragent.state import InMemoryEventStream, InMemoryTaskStore
from sensoragent.tools import ToolRegistry, ToolRuntime
from sensoragent.tools.audio.mock import MockTranscribeTool
from sensoragent.tools.audio import (
  AudioListenTranscribeTool,
  AudioListenVadTranscribeTool,
  AudioSpeakTool,
  AudioTranscribeTool,
)
from sensoragent.tools.robot.mock import MockPickTool, MockPlaceTool
from sensoragent.tools.robot import (
  GripperCloseTool,
  GripperGetStateTool,
  GripperOpenTool,
  RobotGetStateTool,
  RobotMoveJointsTool,
  RobotMoveLinearTool,
  RobotMovePoseTool,
  RobotPlanOrientedPickTool,
  RobotPlanPlaceTool,
  RobotPlanTopDownPickTool,
  RobotResolvePlaceTargetTool,
  RobotStopTool,
  default_place_target_registry,
)
from sensoragent.tools.recovery import RecoveryClassifyFailureTool, RecoveryPlanTool
from sensoragent.tools.vision import (
  VisionConfigDetectTool,
  VisionGroundedSam2Tool,
  VisionOpenVocabularyDetectTool,
)
from sensoragent.tools.vision import VisionCaptureFrameTool
from sensoragent.tools.vision import VisionVerifyObjectInBinTool, VisionVerifyObjectLiftedTool
from sensoragent.tools.vision.mock import MockDetectTool
from sensoragent.workflows import (
  ActionListRuntime,
  build_industrial_recovery_pick_place_tree,
  build_industrial_pick_only_actionlist,
  build_industrial_pick_place_actionlist,
  build_industrial_place_only_actionlist,
  build_industrial_vision_pick_place_actionlist,
  build_mock_pick_place_actionlist,
  build_voice_command_ack_actionlist,
)
from sensoragent.workflows import DecisionTreeRuntime
from sensoragent.agent.llm_planner import LLMPlanner


ToolFactory = Callable[[], object]
SkillFactory = Callable[[], object]


AVAILABLE_TOOLS: dict[str, ToolFactory] = {
  "vision.mock_detect": MockDetectTool,
  "audio.mock_transcribe": MockTranscribeTool,
  "robot.mock_pick": MockPickTool,
  "robot.mock_place": MockPlaceTool,
  "robot.plan_oriented_pick": RobotPlanOrientedPickTool,
  "robot.plan_place": RobotPlanPlaceTool,
  "robot.plan_top_down_pick": RobotPlanTopDownPickTool,
  "recovery.classify_failure": RecoveryClassifyFailureTool,
  "recovery.plan": RecoveryPlanTool,
  "vision.verify_object_lifted": VisionVerifyObjectLiftedTool,
}


SCENE_TOOL_NAMES = {
  "vision.config_detect",
  "vision.grounded_sam2",
  "vision.open_vocab_detect",
  "vision.capture_frame",
  "vision.verify_object_in_bin",
  "robot.resolve_place_target",
}


def _build_recovery_tree(config: SensorAgentConfig):
  """Build the recovery tree in mock or perception-driven mode."""

  vision_config = config.integrations.vision
  if not bool(vision_config.get("recovery_live_detect", False)):
    return build_industrial_recovery_pick_place_tree(
      joint_poses=config.scene.joint_poses,
    )
  enabled_tools = set(config.tools.enabled or ())
  capture_tool = "vision.capture_frame" if "vision.capture_frame" in enabled_tools else None
  return build_industrial_recovery_pick_place_tree(
    joint_poses=config.scene.joint_poses,
    detect_tool="vision.open_vocab_detect",
    capture_tool=capture_tool,
    live_verify=capture_tool is not None,
    spatial_constraint_input=True,
  )


def _build_scene_tool(tool_name: str, config: SensorAgentConfig):
  if tool_name == "vision.config_detect":
    catalog = config.scene.objects or {}
    return VisionConfigDetectTool(catalog)
  if tool_name in {"vision.grounded_sam2", "vision.open_vocab_detect"}:
    vision_config = config.integrations.vision
    common_settings = dict(
      model_path=str(vision_config.get("model_path", "models/vision/yoloe.pt")),
      grounding_dino_model=vision_config.get("grounding_dino_model"),
      sam2_model_path=vision_config.get("sam2_model_path"),
      camera_info_path=vision_config.get("camera_info_path"),
      camera_info=vision_config.get("camera_info"),
      t_base_camera=vision_config.get("T_base_camera"),
      position_base_offset=vision_config.get("position_base_offset"),
      depth_window=int(vision_config.get("depth_window", 7)),
      depth_scale=float(vision_config.get("depth_scale", 1.0)),
      box_threshold=float(vision_config.get("box_threshold", 0.35)),
      text_threshold=float(vision_config.get("text_threshold", 0.25)),
      device=vision_config.get("device"),
      camera_frame=str(
        vision_config.get("camera_frame", "camera_color_optical_frame")
      ),
      base_frame=str(vision_config.get("base_frame", "base_link")),
      workspace=dict(config.scene.workspace or {}),
    )
    if tool_name == "vision.grounded_sam2":
      return VisionGroundedSam2Tool(**common_settings)
    return VisionOpenVocabularyDetectTool(
      backend=str(vision_config.get("backend", "yoloe")),
      refine_masks=vision_config.get("refine_masks"),
      require_masks=bool(vision_config.get("require_masks", False)),
      red_color_shortcut=bool(vision_config.get("red_color_shortcut", False)),
      **common_settings,
    )
  if tool_name == "vision.capture_frame":
    vision_config = config.integrations.vision
    capture_config = dict(vision_config.get("capture") or {})
    return VisionCaptureFrameTool(
      script=str(capture_config.get("script", "scripts/linux/capture_gazebo_rgbd_frame.py")),
      ros_python=capture_config.get("ros_python"),
      ros_setup=capture_config.get("ros_setup"),
      image_topic=str(capture_config.get("image_topic", "/industrial_camera/image")),
      depth_topic=str(capture_config.get("depth_topic", "/industrial_camera/depth_image")),
      camera_info_topic=str(
        capture_config.get("camera_info_topic", "/industrial_camera/camera_info")
      ),
      base_frame=str(capture_config.get("base_frame", "base_link")),
      world_frame=str(capture_config.get("world_frame", "world")),
      out_dir=str(capture_config.get("out_dir", "logs/vision/latest")),
      timeout_seconds=float(capture_config.get("timeout_seconds", 10.0)),
      fallback_t_base_camera=vision_config.get("T_base_camera"),
      fallback_t_world_camera=vision_config.get("T_world_camera"),
    )
  if tool_name == "robot.resolve_place_target":
    targets = config.scene.place_targets or default_place_target_registry()
    return RobotResolvePlaceTargetTool(targets)
  if tool_name == "vision.verify_object_in_bin":
    targets = config.scene.place_targets or default_place_target_registry()
    return VisionVerifyObjectInBinTool(targets)
  raise KeyError(f"Not a scene tool: {tool_name}")

AVAILABLE_SKILLS: dict[str, SkillFactory] = {
  "audio.announce": AudioAnnounceSkill,
  "audio.listen_command": AudioListenCommandSkill,
  "mock.pick_and_place": MockPickAndPlaceSkill,
  "robot.pick": RobotPickSkill,
  "robot.place": RobotPlaceSkill,
  "robot.verify_grasp": RobotVerifyGraspSkill,
  "robot.verify_place": RobotVerifyPlaceSkill,
}

ROBOT_TOOL_FACTORIES = {
  "robot.get_state": RobotGetStateTool,
  "robot.move_joints": RobotMoveJointsTool,
  "robot.move_pose": RobotMovePoseTool,
  "robot.move_linear": RobotMoveLinearTool,
  "robot.stop": RobotStopTool,
  "gripper.open": GripperOpenTool,
  "gripper.close": GripperCloseTool,
  "gripper.get_state": GripperGetStateTool,
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
  if backend == "sounddevice_vad":
    audio_config = config.integrations.audio
    return SoundDeviceVadRecorder(
      model_path=str(audio_config.get("vad_model_path", "models/asr/vad/silero_vad.onnx")),
      threshold=float(audio_config.get("vad_threshold", 0.35)),
      min_rms=float(audio_config.get("vad_min_rms", 0.025)),
      min_speech_windows=int(audio_config.get("vad_min_speech_windows", 2)),
      pre_roll_ms=int(audio_config.get("vad_pre_roll_ms", 120)),
      post_roll_ms=int(audio_config.get("vad_post_roll_ms", 1800)),
      tail_padding_ms=int(audio_config.get("vad_tail_padding_ms", 700)),
      max_utterance_sec=float(audio_config.get("vad_max_utterance_sec", 15.0)),
    )
  raise ValueError(f"Unknown microphone backend: {backend}")


def _build_vad_segmenter(config: SensorAgentConfig):
  audio_config = config.integrations.audio
  model_path = audio_config.get("vad_model_path")
  if not model_path:
    return None
  return SileroVadSegmenter(
    model_path=str(model_path),
    threshold=float(audio_config.get("vad_threshold", 0.35)),
    min_speech_windows=int(audio_config.get("vad_min_speech_windows", 2)),
    pre_roll_ms=int(audio_config.get("vad_pre_roll_ms", 120)),
    post_roll_ms=int(audio_config.get("vad_post_roll_ms", 1800)),
    max_utterance_sec=float(audio_config.get("vad_max_utterance_sec", 15.0)),
  )


def _build_robot_client(config: SensorAgentConfig):
  robot_config = config.integrations.robot
  backend = str(robot_config.get("backend", "fake"))
  if backend == "fake":
    return FakeRobotControlClient(
      dof=int(robot_config.get("dof", 6)),
      maximum_opening=float(robot_config.get("maximum_opening", 0.0848)),
    )
  if backend == "http":
    return HttpRobotControlClient(
      endpoint=str(robot_config.get("endpoint", "http://127.0.0.1:8765")),
      timeout_seconds=float(robot_config.get("timeout_seconds", 120.0)),
    )
  raise ValueError(f"Unknown robot backend: {backend}")


def _build_tool(tool_name: str, config: SensorAgentConfig, robot_client=None):
  if tool_name in SCENE_TOOL_NAMES:
    return _build_scene_tool(tool_name, config)
  if tool_name in AVAILABLE_TOOLS:
    return AVAILABLE_TOOLS[tool_name]()
  if tool_name in ROBOT_TOOL_FACTORIES:
    if robot_client is None:
      raise ValueError("Robot client is required for robot control tools")
    return ROBOT_TOOL_FACTORIES[tool_name](robot_client)
  if tool_name in {
    "audio.listen_transcribe",
    "audio.listen_vad_transcribe",
    "audio.transcribe",
    "audio.speak",
  }:
    client = _build_audio_client(config)
    if tool_name == "audio.listen_transcribe":
      return AudioListenTranscribeTool(_build_microphone_recorder(config), client)
    if tool_name == "audio.listen_vad_transcribe":
      return AudioListenVadTranscribeTool(
        _build_microphone_recorder(config),
        client,
        _build_vad_segmenter(config),
      )
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

  # Derive a human-readable progress log that pairs by filename with the
  # structured JSONL (e.g. logs/tasks/run.jsonl <-> logs/runs/run.log). Mirrors
  # the JSONL gating: no log_path means neither file is written.
  progress_path: Path | None = None
  if log_path is not None:
    progress_path = config.logging.progress_dir / f"{log_path.stem}.log"
  logger = TaskLogger(log_path, console=config.logging.console, progress_path=progress_path)

  tool_registry = ToolRegistry()
  robot_client = None
  if any(tool_name in ROBOT_TOOL_FACTORIES for tool_name in config.tools.enabled):
    robot_client = _build_robot_client(config)
  for tool_name in config.tools.enabled:
    try:
      tool_registry.register(_build_tool(tool_name, config, robot_client))
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
  joint_poses = config.scene.joint_poses
  actionlists = {
    "mock.pick_place_actionlist": build_mock_pick_place_actionlist(),
    "audio.voice_command_ack_actionlist": build_voice_command_ack_actionlist(),
    "industrial.pick_place_actionlist": build_industrial_pick_place_actionlist(joint_poses),
    "industrial.pick_only_actionlist": build_industrial_pick_only_actionlist(joint_poses),
    "industrial.place_only_actionlist": build_industrial_place_only_actionlist(joint_poses),
    "industrial.vision_pick_place_actionlist": build_industrial_vision_pick_place_actionlist(joint_poses),
  }
  decision_tree_runtime = DecisionTreeRuntime(
    tool_runtime,
    skill_runtime,
    actionlist_runtime,
    actionlists,
    logger,
  )
  decision_trees: dict[str, object] = {
    "industrial.recovery_pick_place_tree": _build_recovery_tree(config),
  }
  task_store = InMemoryTaskStore()
  event_stream = InMemoryEventStream()
  planner = None
  if planner_mode == "llm":
    place_targets = tuple(
      (config.scene.place_targets or default_place_target_registry()).keys()
    )
    planner = LLMPlanner(
      OpenAICompatibleClient(load_llm_config_from_env()),
      # DecisionTree targets are dispatched separately by target_kind but share
      # the same LLM whitelist to prevent arbitrary workflow selection.
      allowed_targets=tuple(actionlists.keys()) + tuple(decision_trees.keys()),
      allowed_place_targets=place_targets,
    )
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
