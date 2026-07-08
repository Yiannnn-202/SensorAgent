"""Tool invocation runtime."""

from __future__ import annotations

from sensoragent.logger import TaskLogger
from sensoragent.schemas import ToolCall, ToolResult, TraceContext
from sensoragent.tools.base import ToolRegistry
from sensoragent.tools.errors import ToolError, ToolExecutionError


class ToolRuntime:
  """Invokes registered tools with structured logging."""

  def __init__(self, registry: ToolRegistry, logger: TaskLogger) -> None:
    self._registry = registry
    self._logger = logger

  def invoke(self, tool_name: str, input_data: dict, trace: TraceContext) -> ToolResult:
    self._logger.log(
      "tool_call_started",
      trace,
      {"tool": tool_name, "input": input_data},
    )
    try:
      tool = self._registry.get(tool_name)
      result = tool.run(ToolCall(tool=tool_name, input=input_data, trace=trace))
    except ToolError as exc:
      result = ToolResult(tool=tool_name, success=False, error=str(exc))
    except Exception as exc:
      wrapped = ToolExecutionError(f"Tool execution failed for {tool_name}: {exc}")
      result = ToolResult(tool=tool_name, success=False, error=str(wrapped))
    self._logger.log(
      "tool_call_finished",
      trace,
      {
        "tool": tool_name,
        "success": result.success,
        "output": result.output,
        "error": result.error,
      },
    )
    return result
