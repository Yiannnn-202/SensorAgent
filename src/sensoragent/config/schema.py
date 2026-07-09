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


@dataclass(frozen=True)
class SensorAgentIntegrationsConfig:
  """External/local integration configuration."""

  audio: dict = field(default_factory=dict)
  microphone: dict = field(default_factory=dict)


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
