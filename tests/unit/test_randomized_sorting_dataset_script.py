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

  def test_randomization_samples_zero_to_three_instances_per_class(self) -> None:
    module = _load_module()
    poses, counts = module._randomized_poses(
      random.Random(42),
      position_jitter=0.0075,
      min_per_class=0,
      max_per_class=3,
      allow_empty_scene=False,
    )

    self.assertEqual(len(poses), 9)
    self.assertEqual(set(counts), {"roller", "hex_nut", "short_bolt"})
    self.assertTrue(all(0 <= count <= 3 for count in counts.values()))
    self.assertGreater(sum(counts.values()), 0)
    active = [pose for pose in poses.values() if pose["active"]]
    self.assertEqual(len(active), sum(counts.values()))
    positions = [pose["position"][:2] for pose in active]
    for x, y in positions:
      self.assertGreaterEqual(x, 0.155)
      self.assertLessEqual(x, 0.370)
      self.assertGreaterEqual(y, -0.228)
      self.assertLessEqual(y, -0.032)
    if len(positions) > 1:
      minimum_distance = min(
        math.dist(first, second)
        for index, first in enumerate(positions)
        for second in positions[index + 1:]
      )
      self.assertGreaterEqual(minimum_distance, 0.075)

  def test_inactive_instances_are_parked_outside_camera_workspace(self) -> None:
    module = _load_module()
    poses, counts = module._randomized_poses(
      random.Random(7),
      position_jitter=0.0,
      min_per_class=0,
      max_per_class=0,
      allow_empty_scene=True,
    )

    self.assertEqual(counts, {"roller": 0, "hex_nut": 0, "short_bolt": 0})
    self.assertTrue(all(not pose["active"] for pose in poses.values()))
    self.assertTrue(
      all(pose["position"][0] >= 1.2 for pose in poses.values())
    )

  def test_one_hundred_samples_include_class_empty_examples(self) -> None:
    module = _load_module()
    generated_counts = []
    for index in range(1, 101):
      _, counts = module._randomized_poses(
        random.Random(f"20260812:{index}"),
        position_jitter=0.0075,
        min_per_class=0,
        max_per_class=3,
        allow_empty_scene=False,
      )
      generated_counts.append(counts)

    for class_name in module.CLASS_NAMES:
      self.assertTrue(
        any(counts[class_name] == 0 for counts in generated_counts)
      )
      self.assertTrue(
        any(counts[class_name] == 3 for counts in generated_counts)
      )

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
