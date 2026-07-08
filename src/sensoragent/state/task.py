"""Task state models for Agent orchestration."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum

from sensoragent.schemas import AgentPlan, TraceContext
from sensoragent.schemas.core import utc_now_iso


class TaskStatus(StrEnum):
  """Task lifecycle states."""

  PENDING = "pending"
  RUNNING = "running"
  SUCCEEDED = "succeeded"
  FAILED = "failed"
  CANCELLED = "cancelled"


@dataclass
class TaskState:
  """Mutable state for one Agent task."""

  task_id: str
  user_input: str
  trace: TraceContext
  status: TaskStatus = TaskStatus.PENDING
  input: dict = field(default_factory=dict)
  plan: AgentPlan | None = None
  result: dict | None = None
  error: str | None = None
  created_at: str = field(default_factory=utc_now_iso)
  updated_at: str = field(default_factory=utc_now_iso)

  def mark(self, status: TaskStatus, *, error: str | None = None) -> None:
    self.status = status
    self.error = error
    self.updated_at = utc_now_iso()

  def to_dict(self) -> dict:
    return asdict(self)
