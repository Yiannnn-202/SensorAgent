"""Tests for persistent competition world-state merging."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest import TestCase

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
  sys.path.insert(0, str(SRC))

from sensoragent.state import CompetitionWorldState, ObjectStatus


class CompetitionWorldStateTest(TestCase):
  def test_merge_runtime_state_updates_objects_bins_and_history(self) -> None:
    world = CompetitionWorldState(("bin_cell_3",))

    world.merge_runtime_state(
      {
        "objects": {
          "roller_01": {
            "label": "roller",
            "pose_3d": [0.24, 0.23, 0.142],
            "confidence": 0.91,
            "source": "open_vocab",
            "status": "placed",
            "target": "bin_cell_3",
          }
        },
        "bins": {
          "bin_cell_3": {
            "status": "occupied",
            "occupied_by": "roller_01",
            "observed_position": [0.36, -0.06, 0.30],
          }
        },
        "current_task": {
          "object_id": "roller_01",
          "target": "bin_cell_3",
          "step": "placed",
        },
        "history": [
          {"event": "object_observed"},
          {"event": "object_placed_in_target"},
        ],
      }
    )

    self.assertEqual(world.objects["roller_01"].status, ObjectStatus.PLACED)
    self.assertEqual(world.objects["roller_01"].confidence, 0.91)
    self.assertEqual(world.bins["bin_cell_3"].occupied_by, "roller_01")
    self.assertEqual(world.bins["bin_cell_3"].observed_position, (0.36, -0.06, 0.30))
    self.assertEqual(world.current_task["step"], "placed")
    self.assertIn("runtime_world_state_merged", [entry["event"] for entry in world.history])
