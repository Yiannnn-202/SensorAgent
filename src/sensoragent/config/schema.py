"""Configuration schemas for SensorAgent."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class AgentConfig:
  """Agent runtime configuration."""

  name: str = "sensoragent"
  mode: str = "mock"
  default_skill: str | None = None


@dataclass(frozen=True)
class ToolsConfig:
  """Enabled tool configuration."""

  enabled: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SkillsConfig:
  """Enabled skill configuration."""

  enabled: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class LoggingConfig:
  """Logging configuration."""

  level: str = "info"
  console: bool = True
  app_log: Path = Path("logs/app.log")
  task_dir: Path = Path("logs/tasks")
  trace_dir: Path = Path("logs/traces")
  error_dir: Path = Path("logs/errors")
  progress_dir: Path = Path("logs/runs")


@dataclass(frozen=True)
class SensorAgentIntegrationsConfig:
  """External/local integration configuration."""

  audio: dict = field(default_factory=dict)
  microphone: dict = field(default_factory=dict)
  robot: dict = field(default_factory=dict)
  vision: dict = field(default_factory=dict)


@dataclass(frozen=True)
class SceneConfig:
  """Static scene catalog used by config-driven detection and place targets."""

  objects: dict = field(default_factory=dict)
  object_ontology: dict = field(default_factory=dict)
  release_profiles: dict = field(default_factory=dict)
  place_targets: dict = field(default_factory=dict)
  robot_joint_order: list[str] = field(default_factory=list)
  joint_poses: dict = field(default_factory=dict)
  workspace: dict = field(default_factory=dict)


@dataclass(frozen=True)
class SensorAgentConfig:
  """Top-level SensorAgent configuration."""

  agent: AgentConfig = field(default_factory=AgentConfig)
  tools: ToolsConfig = field(default_factory=ToolsConfig)
  skills: SkillsConfig = field(default_factory=SkillsConfig)
  logging: LoggingConfig = field(default_factory=LoggingConfig)
  integrations: SensorAgentIntegrationsConfig = field(
    default_factory=SensorAgentIntegrationsConfig
  )
  scene: SceneConfig = field(default_factory=SceneConfig)
