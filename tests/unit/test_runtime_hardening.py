"""Unit tests for ToolRuntime timeout, retry, and metadata behavior."""

from __future__ import annotations

import sys
import time
from pathlib import Path
from unittest import TestCase

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
  sys.path.insert(0, str(SRC))

from sensoragent.logger import TaskLogger
from sensoragent.schemas import SkillSpec, ToolCall, ToolResult, ToolSpec, TraceContext
from sensoragent.tools import ToolRegistry, ToolRuntime


class RuntimeHardeningTest(TestCase):
  def test_tool_spec_metadata_defaults_and_overrides(self) -> None:
    default_spec = ToolSpec(name="tool.default", description="Default metadata")
    custom_spec = ToolSpec(
      name="tool.custom",
      description="Custom metadata",
      version="1.2.3",
      tags=("mock", "test"),
      enabled=False,
      timeout_seconds=1.5,
      max_retries=2,
    )

    self.assertEqual(default_spec.version, "0.1.0")
    self.assertEqual(default_spec.tags, ())
    self.assertTrue(default_spec.enabled)
    self.assertIsNone(default_spec.timeout_seconds)
    self.assertEqual(default_spec.max_retries, 0)
    self.assertEqual(custom_spec.version, "1.2.3")
    self.assertEqual(custom_spec.tags, ("mock", "test"))
    self.assertFalse(custom_spec.enabled)
    self.assertEqual(custom_spec.timeout_seconds, 1.5)
    self.assertEqual(custom_spec.max_retries, 2)

  def test_skill_spec_metadata_defaults_and_overrides(self) -> None:
    default_spec = SkillSpec(name="skill.default", description="Default metadata")
    custom_spec = SkillSpec(
      name="skill.custom",
      description="Custom metadata",
      version="1.2.3",
      tags=("workflow",),
      enabled=False,
    )

    self.assertEqual(default_spec.version, "0.1.0")
    self.assertEqual(default_spec.tags, ())
    self.assertTrue(default_spec.enabled)
    self.assertEqual(custom_spec.version, "1.2.3")
    self.assertEqual(custom_spec.tags, ("workflow",))
    self.assertFalse(custom_spec.enabled)

  def test_tool_runtime_times_out_slow_tool(self) -> None:
    class SlowTool:
      spec = ToolSpec(
        name="slow.tool",
        description="Slow tool",
        timeout_seconds=0.01,
      )

      def run(self, call: ToolCall) -> ToolResult:
        time.sleep(0.1)
        return ToolResult(tool=self.spec.name, success=True, output={"ok": True})

    logger = TaskLogger()
    registry = ToolRegistry()
    registry.register(SlowTool())
    runtime = ToolRuntime(registry, logger)

    result = runtime.invoke("slow.tool", {}, TraceContext())

    self.assertFalse(result.success)
    self.assertIn("Tool timed out after", result.error or "")
    self.assertIn("tool_call_attempt_failed", list(logger.events()))

  def test_tool_runtime_retries_unexpected_execution_error(self) -> None:
    class FlakyTool:
      spec = ToolSpec(
        name="flaky.tool",
        description="Flaky tool",
        max_retries=1,
      )

      def __init__(self) -> None:
        self.calls = 0

      def run(self, call: ToolCall) -> ToolResult:
        self.calls += 1
        if self.calls == 1:
          raise RuntimeError("temporary failure")
        return ToolResult(tool=self.spec.name, success=True, output={"calls": self.calls})

    tool = FlakyTool()
    logger = TaskLogger()
    registry = ToolRegistry()
    registry.register(tool)
    runtime = ToolRuntime(registry, logger)

    result = runtime.invoke("flaky.tool", {}, TraceContext())

    self.assertTrue(result.success)
    self.assertEqual(result.output, {"calls": 2})
    self.assertEqual(tool.calls, 2)
    self.assertIn("tool_call_attempt_failed", list(logger.events()))
