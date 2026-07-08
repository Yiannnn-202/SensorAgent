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
from sensoragent.state import TaskStatus


class TaskLifecycleTest(TestCase):
  def test_agent_run_task_lifecycle_succeeds(self) -> None:
    bundle = build_agent_from_config(ROOT / "configs" / "mock.yaml")

    task = bundle.agent.run_task(
      "put the silver roller into the third bin cell",
      {"object_query": "silver roller", "target": "third bin cell"},
    )

    self.assertEqual(task.status, TaskStatus.SUCCEEDED)
    self.assertIsNotNone(task.plan)
    self.assertEqual(task.plan.target, "mock.pick_place_actionlist")
    self.assertIsNotNone(task.result)
    self.assertEqual(task.result["place"]["target"], "third bin cell")
    self.assertIs(bundle.task_store.get(task.task_id), task)

    event_names = [event.event for event in bundle.event_stream.events()]
    self.assertEqual(
      event_names,
      ["task_created", "task_started", "task_planned", "task_succeeded"],
    )

  def test_agent_cancel_pending_task(self) -> None:
    bundle = build_agent_from_config(ROOT / "configs" / "mock.yaml")
    task = bundle.agent.create_task("cancel me", {"object_query": "roller"})

    cancelled = bundle.agent.cancel_task(task.task_id)

    self.assertIsNotNone(cancelled)
    self.assertEqual(cancelled.status, TaskStatus.CANCELLED)
    event_names = [event.event for event in bundle.event_stream.events()]
    self.assertIn("task_cancelled", event_names)
