"""Tests for the hardware place-target recording helper."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

import yaml


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "linux" / "record_hardware_place_target.py"


def _load_module():
  spec = importlib.util.spec_from_file_location("record_hardware_place_target", SCRIPT)
  module = importlib.util.module_from_spec(spec)
  assert spec is not None and spec.loader is not None
  spec.loader.exec_module(module)
  return module


class RecordHardwarePlaceTargetScriptTest(TestCase):
  def test_render_snippet_uses_scene_place_targets_shape(self) -> None:
    module = _load_module()
    pose = {
      "position": [-0.1, -0.2, 0.3],
      "orientation": [0.0, 1.0, 0.0, 0.0],
      "frame_id": "base_link",
    }

    rendered = module._render_snippet("bin_cell_1", pose)

    payload = yaml.safe_load(rendered)
    self.assertEqual(payload["scene"]["place_targets"]["bin_cell_1"], pose)

  def test_update_config_preserves_existing_targets(self) -> None:
    module = _load_module()
    with TemporaryDirectory() as tmp_dir:
      config_path = Path(tmp_dir) / "hardware.yaml"
      config_path.write_text(
        yaml.safe_dump(
          {
            "agent": {"mode": "robot_hardware"},
            "scene": {
              "place_targets": {
                "bin_cell_4": {
                  "position": [-0.3, -0.1, 0.2],
                  "orientation": [0.9, 0.1, 0.0, 0.0],
                  "frame_id": "base_link",
                }
              }
            },
          },
          sort_keys=False,
        ),
        encoding="utf-8",
      )
      pose = {
        "position": [-0.2, -0.1, 0.25],
        "orientation": [0.9, 0.1, 0.0, 0.0],
        "frame_id": "base_link",
      }

      module._update_config(config_path, "bin_cell_1", pose)

      payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
      targets = payload["scene"]["place_targets"]
      self.assertEqual(targets["bin_cell_1"], pose)
      self.assertIn("bin_cell_4", targets)
