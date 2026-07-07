"""Unit tests for minimal registries and structured logging."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest import TestCase

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
  sys.path.insert(0, str(SRC))

from sensoragent.logger import TaskLogger
from sensoragent.schemas import TraceContext
from sensoragent.skills import SkillRegistry
from sensoragent.skills.mock import MockPickAndPlaceSkill
from sensoragent.tools import ToolRegistry
from sensoragent.tools.vision.mock import MockDetectTool


class RegistryLoggerTest(TestCase):
  def test_tool_registry_registers_and_lists_tools(self) -> None:
    registry = ToolRegistry()
    registry.register(MockDetectTool())

    self.assertEqual(registry.names(), ["vision.mock_detect"])
    self.assertEqual(registry.get("vision.mock_detect").spec.name, "vision.mock_detect")

  def test_skill_registry_registers_and_lists_skills(self) -> None:
    registry = SkillRegistry()
    registry.register(MockPickAndPlaceSkill())

    self.assertEqual(registry.names(), ["mock.pick_and_place"])
    self.assertEqual(registry.get("mock.pick_and_place").spec.name, "mock.pick_and_place")

  def test_task_logger_records_events(self) -> None:
    logger = TaskLogger()
    trace = TraceContext(task_id="task_test", trace_id="trace_test")

    logger.log("test_event", trace, {"value": 1})

    self.assertEqual(list(logger.events()), ["test_event"])
    record = logger.records[0]
    self.assertEqual(record.task_id, "task_test")
    self.assertEqual(record.trace_id, "trace_test")
    self.assertEqual(record.payload, {"value": 1})
