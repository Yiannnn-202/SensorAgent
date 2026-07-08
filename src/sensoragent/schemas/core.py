"""Core schemas for the minimal SensorAgent call chain."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from uuid import uuid4


def utc_now_iso() -> str:
  """Return an ISO-8601 UTC timestamp."""

  return datetime.now(UTC).isoformat()


@dataclass(frozen=True)
class TraceContext:
  """Correlation context shared by an Agent task, skill calls, and tool calls."""

  task_id: str = field(default_factory=lambda: f"task_{uuid4().hex}")
  trace_id: str = field(default_factory=lambda: f"trace_{uuid4().hex}")

  def to_dict(self) -> dict[str, str]:
    return asdict(self)


@dataclass(frozen=True)
class AgentRequest:
  """Request entering SensorAgent from an API/MCP-shaped entry point."""

  input: dict
  skill: str | None = None
  actionlist: str | None = None
  decision_tree: str | None = None
  trace: TraceContext = field(default_factory=TraceContext)


@dataclass(frozen=True)
class AgentResponse:
  """Response returned by SensorAgent after skill execution."""

  success: bool
  result: dict | None
  error: str | None
  trace: TraceContext

  def to_dict(self) -> dict:
    return asdict(self)


@dataclass(frozen=True)
class ToolSpec:
  """Static metadata for a callable tool."""

  name: str
  description: str
  version: str = "0.1.0"
  tags: tuple[str, ...] = ()
  enabled: bool = True
  timeout_seconds: float | None = None
  max_retries: int = 0


@dataclass(frozen=True)
class ToolCall:
  """Concrete tool invocation."""

  tool: str
  input: dict
  trace: TraceContext


@dataclass(frozen=True)
class ToolResult:
  """Concrete tool invocation result."""

  tool: str
  success: bool
  output: dict | None = None
  error: str | None = None


@dataclass(frozen=True)
class SkillSpec:
  """Static metadata for a callable skill."""

  name: str
  description: str
  version: str = "0.1.0"
  tags: tuple[str, ...] = ()
  enabled: bool = True


@dataclass(frozen=True)
class SkillCall:
  """Concrete skill invocation."""

  skill: str
  input: dict
  trace: TraceContext


@dataclass(frozen=True)
class SkillResult:
  """Concrete skill invocation result."""

  skill: str
  success: bool
  output: dict | None = None
  error: str | None = None


@dataclass(frozen=True)
class LogRecord:
  """Structured event record emitted by SensorAgent runtimes."""

  event: str
  task_id: str
  trace_id: str
  timestamp: str = field(default_factory=utc_now_iso)
  payload: dict = field(default_factory=dict)

  def to_dict(self) -> dict:
    return asdict(self)
