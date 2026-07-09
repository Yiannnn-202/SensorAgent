"""Unit tests for audio integration clients and tools."""

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
from sensoragent.integrations import FakeAudioClient, FakeMicrophoneRecorder
from sensoragent.schemas import ToolCall, TraceContext
from sensoragent.tools.audio import AudioSpeakTool, AudioTranscribeTool
from sensoragent.tools.audio import AudioListenTranscribeTool


class AudioIntegrationTest(TestCase):
  def test_fake_audio_client_transcribes_and_speaks(self) -> None:
    client = FakeAudioClient()

    transcript = client.transcribe_file("tests/fixtures/audio/command.wav", "zh")
    speech = client.speak_text("任务已完成", "logs/audio/fake.wav")

    self.assertEqual(transcript["language"], "zh")
    self.assertIn("银色滚柱", transcript["text"])
    self.assertTrue(speech["spoken"])
    self.assertEqual(speech["audio_path"], "logs/audio/fake.wav")

  def test_audio_transcribe_tool_uses_client(self) -> None:
    tool = AudioTranscribeTool(FakeAudioClient())

    result = tool.run(
      ToolCall(
        tool="audio.transcribe",
        input={"audio_path": "tests/fixtures/audio/command.wav", "language": "zh"},
        trace=TraceContext(),
      )
    )

    self.assertTrue(result.success)
    self.assertEqual(result.output["language"], "zh")

  def test_audio_listen_transcribe_tool_records_and_transcribes(self) -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
      output_path = str(Path(temp_dir) / "listen.wav")
      tool = AudioListenTranscribeTool(FakeMicrophoneRecorder(), FakeAudioClient())

      result = tool.run(
        ToolCall(
          tool="audio.listen_transcribe",
          input={
            "duration_seconds": 1,
            "language": "zh",
            "output_path": output_path,
          },
          trace=TraceContext(),
        )
      )

      self.assertTrue(result.success)
      self.assertEqual(result.output["audio_path"], output_path)
      self.assertIn("银色滚柱", result.output["text"])
      self.assertTrue(Path(output_path).exists())

  def test_audio_speak_tool_uses_client(self) -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
      output_path = str(Path(temp_dir) / "speech.wav")
      tool = AudioSpeakTool(FakeAudioClient())

      result = tool.run(
        ToolCall(
          tool="audio.speak",
          input={"text": "任务已完成", "output_path": output_path, "play": False},
          trace=TraceContext(),
        )
      )

      self.assertTrue(result.success)
      self.assertEqual(result.output["audio_path"], output_path)

  def test_audio_mock_config_registers_audio_tools(self) -> None:
    bundle = build_agent_from_config(ROOT / "configs" / "audio_mock.yaml")

    self.assertIn("audio.transcribe", bundle.tool_registry.names())
    self.assertIn("audio.speak", bundle.tool_registry.names())
