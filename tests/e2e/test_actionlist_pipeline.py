"""End-to-end tests for ActionList execution."""

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
from sensoragent.schemas import ActionList, ActionStep, ActionStepKind, TraceContext
from sensoragent.workflows import ActionListRuntime, build_mock_pick_place_actionlist


class ActionListPipelineTest(TestCase):
  def test_mock_pick_place_actionlist(self) -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
      log_path = Path(temp_dir) / "actionlist.jsonl"
      bundle = build_agent_from_config(ROOT / "configs" / "mock.yaml", log_path=log_path)
      runtime = ActionListRuntime(bundle.tool_runtime, bundle.skill_runtime, bundle.logger)

      result = runtime.run(
        build_mock_pick_place_actionlist(),
        {"object_query": "silver roller", "target": "third bin cell"},
        TraceContext(),
      )

      self.assertTrue(result.success)
      self.assertIsNotNone(result.output)
      self.assertEqual(result.output["object"]["label"], "silver roller")
      self.assertEqual(result.output["pick"]["object_id"], "mock_object_001")
      self.assertEqual(result.output["place"]["target"], "third bin cell")
      self.assertEqual(
        [step.step for step in result.steps],
        ["detect_object", "pick_object", "place_object"],
      )

      called_tools = [
        record.payload["tool"]
        for record in bundle.logger.records
        if record.event == "tool_call_started"
      ]
      self.assertEqual(
        called_tools,
        ["vision.mock_detect", "robot.mock_pick", "robot.mock_place"],
      )
      events = list(bundle.logger.events())
      self.assertIn("actionlist_started", events)
      self.assertIn("action_step_started", events)
      self.assertIn("action_step_finished", events)
      self.assertIn("actionlist_finished", events)
      self.assertTrue(log_path.exists())
      self.assertGreater(log_path.stat().st_size, 0)

  def test_actionlist_stops_on_failure(self) -> None:
    bundle = build_agent_from_config(ROOT / "configs" / "mock.yaml")
    runtime = ActionListRuntime(bundle.tool_runtime, bundle.skill_runtime, bundle.logger)
    actionlist = ActionList(
      name="mock.failure_actionlist",
      steps=[
        ActionStep(
          name="bad_detect",
          kind=ActionStepKind.TOOL,
          target="vision.mock_detect",
          input={},
          save_as="object",
        ),
        ActionStep(
          name="should_not_run",
          kind=ActionStepKind.TOOL,
          target="robot.mock_pick",
          input={"object_id": "{{ object.object_id }}"},
        ),
      ],
    )

    result = runtime.run(actionlist, {}, TraceContext())

    self.assertFalse(result.success)
    self.assertEqual([step.step for step in result.steps], ["bad_detect"])
    self.assertIn("$.query is required", result.error or "")

    called_tools = [
      record.payload["tool"]
      for record in bundle.logger.records
      if record.event == "tool_call_started"
    ]
    self.assertEqual(called_tools, ["vision.mock_detect"])
