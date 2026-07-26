"""Smoke tests for the Gazebo recovery demo runner.

The demo can be run without Gazebo when --execute is omitted; this keeps the
failure-injection plumbing testable on Windows and CI.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "linux" / "run_gazebo_recovery_demo.py"


def _load_demo_module():
  spec = importlib.util.spec_from_file_location("run_gazebo_recovery_demo", SCRIPT)
  module = importlib.util.module_from_spec(spec)
  assert spec is not None and spec.loader is not None
  spec.loader.exec_module(module)
  return module


class GazeboRecoveryDemoScriptTest(TestCase):
  def test_wrong_bin_demo_runs_without_gazebo(self) -> None:
    module = _load_demo_module()
    output = ROOT / "logs" / "tasks" / "test_recovery_demo_script.json"
    argv = [
      str(SCRIPT),
      "--failure",
      "wrong-bin",
      "--object-query",
      "roller",
      "--target",
      "bin_cell_3",
      "--wrong-target",
      "bin_cell_2",
      "--json-out",
      str(output),
    ]

    with patch.object(sys, "argv", argv):
      exit_code = module.main()

    self.assertEqual(exit_code, 0)
    data = json.loads(output.read_text(encoding="utf-8"))
    self.assertTrue(data["success"])
    self.assertEqual(data["classification"]["failure_type"], "WRONG_BIN")
    self.assertEqual(data["recovery"]["strategy"], "repick_from_observed_pose")
    self.assertIn("recover_pick", [node["node"] for node in data["nodes"]])
