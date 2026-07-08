"""Planning schemas for Agent task orchestration."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum


class PlanTargetKind(StrEnum):
  """Supported Agent plan target kinds."""

  SKILL = "skill"
  ACTIONLIST = "actionlist"
  DECISION_TREE = "decision_tree"


@dataclass(frozen=True)
class AgentPlan:
  """Structured plan produced by a planner before execution."""

  target_kind: PlanTargetKind
  target: str
  input: dict = field(default_factory=dict)
  reason: str = ""

  def to_dict(self) -> dict:
    return asdict(self)
