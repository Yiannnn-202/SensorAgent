"""Tests for the randomized Gazebo sorting dataset collector."""

from __future__ import annotations

import importlib.util
import math
import random
from pathlib import Path
from unittest import TestCase


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "linux" / "collect_randomized_sorting_dataset.py"


def _load_module():
  spec = importlib.util.spec_from_file_location(
    "collect_randomized_sorting_dataset",
    SCRIPT,
  )
  module = importlib.util.module_from_spec(spec)
  assert spec is not None and spec.loader is not None
  spec.loader.exec_module(module)
  return module


class RandomizedSortingDatasetScriptTest(TestCase):
  def test_parts_match_current_three_by_three_scene(self) -> None:
    module = _load_module()

    self.assertEqual(len(module.PARTS), 9)
    self.assertEqual(
      {part["class_name"] for part in module.PARTS},
      {"roller", "hex_nut", "short_bolt"},
    )
    self.assertEqual(
      {part["entity"] for part in module.PARTS},
      {
        f"metal_{class_name}_{index:02d}"
        for class_name in ("roller", "hex_nut", "short_bolt")
        for index in range(1, 4)
      },
    )
    bolts = [
      part for part in module.PARTS if part["class_name"] == "short_bolt"
    ]
    self.assertTrue(all(part["roll"] == math.pi for part in bolts))

  def test_clear_randomization_stays_near_safe_grid_without_overlap(self) -> None:
    module = _load_module()
    poses = module._randomized_poses(
      random.Random(42),
      position_jitter=0.0075,
      occlusion_rate=0.0,
    )

    self.assertEqual(len(poses), 9)
    positions = [pose["position"][:2] for pose in poses.values()]
    for x, y in positions:
      self.assertGreaterEqual(x, 0.155)
      self.assertLessEqual(x, 0.370)
      self.assertGreaterEqual(y, -0.228)
      self.assertLessEqual(y, -0.032)
    minimum_distance = min(
      math.dist(first, second)
      for index, first in enumerate(positions)
      for second in positions[index + 1:]
    )
    self.assertGreaterEqual(minimum_distance, 0.075)

  def test_pose_request_supports_head_down_bolt_orientation(self) -> None:
    module = _load_module()

    request = module._pose_request(
      "metal_short_bolt_01",
      0.2,
      -0.04,
      0.3325,
      math.pi,
      0.0,
      0.0,
    )

    self.assertIn('name: "metal_short_bolt_01"', request)
    self.assertIn("orientation { x: 1.00000000", request)
