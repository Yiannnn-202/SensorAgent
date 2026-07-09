"""End-to-end tests for audio tools through ToolRuntime."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest import TestCase

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
  sys.path.insert(0, str(SRC))

from sensoragent.agent import build_agent_from_config
from sensoragent.schemas import TraceContext


class AudioToolsPipelineTest(TestCase):
  def test_audio_tools_run_through_tool_runtime(self) -> None:
    bundle = build_agent_from_config(ROOT / "configs" / "audio_mock.yaml")

    asr = bundle.tool_runtime.invoke(
      "audio.transcribe",
      {"audio_path": "tests/fixtures/audio/command.wav", "language": "zh"},
      TraceContext(),
    )
    tts = bundle.tool_runtime.invoke(
      "audio.speak",
      {"text": "任务已完成", "output_path": "logs/audio/fake.wav", "play": False},
      TraceContext(),
    )

    self.assertTrue(asr.success)
    self.assertTrue(tts.success)
    self.assertIn("银色滚柱", asr.output["text"])
    self.assertEqual(tts.output["audio_path"], "logs/audio/fake.wav")
