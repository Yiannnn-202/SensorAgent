"""End-to-end tests for DecisionTree execution."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest import TestCase

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
  sys.path.insert(0, str(SRC))

from sensoragent.agent import build_agent_from_config
from sensoragent.schemas import TraceContext
from sensoragent.tools.robot.failure import MockFailOncePickTool
from sensoragent.tools.vision.failure import MockNotFoundDetectTool
from sensoragent.workflows import (
  DecisionTreeRuntime,
  build_mock_not_found_branch_tree,
  build_mock_retry_pick_tree,
)


class DecisionTreePipelineTest(TestCase):
  def test_decision_tree_retries_after_pick_failure(self) -> None:
    bundle = build_agent_from_config(ROOT / "configs" / "mock.yaml")
    bundle.tool_registry.register(MockFailOncePickTool())
    runtime = DecisionTreeRuntime(
      bundle.tool_runtime,
      bundle.skill_runtime,
      bundle.actionlist_runtime,
      bundle.actionlists,
      bundle.logger,
    )

    result = runtime.run(
      build_mock_retry_pick_tree(),
      {"object_query": "silver roller"},
      TraceContext(),
    )

    self.assertTrue(result.success)
    pick_result = next(node for node in result.nodes if node.node == "pick")
    self.assertEqual(pick_result.attempts, 2)
    self.assertEqual(result.nodes[-1].node, "success")
    self.assertIn("decision_node_attempt_failed", list(bundle.logger.events()))

  def test_decision_tree_branches_when_object_not_found(self) -> None:
    bundle = build_agent_from_config(ROOT / "configs" / "mock.yaml")
    bundle.tool_registry.register(MockNotFoundDetectTool())
    runtime = DecisionTreeRuntime(
      bundle.tool_runtime,
      bundle.skill_runtime,
      bundle.actionlist_runtime,
      bundle.actionlists,
      bundle.logger,
    )

    result = runtime.run(
      build_mock_not_found_branch_tree(),
      {"object_query": "missing object"},
      TraceContext(),
    )

    self.assertFalse(result.success)
    self.assertEqual([node.node for node in result.nodes], ["detect", "found_check", "not_found"])
    self.assertIn("decision_tree_finished", list(bundle.logger.events()))
