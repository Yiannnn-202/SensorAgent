"""Tests for the Phase G1 Gazebo smoke runner."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest import TestCase


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "linux" / "run_g1_gazebo_smoke.py"


def _load_module():
  spec = importlib.util.spec_from_file_location("run_g1_gazebo_smoke", SCRIPT)
  module = importlib.util.module_from_spec(spec)
  assert spec is not None and spec.loader is not None
  spec.loader.exec_module(module)
  return module


class G1GazeboSmokeScriptTest(TestCase):
  def test_fake_mode_writes_report_for_stable_baseline(self) -> None:
    module = _load_module()
    output = ROOT / "logs" / "tasks" / "test_g1_gazebo_smoke.json"

    exit_code = module.main(["--json-out", str(output), "--settle-seconds", "0"])

    self.assertEqual(exit_code, 0)
    report = module.json.loads(output.read_text(encoding="utf-8"))
    self.assertTrue(report["success"])
    self.assertEqual(report["mode"], "fake")
    self.assertEqual(
      report["actionlist"]["name"],
      "industrial.sorting_config_pick_place_actionlist",
    )
    self.assertTrue(report["grasp_matrix_smoke"]["result"]["success"])
