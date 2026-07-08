"""End-to-end tests for structured failure paths."""

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


class FailurePathTest(TestCase):
  def test_unknown_skill_returns_structured_failure(self) -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
      log_path = Path(temp_dir) / "failure.jsonl"
      bundle = build_agent_from_config(ROOT / "configs" / "mock.yaml", log_path=log_path)
      endpoint = MockMcpEndpoint(bundle.agent)

      response = endpoint.call_skill("mock.missing", {})

      self.assertFalse(response.success)
      self.assertIsNone(response.result)
      self.assertIn("Unknown skill: mock.missing", response.error or "")
      events = list(bundle.logger.events())
      self.assertIn("agent_request_started", events)
      self.assertIn("skill_call_finished", events)
      self.assertIn("agent_request_finished", events)
      self.assertTrue(log_path.exists())
      self.assertGreater(log_path.stat().st_size, 0)
