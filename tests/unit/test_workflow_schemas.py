"""Unit tests for ActionList and ActionStep schemas."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest import TestCase

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
  sys.path.insert(0, str(SRC))

from sensoragent.schemas import ActionList, ActionStep, ActionStepKind


class WorkflowSchemaTest(TestCase):
  def test_action_step_schema(self) -> None:
    step = ActionStep(
      name="detect_object",
      kind=ActionStepKind.TOOL,
      target="vision.config_detect",
      input={"query": "{{ object_query }}"},
      save_as="object",
      description="Detect the target object.",
    )

    self.assertEqual(step.kind, ActionStepKind.TOOL)
    self.assertEqual(step.target, "vision.config_detect")
    self.assertEqual(step.input["query"], "{{ object_query }}")
    self.assertEqual(step.save_as, "object")
    self.assertTrue(step.stop_on_failure)
    self.assertEqual(step.to_dict()["kind"], ActionStepKind.TOOL)

  def test_action_list_schema(self) -> None:
    actionlist = ActionList(
      name="industrial.pick_place",
      description="Industrial pick-and-place action list.",
      inputs={"object_query": "string", "target": "string"},
      steps=[
        ActionStep(
          name="detect_object",
          kind=ActionStepKind.TOOL,
          target="vision.config_detect",
          input={"query": "{{ object_query }}"},
          save_as="object",
        ),
        ActionStep(
          name="pick_object",
          kind=ActionStepKind.TOOL,
          target="robot.plan_top_down_pick",
          input={"object_id": "{{ object.object_id }}"},
          save_as="pick",
        ),
      ],
    )

    self.assertEqual(actionlist.name, "industrial.pick_place")
    self.assertEqual(len(actionlist.steps), 2)
    self.assertEqual(actionlist.inputs["object_query"], "string")
    self.assertEqual(actionlist.to_dict()["steps"][0]["name"], "detect_object")
