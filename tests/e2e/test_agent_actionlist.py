"""End-to-end tests for AgentRuntime ActionList dispatch."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest import TestCase

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
  sys.path.insert(0, str(SRC))

from sensoragent.agent import build_agent_from_config
from sensoragent.mcp import MockMcpEndpoint
from sensoragent.schemas import AgentRequest


class AgentActionListTest(TestCase):
  def test_agent_runtime_runs_actionlist(self) -> None:
    bundle = build_agent_from_config(ROOT / "configs" / "mock.yaml")
    endpoint = MockMcpEndpoint(bundle.agent)

    response = endpoint.call_actionlist(
      "mock.pick_place_actionlist",
      {"object_query": "silver roller", "target": "third bin cell"},
    )

    self.assertTrue(response.success)
    self.assertIsNotNone(response.result)
    self.assertEqual(response.result["object"]["label"], "silver roller")
    self.assertEqual(response.result["place"]["target"], "third bin cell")
    self.assertIn("actionlist_started", list(bundle.logger.events()))

  def test_agent_runtime_rejects_unknown_actionlist(self) -> None:
    bundle = build_agent_from_config(ROOT / "configs" / "mock.yaml")
    endpoint = MockMcpEndpoint(bundle.agent)

    response = endpoint.call_actionlist("mock.missing_actionlist", {})

    self.assertFalse(response.success)
    self.assertIn("Unknown actionlist: mock.missing_actionlist", response.error or "")

  def test_agent_runtime_rejects_skill_and_actionlist_conflict(self) -> None:
    bundle = build_agent_from_config(ROOT / "configs" / "mock.yaml")

    response = bundle.agent.handle(
      AgentRequest(
        skill="mock.pick_and_place",
        actionlist="mock.pick_place_actionlist",
        input={},
      )
    )

    self.assertFalse(response.success)
    self.assertIn("cannot specify both skill and actionlist", response.error or "")
