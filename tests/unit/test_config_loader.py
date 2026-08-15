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
from sensoragent.config import load_config


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
