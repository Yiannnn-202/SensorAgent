"""Unit tests for ToolRuntime contract validation hooks."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest import TestCase

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
  sys.path.insert(0, str(SRC))

from sensoragent.contracts import ContractValidator
from sensoragent.logger import TaskLogger
from sensoragent.schemas import ToolCall, ToolResult, ToolSpec, TraceContext
from sensoragent.tools import ToolRegistry, ToolRuntime
from sensoragent.tools.vision.mock import MockDetectTool


class ToolRuntimeValidationTest(TestCase):
  def test_tool_runtime_rejects_invalid_input_before_invocation(self) -> None:
    registry = ToolRegistry()
    registry.register(MockDetectTool())
    logger = TaskLogger()
    runtime = ToolRuntime(registry, logger, ContractValidator(ROOT / "contracts"))

    result = runtime.invoke("vision.mock_detect", {}, TraceContext())

    self.assertFalse(result.success)
    self.assertIn("$.query is required", result.error or "")
    called_events = list(logger.events())
    self.assertIn("tool_call_started", called_events)
    self.assertIn("tool_call_finished", called_events)

  def test_tool_runtime_rejects_invalid_success_output_after_invocation(self) -> None:
    class BadOutputTool:
      spec = ToolSpec(name="vision.mock_detect", description="Bad output tool")

      def run(self, call: ToolCall) -> ToolResult:
        return ToolResult(
          tool=self.spec.name,
          success=True,
          output={"found": True},
        )

    registry = ToolRegistry()
    registry.register(BadOutputTool())
    logger = TaskLogger()
    runtime = ToolRuntime(registry, logger, ContractValidator(ROOT / "contracts"))

    result = runtime.invoke("vision.mock_detect", {"query": "roller"}, TraceContext())

    self.assertFalse(result.success)
    self.assertIn("$.label is required", result.error or "")
