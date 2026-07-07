"""Tool protocol and registry."""

from __future__ import annotations

from typing import Protocol

from sensoragent.schemas import ToolCall, ToolResult, ToolSpec


class Tool(Protocol):
  """Smallest callable capability exposed to SensorAgent."""

  spec: ToolSpec

  def run(self, call: ToolCall) -> ToolResult:
    """Run the tool."""


class ToolRegistry:
  """In-memory tool registry."""

  def __init__(self) -> None:
    self._tools: dict[str, Tool] = {}

  def register(self, tool: Tool) -> None:
    if tool.spec.name in self._tools:
      raise ValueError(f"Tool already registered: {tool.spec.name}")
    self._tools[tool.spec.name] = tool

  def get(self, name: str) -> Tool:
    try:
      return self._tools[name]
    except KeyError as exc:
      raise KeyError(f"Unknown tool: {name}") from exc

  def names(self) -> list[str]:
    return sorted(self._tools)
