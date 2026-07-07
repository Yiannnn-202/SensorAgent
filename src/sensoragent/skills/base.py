"""Skill protocol and registry."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from sensoragent.logger import TaskLogger
from sensoragent.schemas import SkillCall, SkillResult, SkillSpec
from sensoragent.tools import ToolRuntime


@dataclass(frozen=True)
class SkillContext:
  """Runtime dependencies available to a skill."""

  tool_runtime: ToolRuntime
  logger: TaskLogger


class Skill(Protocol):
  """Composable high-level capability."""

  spec: SkillSpec

  def run(self, call: SkillCall, context: SkillContext) -> SkillResult:
    """Run the skill."""


class SkillRegistry:
  """In-memory skill registry."""

  def __init__(self) -> None:
    self._skills: dict[str, Skill] = {}

  def register(self, skill: Skill) -> None:
    if skill.spec.name in self._skills:
      raise ValueError(f"Skill already registered: {skill.spec.name}")
    self._skills[skill.spec.name] = skill

  def get(self, name: str) -> Skill:
    try:
      return self._skills[name]
    except KeyError as exc:
      raise KeyError(f"Unknown skill: {name}") from exc

  def names(self) -> list[str]:
    return sorted(self._skills)
