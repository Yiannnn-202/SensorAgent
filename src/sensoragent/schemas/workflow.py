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


class DecisionNodeKind(StrEnum):
  """Supported decision tree node kinds."""

  TOOL = "tool"
  SKILL = "skill"
  ACTIONLIST = "actionlist"
  CONDITION = "condition"
  TERMINAL = "terminal"


class ConditionOperator(StrEnum):
  """Supported condition operators."""

  EXISTS = "exists"
  EQUALS = "equals"
  TRUTHY = "truthy"


@dataclass(frozen=True)
class DecisionCondition:
  """Condition evaluated against decision tree context."""

  path: str
  operator: ConditionOperator
  value: object | None = None


@dataclass(frozen=True)
class DecisionNode:
  """One executable or branching node inside a DecisionTree."""

  name: str
  kind: DecisionNodeKind
  target: str | None = None
  input: dict = field(default_factory=dict)
  condition: DecisionCondition | None = None
  save_as: str | None = None
  on_success: str | None = None
  on_failure: str | None = None
  max_retries: int = 0
  terminal_success: bool | None = None
  description: str = ""


@dataclass(frozen=True)
class DecisionTree:
  """Branching workflow made of decision nodes."""

  name: str
  start: str
  nodes: list[DecisionNode]
  description: str = ""
  version: str = "0.1.0"
  inputs: dict[str, str] = field(default_factory=dict)
  tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class DecisionNodeResult:
  """Execution result for a single DecisionNode."""

  node: str
  success: bool
  attempts: int = 1
  output: dict | None = None
  error: str | None = None


@dataclass(frozen=True)
class DecisionTreeResult:
  """Execution result for a DecisionTree."""

  decision_tree: str
  success: bool
  nodes: list[DecisionNodeResult]
  output: dict | None = None
  error: str | None = None
