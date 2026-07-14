"""Unit tests for audio skills and voice ActionLists."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest import TestCase

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
  sys.path.insert(0, str(SRC))

from sensoragent.agent import build_agent_from_config
from sensoragent.schemas import TraceContext


class AudioSkillsTest(TestCase):
  def test_audio_mock_config_registers_voice_tools_and_skills(self) -> None:
    bundle = build_agent_from_config(ROOT / "configs" / "audio_mock.yaml")

    self.assertIn("audio.listen_vad_transcribe", bundle.tool_registry.names())
    self.assertIn("audio.listen_command", bundle.skill_registry.names())
    self.assertIn("audio.announce", bundle.skill_registry.names())
    self.assertIn("audio.voice_command_ack_actionlist", bundle.actionlists)

  def test_listen_command_skill_invokes_audio_tool(self) -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
      output_path = str(Path(temp_dir) / "command.wav")
      bundle = build_agent_from_config(ROOT / "configs" / "audio_mock.yaml")

      result = bundle.skill_runtime.invoke(
        "audio.listen_command",
        {
          "duration_seconds": 1,
          "language": "zh",
          "output_path": output_path,
        },
        TraceContext(),
      )

      self.assertTrue(result.success)
      self.assertEqual(result.output["text"], result.output["command_text"])
      self.assertEqual(result.output["audio_path"], output_path)
      self.assertTrue(Path(output_path).exists())

  def test_announce_skill_invokes_tts_tool(self) -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
      output_path = str(Path(temp_dir) / "announce.wav")
      bundle = build_agent_from_config(ROOT / "configs" / "audio_mock.yaml")

      result = bundle.skill_runtime.invoke(
        "audio.announce",
        {
          "kind": "task_success",
          "output_path": output_path,
          "play": False,
        },
        TraceContext(),
      )

      self.assertTrue(result.success)
      self.assertTrue(result.output["spoken"])
      self.assertEqual(result.output["audio_path"], output_path)
      self.assertEqual(result.output["text"], "任务已完成")

  def test_voice_command_ack_actionlist_runs_audio_skills(self) -> None:
    bundle = build_agent_from_config(ROOT / "configs" / "audio_mock.yaml")

    result = bundle.actionlist_runtime.run(
      bundle.actionlists["audio.voice_command_ack_actionlist"],
      {"duration_seconds": 1, "language": "zh"},
      TraceContext(),
    )

    self.assertTrue(result.success)
    self.assertIn("command", result.output)
    self.assertIn("announcement", result.output)
