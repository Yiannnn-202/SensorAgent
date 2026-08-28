"""Unit tests for minimal registries and structured logging."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch
from unittest import TestCase

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
  sys.path.insert(0, str(SRC))

from sensoragent.logger import TaskLogger
from sensoragent.schemas import SkillCall, SkillResult, SkillSpec, ToolCall, ToolResult, ToolSpec, TraceContext
from sensoragent.skills import Skill, SkillContext, SkillRegistry
from sensoragent.skills.errors import SkillNotFoundError, SkillRegistrationError
from sensoragent.tools import ToolRegistry, ToolRuntime
from sensoragent.tools.errors import ToolNotFoundError, ToolRegistrationError


class _TestTool:
  spec = ToolSpec(name="test.tool", description="test tool")

  def run(self, call: ToolCall) -> ToolResult:
    del call
    return ToolResult(tool=self.spec.name, success=True, output={"ok": True})


class _TestSkill(Skill):
  spec = SkillSpec(name="test.skill", description="test skill")

  def run(self, call: SkillCall, context: SkillContext) -> SkillResult:
    del call, context
    return SkillResult(skill=self.spec.name, success=True, output={"ok": True})


class RegistryLoggerTest(TestCase):
  def test_tool_registry_registers_and_lists_tools(self) -> None:
    registry = ToolRegistry()
    registry.register(_TestTool())

    self.assertEqual(registry.names(), ["test.tool"])
    self.assertEqual(registry.get("test.tool").spec.name, "test.tool")

  def test_tool_registry_rejects_duplicate_tools(self) -> None:
    registry = ToolRegistry()
    registry.register(_TestTool())

    with self.assertRaises(ToolRegistrationError):
      registry.register(_TestTool())

  def test_tool_registry_raises_typed_error_for_unknown_tool(self) -> None:
    registry = ToolRegistry()

    with self.assertRaises(ToolNotFoundError):
      registry.get("vision.missing")

  def test_skill_registry_registers_and_lists_skills(self) -> None:
    registry = SkillRegistry()
    registry.register(_TestSkill())

    self.assertEqual(registry.names(), ["test.skill"])
    self.assertEqual(registry.get("test.skill").spec.name, "test.skill")

  def test_skill_registry_rejects_duplicate_skills(self) -> None:
    registry = SkillRegistry()
    registry.register(_TestSkill())

    with self.assertRaises(SkillRegistrationError):
      registry.register(_TestSkill())

  def test_skill_registry_raises_typed_error_for_unknown_skill(self) -> None:
    registry = SkillRegistry()

    with self.assertRaises(SkillNotFoundError):
      registry.get("missing.skill")

  def test_task_logger_records_events(self) -> None:
    logger = TaskLogger()
    trace = TraceContext(task_id="task_test", trace_id="trace_test")

    logger.log("test_event", trace, {"value": 1})

    self.assertEqual(list(logger.events()), ["test_event"])
    record = logger.records[0]
    self.assertEqual(record.task_id, "task_test")
    self.assertEqual(record.trace_id, "trace_test")
    self.assertEqual(record.payload, {"value": 1})

  def test_task_logger_prints_console_progress_to_stderr(self) -> None:
    logger = TaskLogger(console=True)
    trace = TraceContext(task_id="task_test", trace_id="trace_test")

    with patch("sys.stderr") as stderr:
      logger.log("tool_call_started", trace, {"tool": "vision.open_vocab_detect"})

    stderr.write.assert_called()
    output = "".join(call.args[0] for call in stderr.write.call_args_list)
    self.assertIn("[tool] start vision.open_vocab_detect", output)

  def test_tool_runtime_wraps_unexpected_tool_failure(self) -> None:
    class BrokenTool:
      spec = ToolSpec(name="broken.tool", description="Broken tool")

      def run(self, call: ToolCall) -> ToolResult:
        raise RuntimeError("boom")

    logger = TaskLogger()
    registry = ToolRegistry()
    registry.register(BrokenTool())
    runtime = ToolRuntime(registry, logger)

    result = runtime.invoke("broken.tool", {}, TraceContext())

    self.assertFalse(result.success)
    self.assertIn("Tool execution failed for broken.tool", result.error or "")
    self.assertIn("tool_call_finished", list(logger.events()))
