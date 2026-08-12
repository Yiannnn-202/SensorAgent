"""YAML configuration loader for SensorAgent."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from sensoragent.config.schema import (
  AgentConfig,
  LoggingConfig,
  SceneConfig,
  SensorAgentIntegrationsConfig,
  SensorAgentConfig,
  SkillsConfig,
  ToolsConfig,
)


def _as_mapping(value: Any, section: str) -> dict:
  if value is None:
    return {}
  if not isinstance(value, dict):
    raise ValueError(f"Config section '{section}' must be a mapping")
  return value


def _as_string_list(value: Any, section: str) -> list[str]:
  if value is None:
    return []
  if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
    raise ValueError(f"Config section '{section}' must be a list of strings")
  return value


def load_config(path: str | Path) -> SensorAgentConfig:
  """Load a SensorAgent YAML config file."""

  config_path = Path(path)
  raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
  if not isinstance(raw, dict):
    raise ValueError("Top-level config must be a mapping")

  agent = _as_mapping(raw.get("agent"), "agent")
  tools = _as_mapping(raw.get("tools"), "tools")
  skills = _as_mapping(raw.get("skills"), "skills")
  logging = _as_mapping(raw.get("logging"), "logging")
  integrations = _as_mapping(raw.get("integrations"), "integrations")
  scene = _as_mapping(raw.get("scene"), "scene")

  return SensorAgentConfig(
    agent=AgentConfig(
      name=str(agent.get("name", "sensoragent")),
      mode=str(agent.get("mode", "mock")),
      default_skill=(
        str(agent["default_skill"]) if agent.get("default_skill") is not None else None
      ),
    ),
    tools=ToolsConfig(enabled=_as_string_list(tools.get("enabled"), "tools.enabled")),
    skills=SkillsConfig(enabled=_as_string_list(skills.get("enabled"), "skills.enabled")),
    logging=LoggingConfig(
      level=str(logging.get("level", "info")),
      console=bool(logging.get("console", True)),
      app_log=Path(str(logging.get("app_log", "logs/app.log"))),
      task_dir=Path(str(logging.get("task_dir", "logs/tasks"))),
      trace_dir=Path(str(logging.get("trace_dir", "logs/traces"))),
      error_dir=Path(str(logging.get("error_dir", "logs/errors"))),
      progress_dir=Path(str(logging.get("progress_dir", "logs/runs"))),
    ),
    integrations=SensorAgentIntegrationsConfig(
      audio=_as_mapping(integrations.get("audio"), "integrations.audio"),
      microphone=_as_mapping(
        integrations.get("microphone"),
        "integrations.microphone",
      ),
      robot=_as_mapping(integrations.get("robot"), "integrations.robot"),
      vision=_as_mapping(integrations.get("vision"), "integrations.vision"),
    ),
    scene=SceneConfig(
      objects=_as_mapping(scene.get("objects"), "scene.objects"),
      object_ontology=_as_mapping(
        scene.get("object_ontology"),
        "scene.object_ontology",
      ),
      release_profiles=_as_mapping(scene.get("release_profiles"), "scene.release_profiles"),
      place_targets=_as_mapping(scene.get("place_targets"), "scene.place_targets"),
      robot_joint_order=_as_string_list(
        scene.get("robot_joint_order"),
        "scene.robot_joint_order",
      ),
      joint_poses=_as_mapping(scene.get("joint_poses"), "scene.joint_poses"),
      workspace=_as_mapping(scene.get("workspace"), "scene.workspace"),
    ),
  )
