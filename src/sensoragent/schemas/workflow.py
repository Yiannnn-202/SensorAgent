"""Workflow schemas for ActionList execution."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum


class ActionStepKind(StrEnum):
  """Supported action step target kinds."""

  TOOL = "tool"
  SKILL = "skill"


@dataclass(frozen=True)
class ActionStep:
  """One executable step inside an ActionList."""

  name: str
  kind: ActionStepKind
  target: str
  input: dict = field(default_factory=dict)
  save_as: str | None = None
  stop_on_failure: bool = True
  description: str = ""

  def to_dict(self) -> dict:
    return asdict(self)


@dataclass(frozen=True)
class ActionList:
  """Ordered workflow made of executable action steps."""

  name: str
  steps: list[ActionStep]
  description: str = ""
  version: str = "0.1.0"
  inputs: dict[str, str] = field(default_factory=dict)
  tags: tuple[str, ...] = ()

  def to_dict(self) -> dict:
    return asdict(self)


@dataclass(frozen=True)
class ActionStepResult:
  """Execution result for a single ActionStep."""

  step: str
  success: bool
  output: dict | None = None
  error: str | None = None


@dataclass(frozen=True)
class ActionListResult:
  """Execution result for an ActionList."""

  actionlist: str
  success: bool
  steps: list[ActionStepResult]
  output: dict | None = None
  error: str | None = None
