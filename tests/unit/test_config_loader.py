"""Unit tests for configuration loading and runtime bootstrap."""

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
from sensoragent.schemas import TraceContext


class ConfigLoaderTest(TestCase):
  def test_load_mock_config(self) -> None:
    config = load_config(ROOT / "configs" / "mock.yaml")

    self.assertEqual(config.agent.mode, "mock")
    self.assertEqual(config.agent.default_skill, "mock.pick_and_place")
    self.assertIn("vision.mock_detect", config.tools.enabled)
    self.assertIn("mock.pick_and_place", config.skills.enabled)

  def test_build_agent_from_mock_config(self) -> None:
    bundle = build_agent_from_config(ROOT / "configs" / "mock.yaml")

    self.assertIn("vision.mock_detect", bundle.tool_registry.names())
    self.assertIn("robot.mock_pick", bundle.tool_registry.names())
    self.assertIn("mock.pick_and_place", bundle.skill_registry.names())

  def test_build_agent_from_explicit_env_path(self) -> None:
    bundle = build_agent_from_env(ROOT / "configs" / "mock.yaml")

    self.assertIn("vision.mock_detect", bundle.tool_registry.names())
    self.assertIn("mock.pick_and_place", bundle.skill_registry.names())

  def test_load_robot_sim_vision_config(self) -> None:
    config = load_config(ROOT / "configs" / "robot_sim.yaml")

    self.assertEqual(config.integrations.vision["backend"], "grounding_dino")
    self.assertEqual(
      config.integrations.vision["grounding_dino_model"],
      "models/vision/grounding-dino/grounding_dino_object_mask_2_unified_v1/checkpoint-best",
    )
    self.assertEqual(
      config.integrations.vision["sam2_model_path"],
      "models/vision/sam2_t.pt",
    )
    self.assertTrue(config.integrations.vision["refine_masks"])
    self.assertFalse(config.integrations.vision["require_masks"])
    self.assertNotIn("model_path", config.integrations.vision)
    self.assertIn("vision.open_vocab_detect", config.tools.enabled)
    self.assertEqual(
      config.scene.robot_joint_order,
      ["joint1", "joint2", "joint3", "joint4", "joint5", "joint6"],
    )
    self.assertIsNone(config.scene.joint_poses["pick_staging_joints"])
    self.assertIsNone(config.scene.joint_poses["carry_joints"])
    self.assertIsNone(config.scene.joint_poses["place_staging_joints"])
    self.assertEqual(config.scene.objects["block"][:3], [-0.24, -0.18, 0.14])
    self.assertEqual(config.scene.objects["cube"], config.scene.objects["block"])

  def test_load_audio_robot_sim_config(self) -> None:
    config = load_config(ROOT / "configs" / "audio_robot_sim.yaml")

    self.assertEqual(config.agent.mode, "audio_robot_sim")
    self.assertEqual(config.integrations.audio["backend"], "local")
    self.assertEqual(config.integrations.microphone["backend"], "sounddevice_vad")
    self.assertEqual(config.integrations.robot["backend"], "http")
    self.assertTrue(config.integrations.vision["recovery_live_detect"])
    self.assertIn("audio.listen_vad_transcribe", config.tools.enabled)
    self.assertIn("vision.capture_frame", config.tools.enabled)
    self.assertIn("vision.verify_object_in_bin", config.tools.enabled)
    self.assertIn("robot.pick", config.skills.enabled)
    self.assertIn("bin_cell_3", config.scene.place_targets)

  def test_hardware_baseline_enables_local_voice_input(self) -> None:
    config = load_config(
      ROOT / "configs" / "robot_hardware_sensoragent_v1i_baseline.yaml"
    )

    self.assertEqual(config.integrations.audio["backend"], "local")
    self.assertEqual(config.integrations.audio["listen_language"], "zh")
    self.assertEqual(
      config.integrations.microphone["backend"], "sounddevice_vad"
    )
    self.assertIn("audio.listen_vad_transcribe", config.tools.enabled)
    self.assertEqual(config.integrations.vision["backend"], "grounding_dino")
    self.assertIn("vision.grounded_sam2", config.tools.enabled)
    self.assertEqual(
      config.integrations.vision["source_region"]["frame_id"], "base_link"
    )
    self.assertEqual(
      len(config.integrations.vision["source_region"]["polygon"]), 4
    )
    self.assertEqual(config.scene.workspace["table_z"], 0.084)
    self.assertEqual(config.scene.pick_profiles["short_bolt"]["descent_speed"], 1.0)
    self.assertEqual(config.scene.pick_profiles["short_bolt"]["lift_speed"], 1.0)
    self.assertEqual(config.scene.pick_profiles["short_bolt"]["gripper_speed"], 0.75)
    self.assertEqual(
      config.scene.pick_profiles["hex_nut"]["position_offset"],
        [0.0, 0.0, 0.027],
    )
    self.assertTrue(config.scene.pick_profiles["hex_nut"]["lock_orientation"])
    self.assertEqual(config.scene.pick_profiles["hex_nut"]["motion_speed"], 1.0)
    self.assertEqual(config.scene.pick_profiles["hex_nut"]["descent_speed"], 1.0)
    self.assertEqual(config.scene.pick_profiles["hex_nut"]["gripper_force"], 1.0)
    self.assertEqual(config.scene.pick_profiles["hex_nut"]["close_opening"], 0.0)
    self.assertEqual(config.scene.pick_profiles["hex_nut"]["gripper_speed"], 0.75)
    self.assertIn("hardware.pick_place_actionlist", _allowed_planner_targets(
      config,
      {"hardware.pick_place_actionlist": object()},
      {},
    ))

  def test_yolo_seg_hardware_config_inherits_short_bolt_baseline(self) -> None:
    config = load_config(ROOT / "configs" / "robot_hardware_yolo_seg.yaml")

    self.assertEqual(config.integrations.vision["backend"], "yolo_seg")
    self.assertEqual(
      config.integrations.vision["model_path"],
      "/home/hcn/Island-Arm/models/combined.pt",
    )
    self.assertTrue(config.integrations.vision["first_detection_preview_gui"])
    self.assertEqual(config.scene.pick_profiles["short_bolt"]["gripper_force"], 1.0)
    self.assertTrue(config.scene.pick_profiles["roller"]["enabled"])
    self.assertEqual(config.scene.pick_profiles["roller"]["position_offset"], [0.015, 0.0, 0.018])
    self.assertFalse(config.scene.pick_profiles["roller"]["lock_orientation"])
    self.assertEqual(config.scene.pick_profiles["roller"]["orientation_mode"], "yaw_only")
    self.assertTrue(config.scene.pick_profiles["hex_nut"]["enabled"])
    self.assertEqual(
      config.scene.pick_profiles["hex_nut"]["position_offset"],
        [0.0, 0.0, 0.027],
    )
    self.assertTrue(config.scene.pick_profiles["hex_nut"]["lock_orientation"])
    self.assertEqual(config.scene.pick_profiles["hex_nut"]["motion_speed"], 1.0)
    self.assertEqual(config.scene.pick_profiles["hex_nut"]["gripper_force"], 1.0)
    self.assertEqual(config.scene.pick_profiles["hex_nut"]["close_opening"], 0.0)
    self.assertEqual(config.scene.pick_profiles["hex_nut"]["gripper_speed"], 0.75)
    self.assertEqual(config.scene.pick_profiles["roller"]["descent_speed"], 1.0)
    self.assertEqual(config.scene.pick_profiles["roller"]["gripper_force"], 1.0)
    self.assertIn("vision.open_vocab_detect", config.tools.enabled)
    self.assertIn("vision.resolve_reference", config.tools.enabled)

  def test_hardware_config_enables_pick_actionlist_dependencies(self) -> None:
    config = load_config(ROOT / "configs" / "robot_hardware.example.yaml")

    self.assertIn("vision.capture_frame", config.tools.enabled)
    self.assertIn("vision.grounded_sam2", config.tools.enabled)
    self.assertIn("robot.select_pick_profile", config.tools.enabled)
    self.assertIn("robot.resolve_place_target", config.tools.enabled)
    self.assertIn("robot.plan_place", config.tools.enabled)
    self.assertIn("robot.verify_grasp", config.skills.enabled)
    self.assertIn("robot.verify_place", config.skills.enabled)
    self.assertIn("robot.ensure_observe_pose", config.tools.enabled)
    self.assertEqual(config.scene.pick_profiles["short_bolt"]["gripper_force"], 0.6)
    self.assertEqual(config.scene.pick_profiles["short_bolt"]["close_opening"], 0.0)
    self.assertEqual(config.scene.pick_profiles["short_bolt"]["tcp_offset"], [0.0, 0.0, 0.131])
    self.assertEqual(config.scene.pick_profiles["short_bolt"]["camera_left_offset_m"], 0.01)

  def test_planner_targets_include_hardware_workflows_only_when_config_can_run_them(self) -> None:
    hardware_config = load_config(ROOT / "configs" / "robot_hardware.example.yaml")
    sim_config = load_config(ROOT / "configs" / "robot_sim.yaml")
    actionlists = {
      "hardware.pick_object_actionlist": object(),
      "hardware.pick_place_actionlist": object(),
      "industrial.pick_only_actionlist": object(),
    }

    self.assertIn(
      "hardware.pick_object_actionlist",
      _allowed_planner_targets(hardware_config, actionlists, {}),
    )
    self.assertNotIn(
      "hardware.pick_place_actionlist",
      _allowed_planner_targets(hardware_config, actionlists, {}),
    )
    hardware_config.scene.place_targets["bin_cell_1"] = {
      "position": [0.4, 0.0, 0.25],
      "orientation": [0.0, 1.0, 0.0, 0.0],
      "frame_id": "base_link",
    }
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

  def test_hardware_config_does_not_expose_default_place_targets(self) -> None:
    bundle = build_agent_from_config(
      ROOT / "configs" / "robot_hardware.example.yaml",
    )

    result = bundle.tool_runtime.invoke(
      "robot.resolve_place_target",
      {"target": "bin_cell_3"},
      TraceContext(),
    )
    self.assertFalse(result.success)
    self.assertIn("unknown place target", result.error or "")
