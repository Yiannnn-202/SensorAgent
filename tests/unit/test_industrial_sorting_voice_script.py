"""Tests for the deterministic industrial sorting voice command parser."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest import TestCase
from dataclasses import replace


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "linux" / "run_industrial_sorting_voice_sim.py"


def _load_module():
  spec = importlib.util.spec_from_file_location("run_industrial_sorting_voice_sim", SCRIPT)
  module = importlib.util.module_from_spec(spec)
  assert spec is not None and spec.loader is not None
  spec.loader.exec_module(module)
  return module


class IndustrialSortingVoiceScriptTest(TestCase):
  def test_parses_chinese_object_and_target(self) -> None:
    module = _load_module()
    self.assertEqual(
      module.parse_sorting_command("把短螺栓放到六号格"),
      {"object_query": "短螺栓", "target": "bin_cell_6"},
    )

  def test_parses_supported_alias(self) -> None:
    module = _load_module()
    self.assertEqual(
      module.parse_sorting_command("将滚柱放到第3格"),
      {"object_query": "滚轮", "target": "bin_cell_3"},
    )

  def test_rejects_incomplete_command(self) -> None:
    module = _load_module()
    with self.assertRaises(ValueError):
      module.parse_sorting_command("把方块放好")

  def test_text_mode_config_removes_audio_listen_tools(self) -> None:
    from sensoragent.config import load_config

    module = _load_module()
    config = load_config(ROOT / "configs" / "robot_sorting_sim.yaml")
    config = replace(config, tools=replace(config.tools, enabled=["audio.listen_vad_transcribe", "audio.transcribe", "robot.get_state"]))

    active_config = module._text_mode_config(config)

    self.assertEqual(active_config.tools.enabled, ["audio.transcribe", "robot.get_state"])
  def test_parses_ninth_cell_in_physical_three_by_three_bin(self) -> None:
    module = _load_module()
    self.assertEqual(
      module.parse_sorting_command("把螺母放到九号格"),
      {"object_query": "六角螺母", "target": "bin_cell_9"},
    )
