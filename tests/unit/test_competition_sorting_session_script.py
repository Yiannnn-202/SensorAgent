"""Tests for the competition text/voice sorting session."""

from __future__ import annotations

import importlib.util
from dataclasses import replace
from pathlib import Path
from unittest import TestCase

from sensoragent.schemas import ActionListResult, ActionStepResult


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "linux" / "run_competition_sorting_session.py"


def _load_module():
  spec = importlib.util.spec_from_file_location(
    "run_competition_sorting_session",
    SCRIPT,
  )
  module = importlib.util.module_from_spec(spec)
  assert spec is not None and spec.loader is not None
  spec.loader.exec_module(module)
  return module


class CompetitionSortingSessionScriptTest(TestCase):
  def _session(self):
    module = _load_module()
    config = module.load_config(ROOT / "configs" / "robot_sorting_sim.yaml")
    config = module.prepare_config(config, execute=False, voice_enabled=False)
    config = replace(
      config,
      logging=replace(config.logging, console=False),
    )
    bundle = module.build_agent(config)
    return module, module.CompetitionSortingSession(config, bundle)

  def test_ambiguous_command_does_not_move_robot(self) -> None:
    _, session = self._session()

    result = session.handle_text("把滚轮放到三号格", turn_index=0)

    self.assertFalse(result["success"])
    self.assertEqual(result["error"], "INSTANCE_AMBIGUOUS")
    self.assertIn("检测到 3 个", result["clarification"])
    self.assertFalse(session.world.placed_instances)

  def test_grounded_command_executes_and_updates_world_state(self) -> None:
    _, session = self._session()

    result = session.handle_text(
      "把离机械臂最近的滚轮放到三号格",
      turn_index=0,
    )

    self.assertTrue(result["success"], result.get("execution"))
    self.assertEqual(
      result["selected_instance"]["instance_id"],
      "metal_roller_03",
    )
    self.assertEqual(
      result["world_state"]["bins"]["bin_cell_3"]["occupied_by"],
      "metal_roller_03",
    )
    self.assertEqual(result["perception_backend"], "oracle_config")

  def test_occupied_bin_requires_new_target(self) -> None:
    _, session = self._session()
    first = session.handle_text(
      "把最近的滚轮放到三号格",
      turn_index=0,
    )
    self.assertTrue(first["success"])

    second = session.handle_text(
      "把最近的六角螺母放到三号格",
      turn_index=1,
    )

    self.assertFalse(second["success"])
    self.assertEqual(second["error"], "TARGET_OCCUPIED")

  def test_text_configuration_removes_audio_runtime(self) -> None:
    module = _load_module()
    config = module.load_config(ROOT / "configs" / "robot_sorting_sim.yaml")

    active = module.prepare_config(config, execute=False, voice_enabled=False)

    self.assertEqual(active.integrations.robot["backend"], "fake")
    self.assertFalse(
      any(name.startswith("audio.") for name in active.tools.enabled)
    )

  def test_grasp_failure_is_classified_and_retried_once(self) -> None:
    _, session = self._session()
    original_run = session.bundle.actionlist_runtime.run
    calls = 0

    def fail_then_succeed(actionlist, input_data, trace):
      nonlocal calls
      calls += 1
      if calls == 1:
        return ActionListResult(
          actionlist=actionlist.name,
          success=False,
          steps=[
            ActionStepResult(
              step="verify_grasp",
              success=False,
              output={"opening": 0.0},
              error="grasp not detected (opening=0.0000)",
            )
          ],
          output=dict(input_data),
          error="grasp not detected (opening=0.0000)",
        )
      return original_run(actionlist, input_data, trace)

    session.bundle.actionlist_runtime.run = fail_then_succeed
    result = session.handle_text(
      "把最近的短螺栓放到二号格",
      turn_index=0,
    )

    self.assertTrue(result["success"], result["execution"])
    self.assertEqual(result["execution"]["recovery_attempts"], 1)
    first_attempt = result["execution"]["attempts"][0]
    self.assertEqual(
      first_attempt["classification"]["failure_type"],
      "GRASP_EMPTY",
    )
    self.assertEqual(
      first_attempt["recovery_plan"]["strategy"],
      "retry_pick_adjusted_grasp",
    )

  def test_execution_runtime_world_state_is_merged_into_session_state(self) -> None:
    _, session = self._session()
    original_run = session.bundle.actionlist_runtime.run

    def run_with_world_state(actionlist, input_data, trace):
      result = original_run(actionlist, input_data, trace)
      output = dict(result.output or {})
      output["world_state"] = {
        "objects": {
          input_data["object_query"]: {
            "label": "roller",
            "pose_3d": [0.24, 0.23, 0.142],
            "confidence": 0.99,
            "source": "decision_tree",
            "status": "placed",
            "target": input_data["target"],
          }
        },
        "bins": {
          input_data["target"]: {
            "status": "occupied",
            "occupied_by": input_data["object_query"],
            "observed_position": [0.36, -0.06, 0.30],
          }
        },
        "current_task": {
          "object_id": input_data["object_query"],
          "target": input_data["target"],
          "step": "placed",
        },
        "history": [{"event": "object_placed_in_target"}],
      }
      return ActionListResult(
        actionlist=result.actionlist,
        success=result.success,
        steps=result.steps,
        output=output,
        error=result.error,
      )

  def test_batch_command_places_every_instance_one_cell_each(self) -> None:
    _, session = self._session()
    executed: list[dict] = []
    original_run = session.bundle.actionlist_runtime.run

    def record_runs(actionlist, input_data, trace):
      executed.append(dict(input_data))
      return original_run(actionlist, input_data, trace)

    session.bundle.actionlist_runtime.run = record_runs
    result = session.handle_text("把所有滚轮放到一号格", turn_index=0)

    self.assertTrue(result["success"], result.get("subtasks"))
    self.assertEqual(result["type"], "batch_command")
    self.assertEqual(len(result["subtasks"]), 3)
    # Each instance gets its own cell, filling from the named start target.
    self.assertEqual(
      [subtask["target"] for subtask in result["subtasks"]],
      ["bin_cell_1", "bin_cell_2", "bin_cell_3"],
    )
    self.assertEqual(
      {subtask["instance_id"] for subtask in result["subtasks"]},
      {"metal_roller_01", "metal_roller_02", "metal_roller_03"},
    )
    self.assertEqual(len(executed), 3)
    world_events = [entry["event"] for entry in session.world.history]
    self.assertIn("batch_task_started", world_events)
    self.assertIn("batch_subtask_completed", world_events)
    self.assertIn("batch_task_finished", world_events)

  def test_batch_command_failure_stops_and_records_remaining_queue(self) -> None:
    _, session = self._session()
    original_run = session.bundle.actionlist_runtime.run
    instances_executed: list[str] = []

    def fail_second_instance(actionlist, input_data, trace):
      instance_id = input_data["object_query"]
      if not instances_executed or instances_executed[-1] != instance_id:
        instances_executed.append(instance_id)
      # The second queued instance fails every attempt, including recovery.
      if len(instances_executed) >= 2:
        return ActionListResult(
          actionlist=actionlist.name,
          success=False,
          steps=[
            ActionStepResult(
              step="verify_grasp",
              success=False,
              output={"opening": 0.0},
              error="grasp not detected (opening=0.0000)",
            )
          ],
          output=dict(input_data),
          error="grasp not detected (opening=0.0000)",
        )
      return original_run(actionlist, input_data, trace)

    session.bundle.actionlist_runtime.run = fail_second_instance
    result = session.handle_text("把所有滚轮放到一号格", turn_index=0)

    self.assertFalse(result["success"])
    self.assertEqual(len(result["subtasks"]), 2)
    self.assertTrue(result["subtasks"][0]["success"])
    self.assertFalse(result["subtasks"][1]["success"])
    failed_id = result["subtasks"][1]["instance_id"]
    self.assertEqual(result["failed_instance"], failed_id)
    self.assertEqual(len(result["remaining_queue"]), 1)
    self.assertNotIn(failed_id, result["remaining_queue"])
    self.assertNotIn(failed_id, session.world.placed_instances)
    world_events = [entry["event"] for entry in session.world.history]
    self.assertIn("batch_task_interrupted", world_events)
    # Only the first two instances ever reached the actionlist.
    self.assertEqual(
      set(instances_executed),
      {sub["instance_id"] for sub in result["subtasks"]},
    )

  def test_batch_command_rejects_when_cells_run_out(self) -> None:
    _, session = self._session()
    for target, cell in session.world.bins.items():
      if target != "bin_cell_2":
        cell.status = "occupied"

    result = session.handle_text("把所有滚轮放到一号格", turn_index=0)

    self.assertFalse(result["success"])
    self.assertEqual(result["error"], "NOT_ENOUGH_EMPTY_CELLS")

  def test_batch_command_rejects_when_class_is_exhausted(self) -> None:
    _, session = self._session()
    for instance_id in ("metal_roller_01", "metal_roller_02", "metal_roller_03"):
      session.world.mark_placed(instance_id, "bin_cell_1")

    result = session.handle_text("把所有滚轮放到一号格", turn_index=0)

    self.assertFalse(result["success"])
    self.assertEqual(result["error"], "NO_REMAINING_INSTANCES")
