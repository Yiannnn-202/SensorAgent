"""Tests for the sorting-scene grasp matrix runner."""

from __future__ import annotations

import importlib.util
from dataclasses import replace
from pathlib import Path
from unittest import TestCase


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "linux" / "test_sorting_scene_grasp_matrix.py"


def _load_module():
  spec = importlib.util.spec_from_file_location(
    "test_sorting_scene_grasp_matrix",
    SCRIPT,
  )
  module = importlib.util.module_from_spec(spec)
  assert spec is not None and spec.loader is not None
  spec.loader.exec_module(module)
  return module


class SortingSceneGraspMatrixScriptTest(TestCase):
  def test_scene_matrix_matches_current_nine_instances(self) -> None:
    module = _load_module()

    self.assertEqual(
      set(module.SCENE_PARTS),
      {
        f"metal_{class_name}_{index:02d}"
        for class_name in ("roller", "hex_nut", "short_bolt")
        for index in range(1, 4)
      },
    )
    bolt_poses = {
      name: pose
      for name, pose in module.SCENE_PARTS.items()
      if "short_bolt" in name
    }
    self.assertTrue(all(pose[3] == module.math.pi for pose in bolt_poses.values()))

  def test_fake_backend_completes_one_grasp_attempt(self) -> None:
    module = _load_module()
    config = module.load_config(ROOT / "configs" / "robot_sorting_sim.yaml")
    config = replace(
      module._active_config(config, execute=False),
      logging=replace(config.logging, console=False),
    )
    bundle = module.build_agent(config)

    preparation = module._prepare_robot(
      bundle,
      config,
      execute=False,
      settle_seconds=0.0,
    )
    result = module.run_grasp_attempt(
      bundle,
      config,
      "metal_roller_02",
      attempt=1,
    )

    self.assertTrue(preparation)
    self.assertTrue(result["success"], result["error"])
    self.assertEqual(result["instance_id"], "metal_roller_02")
    self.assertEqual(result["failed_stage"], None)

  def test_main_fake_mode_writes_report(self) -> None:
    module = _load_module()
    output = ROOT / "logs" / "tasks" / "test_sorting_grasp_matrix.json"

    exit_code = module.main(
      [
        "--instance",
        "metal_short_bolt_02",
        "--json-out",
        str(output),
      ]
    )

    self.assertEqual(exit_code, 0)
    report = module.json.loads(output.read_text(encoding="utf-8"))
    self.assertTrue(report["success"])
    self.assertEqual(report["mode"], "fake")
    self.assertEqual(report["summary"]["total"], 1)
