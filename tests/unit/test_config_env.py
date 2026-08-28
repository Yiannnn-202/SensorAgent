"""Unit tests for environment-based config resolution."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest import TestCase

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
  sys.path.insert(0, str(SRC))

from sensoragent.config import resolve_config_path


class ConfigEnvTest(TestCase):
  def test_explicit_path_has_highest_priority(self) -> None:
    path = resolve_config_path(
      "custom.yaml",
      environ={"SENSORAGENT_CONFIG": "env.yaml", "SENSORAGENT_ENV": "mock"},
    )

    self.assertEqual(path, Path("custom.yaml"))

  def test_sensoragent_config_overrides_environment_name(self) -> None:
    path = resolve_config_path(
      environ={"SENSORAGENT_CONFIG": "configs/dev.yaml", "SENSORAGENT_ENV": "mock"}
    )

    self.assertEqual(path, Path("configs/dev.yaml"))

  def test_sensoragent_env_maps_to_named_config(self) -> None:
    path = resolve_config_path(environ={"SENSORAGENT_ENV": "competition"})

    self.assertEqual(path, Path("configs") / "competition.yaml")

  def test_default_config_is_competition_sim(self) -> None:
    path = resolve_config_path(environ={})

    self.assertEqual(path, Path("configs") / "competition_sim.yaml")
