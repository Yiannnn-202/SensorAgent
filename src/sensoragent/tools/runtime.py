"""Tool invocation runtime."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from typing import TYPE_CHECKING

from sensoragent.logger import TaskLogger
from sensoragent.schemas import ToolCall, ToolResult, TraceContext
from sensoragent.tools.base import ToolRegistry
from sensoragent.tools.errors import ToolError, ToolExecutionError, ToolTimeoutError

if TYPE_CHECKING:
  from sensoragent.contracts import ContractValidator


class ToolRuntime:
  """Invokes registered tools with structured logging."""

  def __init__(
    self,
    registry: ToolRegistry,
    logger: TaskLogger,
    contract_validator: ContractValidator | None = None,
  ) -> None:
    self._registry = registry
    self._logger = logger
    self._contract_validator = contract_validator

  def _run_with_timeout(
    self,
    tool,
    call: ToolCall,
    timeout_seconds: float | None,
  ) -> ToolResult:
    if timeout_seconds is None or timeout_seconds <= 0:
      return tool.run(call)

    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(tool.run, call)
    try:
      return future.result(timeout=timeout_seconds)
    except FutureTimeoutError as exc:
      future.cancel()
      raise ToolTimeoutError(
        f"Tool timed out after {timeout_seconds}s: {call.tool}"
      ) from exc
    finally:
      executor.shutdown(wait=False, cancel_futures=True)

  def invoke(self, tool_name: str, input_data: dict, trace: TraceContext) -> ToolResult:
    self._logger.log(
      "tool_call_started",
      trace,
      {"tool": tool_name, "input": input_data},
    )
    try:
      if self._contract_validator is not None:
        self._contract_validator.validate_tool_input(tool_name, input_data)
      tool = self._registry.get(tool_name)
      call = ToolCall(tool=tool_name, input=input_data, trace=trace)
      max_retries = max(0, tool.spec.max_retries)
      timeout_seconds = tool.spec.timeout_seconds
      last_error: ToolExecutionError | ToolTimeoutError | None = None
      for attempt in range(max_retries + 1):
        try:
          result = self._run_with_timeout(tool, call, timeout_seconds)
          break
        except ToolTimeoutError as exc:
          last_error = exc
          self._logger.log(
            "tool_call_attempt_failed",
            trace,
            {
              "tool": tool_name,
              "attempt": attempt + 1,
              "max_retries": max_retries,
              "error": str(exc),
            },
          )
        except Exception as exc:
          last_error = ToolExecutionError(f"Tool execution failed for {tool_name}: {exc}")
          self._logger.log(
            "tool_call_attempt_failed",
            trace,
            {
              "tool": tool_name,
              "attempt": attempt + 1,
              "max_retries": max_retries,
              "error": str(last_error),
            },
          )
      else:
        if last_error is None:
          last_error = ToolExecutionError(f"Tool execution failed for {tool_name}")
        raise last_error
      if result.success and self._contract_validator is not None:
        self._contract_validator.validate_tool_output(tool_name, result.output)
    except ToolError as exc:
      result = ToolResult(tool=tool_name, success=False, error=str(exc))
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
