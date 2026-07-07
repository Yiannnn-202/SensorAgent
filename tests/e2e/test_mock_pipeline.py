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

from sensoragent.agent import build_agent_from_config
from sensoragent.mcp import MockMcpEndpoint


class MockPipelineTest(TestCase):
  def test_mock_mcp_to_skill_to_tool_pipeline(self) -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
      log_path = Path(temp_dir) / "task.jsonl"
      bundle = build_agent_from_config(ROOT / "configs" / "mock.yaml", log_path=log_path)
      endpoint = MockMcpEndpoint(bundle.agent)

      response = endpoint.call_skill(
        "mock.pick_and_place",
        {"object_query": "silver roller", "target": "third bin cell"},
      )

      self.assertTrue(response.success)
      self.assertIsNotNone(response.result)
      self.assertEqual(response.result["object"]["label"], "silver roller")
      self.assertEqual(response.result["place"]["target"], "third bin cell")

      events = list(bundle.logger.events())
      self.assertIn("agent_request_started", events)
      self.assertIn("skill_call_started", events)
      self.assertIn("tool_call_started", events)
      self.assertIn("tool_call_finished", events)
      self.assertIn("skill_call_finished", events)
      self.assertIn("agent_request_finished", events)

      called_tools = [
        record.payload["tool"]
        for record in bundle.logger.records
        if record.event == "tool_call_started"
      ]
      self.assertEqual(
        called_tools,
        ["vision.mock_detect", "robot.mock_pick", "robot.mock_place"],
      )
      self.assertTrue(log_path.exists())
      self.assertGreater(log_path.stat().st_size, 0)
