"""Unit tests for submission configuration loading and runtime bootstrap."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest import TestCase

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
  sys.path.insert(0, str(SRC))

from sensoragent.agent import build_agent_from_config, build_agent_from_env
from sensoragent.agent.bootstrap import _allowed_planner_targets
from sensoragent.config import load_config


class ConfigLoaderTest(TestCase):
  def test_build_agent_from_explicit_env_path(self) -> None:
    bundle = build_agent_from_env(ROOT / "configs" / "competition_sim.yaml")

    self.assertIn("vision.dual_branch_detect", bundle.tool_registry.names())
    self.assertIn("industrial.recovery_pick_place_tree", bundle.decision_trees)

  def test_competition_sim_uses_live_dual_branch_perception(self) -> None:
    config = load_config(ROOT / "configs" / "competition_sim.yaml")

    self.assertEqual(config.agent.mode, "competition_sim")
    self.assertEqual(config.integrations.robot["backend"], "http")
    self.assertEqual(config.integrations.vision["backend"], "dual_branch")
    self.assertTrue(config.integrations.vision["recovery_live_detect"])
    self.assertIn("vision.dual_branch_detect", config.tools.enabled)
    self.assertIn("vision.capture_frame", config.tools.enabled)
    self.assertNotIn("vision.config_detect", config.tools.enabled)
    self.assertIn("bin_cell_3", config.scene.place_targets)

  def test_competition_eval_is_local_fake_backend(self) -> None:
    config = load_config(ROOT / "configs" / "competition_eval.yaml")

    self.assertEqual(config.agent.mode, "competition_eval")
    self.assertEqual(config.integrations.robot["backend"], "fake")
    self.assertFalse(config.integrations.vision["recovery_live_detect"])
    self.assertIn("vision.config_detect", config.tools.enabled)
    self.assertIn("robot.plan_oriented_pick", config.tools.enabled)

  def test_competition_hardware_enables_dual_branch_tools(self) -> None:
    config = load_config(ROOT / "configs" / "competition_hardware.yaml")

    self.assertEqual(config.agent.mode, "competition_hardware")
    self.assertEqual(config.integrations.robot["endpoint"], "http://127.0.0.1:8766")
    self.assertEqual(config.integrations.vision["backend"], "dual_branch")
    self.assertIn("vision.dual_branch_detect", config.tools.enabled)
    self.assertIn("vision.yolo11_seg_detect", config.tools.enabled)
    self.assertIn("vision.grounded_sam2", config.tools.enabled)
    self.assertIn("vision.capture_frame", config.tools.enabled)
    self.assertIn("robot.verify_grasp", config.skills.enabled)
    self.assertIn("robot.verify_place", config.skills.enabled)
    self.assertIn("short_bolt", config.scene.object_ontology)
    self.assertIn("bin_cell_1", config.scene.place_targets)

  def test_planner_targets_include_hardware_workflows_only_when_config_can_run_them(self) -> None:
    hardware_config = load_config(ROOT / "configs" / "competition_hardware.yaml")
    sim_config = load_config(ROOT / "configs" / "competition_sim.yaml")
    actionlists = {
      "hardware.pick_object_actionlist": object(),
      "hardware.pick_place_actionlist": object(),
      "industrial.pick_only_actionlist": object(),
    }

    self.assertIn(
      "hardware.pick_object_actionlist",
      _allowed_planner_targets(hardware_config, actionlists, {}),
    )
    self.assertIn(
      "hardware.pick_place_actionlist",
      _allowed_planner_targets(hardware_config, actionlists, {}),
    )
    self.assertNotIn(
      "hardware.pick_object_actionlist",
      _allowed_planner_targets(sim_config, actionlists, {}),
    )
    self.assertNotIn(
      "hardware.pick_place_actionlist",
      _allowed_planner_targets(sim_config, actionlists, {}),
    )

  def test_competition_configs_build_without_loading_model_weights(self) -> None:
    sim = build_agent_from_config(ROOT / "configs" / "competition_sim.yaml")
    eval_bundle = build_agent_from_config(ROOT / "configs" / "competition_eval.yaml")

    self.assertIn("vision.dual_branch_detect", sim.tool_registry.names())
    self.assertIn("vision.config_detect", eval_bundle.tool_registry.names())
