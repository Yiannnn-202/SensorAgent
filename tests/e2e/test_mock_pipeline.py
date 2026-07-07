"""End-to-end test for the minimal MCP/API -> Skill -> Tool chain."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest import TestCase

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
  sys.path.insert(0, str(SRC))

from sensoragent.agent import AgentRuntime
from sensoragent.logger import TaskLogger
from sensoragent.mcp import MockMcpEndpoint
from sensoragent.skills import SkillRegistry, SkillRuntime
from sensoragent.skills.mock import MockPickAndPlaceSkill
from sensoragent.tools import ToolRegistry, ToolRuntime
from sensoragent.tools.audio.mock import MockTranscribeTool
from sensoragent.tools.robot.mock import MockPickTool, MockPlaceTool
from sensoragent.tools.vision.mock import MockDetectTool


class MockPipelineTest(TestCase):
  def test_mock_mcp_to_skill_to_tool_pipeline(self) -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
      log_path = Path(temp_dir) / "task.jsonl"
      logger = TaskLogger(log_path)

      tool_registry = ToolRegistry()
      tool_registry.register(MockDetectTool())
      tool_registry.register(MockTranscribeTool())
      tool_registry.register(MockPickTool())
      tool_registry.register(MockPlaceTool())
      tool_runtime = ToolRuntime(tool_registry, logger)

      skill_registry = SkillRegistry()
      skill_registry.register(MockPickAndPlaceSkill())
      skill_runtime = SkillRuntime(skill_registry, tool_runtime, logger)

      agent = AgentRuntime(skill_runtime, logger)
      endpoint = MockMcpEndpoint(agent)

      response = endpoint.call_skill(
        "mock.pick_and_place",
        {"object_query": "silver roller", "target": "third bin cell"},
      )

      self.assertTrue(response.success)
      self.assertIsNotNone(response.result)
      self.assertEqual(response.result["object"]["label"], "silver roller")
      self.assertEqual(response.result["place"]["target"], "third bin cell")

      events = list(logger.events())
      self.assertIn("agent_request_started", events)
      self.assertIn("skill_call_started", events)
      self.assertIn("tool_call_started", events)
      self.assertIn("tool_call_finished", events)
      self.assertIn("skill_call_finished", events)
      self.assertIn("agent_request_finished", events)

      called_tools = [
        record.payload["tool"]
        for record in logger.records
        if record.event == "tool_call_started"
      ]
      self.assertEqual(
        called_tools,
        ["vision.mock_detect", "robot.mock_pick", "robot.mock_place"],
      )
      self.assertTrue(log_path.exists())
      self.assertGreater(log_path.stat().st_size, 0)
