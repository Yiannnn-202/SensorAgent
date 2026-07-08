"""In-memory Agent event stream."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from sensoragent.schemas import TraceContext
from sensoragent.schemas.core import utc_now_iso


@dataclass(frozen=True)
class AgentEvent:
  """Event emitted by Agent task orchestration."""

  event: str
  task_id: str
  trace_id: str
  timestamp: str = field(default_factory=utc_now_iso)
  payload: dict = field(default_factory=dict)

  def to_dict(self) -> dict:
    return asdict(self)


class InMemoryEventStream:
  """Stores Agent events for tests and future WebSocket streaming."""

  def __init__(self) -> None:
    self._events: list[AgentEvent] = []

  def publish(self, event: str, trace: TraceContext, payload: dict | None = None) -> None:
    self._events.append(
      AgentEvent(
        event=event,
        task_id=trace.task_id,
        trace_id=trace.trace_id,
        payload=payload or {},
      )
    )

  def events(self) -> list[AgentEvent]:
    return list(self._events)
