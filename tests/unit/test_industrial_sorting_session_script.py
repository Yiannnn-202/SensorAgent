"""Tests for the persistent industrial sorting session loop."""

from __future__ import annotations

import importlib.util
from dataclasses import replace
from io import StringIO
from pathlib import Path
from unittest import TestCase


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "linux" / "run_industrial_sorting_session.py"


def _load_module():
  spec = importlib.util.spec_from_file_location("run_industrial_sorting_session", SCRIPT)
  module = importlib.util.module_from_spec(spec)
  assert spec is not None and spec.loader is not None
  spec.loader.exec_module(module)
  return module


def _build_text_bundle(module):
  config = module.load_config(ROOT / "configs" / "robot_sorting_sim.yaml")
  config = replace(
    config,
    logging=replace(config.logging, console=False),
  )
  active_config = module.prepare_session_config(
    config,
    execute=False,
    voice_enabled=False,
  )
  return module.build_agent(active_config)


class IndustrialSortingSessionScriptTest(TestCase):
  def test_text_config_removes_audio_assets_for_dry_run(self) -> None:
    module = _load_module()
    config = module.load_config(ROOT / "configs" / "robot_sorting_sim.yaml")

    active_config = module.prepare_session_config(
      config,
      execute=False,
      voice_enabled=False,
    )

    self.assertEqual(active_config.integrations.robot["backend"], "fake")
    self.assertFalse(
      any(name.startswith("audio.") for name in active_config.tools.enabled)
    )
    self.assertFalse(
      any(name.startswith("audio.") for name in active_config.skills.enabled)
    )

  def test_control_commands_are_recognized(self) -> None:
    module = _load_module()

    self.assertTrue(module.is_exit_command("退出"))
    self.assertTrue(module.is_exit_command(" exit "))
    self.assertTrue(module.is_status_command("状态"))
    self.assertTrue(module.is_status_command(" status "))

  def test_runs_one_text_sorting_turn_with_fake_robot(self) -> None:
    module = _load_module()
    bundle = _build_text_bundle(module)

    result = module.run_sorting_turn(bundle, "把方块放到1号格", turn_index=0)

    self.assertTrue(result["success"], result.get("error"))
    self.assertEqual(
      result["command"],
      {"object_query": "方块", "target": "bin_cell_1"},
    )
    self.assertEqual(result["type"], "command")

  def test_text_loop_continues_until_exit(self) -> None:
    module = _load_module()
    bundle = _build_text_bundle(module)
    output = StringIO()

    code = module.run_text_loop(
      bundle,
      input_stream=StringIO("把方块放到1号格\nexit\n"),
      output_stream=output,
      prompt_stream=StringIO(),
    )

    self.assertEqual(code, 0)
    rendered = output.getvalue()
    self.assertIn('"type": "command"', rendered)
    self.assertIn('"type": "exit"', rendered)
