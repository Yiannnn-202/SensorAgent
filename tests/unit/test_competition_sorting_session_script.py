"""Tests for the submission competition sorting session."""

from __future__ import annotations

import importlib.util
from dataclasses import replace
from pathlib import Path
from unittest import TestCase

from sensoragent.schemas import (
  ActionListResult,
  ActionStepResult,
  DecisionNodeResult,
  DecisionTreeResult,
)


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
  def _sim_session(self):
    module = _load_module()
    config = module.load_config(ROOT / "configs" / "competition_sim.yaml")
    config = module.prepare_config(config, execute=False, voice_enabled=False)
    config = replace(config, logging=replace(config.logging, console=False))
    bundle = module.build_agent(config)
    return module, module.CompetitionSortingSession(config, bundle, backend="sim")

  def test_text_configuration_removes_audio_runtime(self) -> None:
    module = _load_module()
    config = module.load_config(ROOT / "configs" / "competition_sim.yaml")

    active = module.prepare_config(config, execute=False, voice_enabled=False)

    self.assertEqual(active.integrations.robot["backend"], "fake")
    self.assertFalse(
      any(name.startswith("audio.") for name in active.tools.enabled)
    )

  def test_sim_backend_rejects_multi_instance_command_without_selector(self) -> None:
    _, session = self._sim_session()

    result = session.handle_text("把滚轮放到三号格", turn_index=0)

    self.assertFalse(result["success"])
    self.assertEqual(result["error"], "INSTANCE_AMBIGUOUS")
    self.assertIn("请说明左、右、前、后、最近、最远或第几个", result["clarification"])

  def test_sim_backend_uses_live_perception_decision_tree(self) -> None:
    _, session = self._sim_session()
    calls: list[dict] = []

    def record_tree(tree, input_data, trace):
      calls.append({"tree": tree.name, "input": dict(input_data)})
      return DecisionTreeResult(
        decision_tree=tree.name,
        success=True,
        nodes=[DecisionNodeResult(node="detect_object", success=True)],
        output={
          "world_state": {
            "objects": {
              "roller_001": {
                "label": "roller",
                "pose_3d": [-0.25, 0.03, 0.14],
                "confidence": 0.91,
                "source": "vision.dual_branch_detect",
                "status": "placed",
                "target": input_data["target"],
              }
            },
            "bins": {
              input_data["target"]: {
                "status": "occupied",
                "occupied_by": "roller_001",
              }
            },
            "current_task": {"object_id": "roller_001", "target": input_data["target"]},
            "history": [{"event": "object_placed_in_target"}],
          }
        },
      )

    session.bundle.decision_tree_runtime.run = record_tree
    result = session.handle_text("把左边的滚轮放到三号格", turn_index=0)

    self.assertTrue(result["success"], result.get("execution"))
    self.assertEqual(result["perception_backend"], "gazebo_rgbd")
    self.assertEqual(calls[0]["tree"], "industrial.recovery_pick_place_tree")
    self.assertEqual(calls[0]["input"]["object_query"], "roller")
    self.assertEqual(calls[0]["input"]["target"], "bin_cell_3")
    self.assertEqual(calls[0]["input"]["spatial_constraint"]["relation"], "left")
    self.assertEqual(result["world_state"]["bins"]["bin_cell_3"]["occupied_by"], "roller_001")

  def test_hardware_backend_uses_hardware_pick_place_actionlist(self) -> None:
    module = _load_module()
    config = module.load_config(ROOT / "configs" / "competition_hardware.yaml")
    config = module.prepare_config(config, execute=False, voice_enabled=False)
    bundle = module.build_agent(config)
    session = module.CompetitionSortingSession(config, bundle, backend="hardware")
    calls: list[dict] = []

    def record_run(actionlist, input_data, trace):
      calls.append({"actionlist": actionlist.name, "input": dict(input_data)})
      return ActionListResult(
        actionlist=actionlist.name,
        success=False,
        steps=[
          ActionStepResult(
            step="capture_frame",
            success=False,
            error="CAPTURE_FAILED: test stub",
          )
        ],
        output=dict(input_data),
        error="CAPTURE_FAILED: test stub",
      )

    session.bundle.actionlist_runtime.run = record_run
    result = session.handle_text("把短螺栓放到一号格", turn_index=0)

    self.assertFalse(result["success"])
    self.assertEqual(result["backend"], "hardware")
    self.assertEqual(result["perception_backend"], "hardware_rgbd")
    self.assertEqual(calls[0]["actionlist"], "hardware.pick_place_actionlist")
    self.assertEqual(calls[0]["input"]["object_query"], "short bolt")
    self.assertEqual(calls[0]["input"]["pick_profile"], "short_bolt")
    self.assertEqual(calls[0]["input"]["target"], "bin_cell_1")

  def test_batch_command_is_rejected_in_visual_modes(self) -> None:
    _, session = self._sim_session()

    result = session.handle_text("把所有滚轮放到一号格", turn_index=0)

    self.assertFalse(result["success"])
    self.assertEqual(result["error"], "BATCH_UNSUPPORTED")
