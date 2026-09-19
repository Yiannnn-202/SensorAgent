"""End-to-end tests for Agent task lifecycle orchestration."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest import TestCase

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
  sys.path.insert(0, str(SRC))

from sensoragent.agent import build_agent_from_config
from sensoragent.agent.runtime import _validate_required_workflow_inputs
from sensoragent.schemas import AgentPlan, PlanTargetKind
from sensoragent.state import TaskStatus


class TaskLifecycleTest(TestCase):
  def test_required_workflow_inputs_reject_empty_planner_fields(self) -> None:
    error = _validate_required_workflow_inputs(
      AgentPlan(
        target_kind=PlanTargetKind.DECISION_TREE,
        target="industrial.recovery_pick_place_tree",
        input={"object_query": "", "target": "bin_cell_3"},
      ),
      {"object_query": "", "target": "bin_cell_3"},
    )

    self.assertEqual(
      error,
      "Planner selected industrial.recovery_pick_place_tree but missing required input(s): object_query",
    )

  def test_agent_create_task_lifecycle_records_state(self) -> None:
    bundle = build_agent_from_config(ROOT / "configs" / "competition_sim.yaml")
    task = bundle.agent.create_task(
      "把左边的滚轮放到三号格",
      {"object_query": "roller", "target": "bin_cell_3"},
    )

    self.assertEqual(task.status, TaskStatus.PENDING)
    self.assertIs(bundle.task_store.get(task.task_id), task)
    self.assertEqual(
      [event.event for event in bundle.event_stream.events()],
      ["task_created"],
    )

  def test_agent_cancel_pending_task(self) -> None:
    bundle = build_agent_from_config(ROOT / "configs" / "competition_sim.yaml")
    task = bundle.agent.create_task("cancel me", {"object_query": "roller"})

    cancelled = bundle.agent.cancel_task(task.task_id)

    self.assertIsNotNone(cancelled)
    self.assertEqual(cancelled.status, TaskStatus.CANCELLED)
    event_names = [event.event for event in bundle.event_stream.events()]
    self.assertIn("task_cancelled", event_names)
