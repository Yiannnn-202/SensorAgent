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
