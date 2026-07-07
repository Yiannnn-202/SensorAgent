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
