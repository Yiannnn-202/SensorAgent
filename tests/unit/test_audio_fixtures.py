"""Tests for audio fixtures used by ASR/TTS integration work."""

from __future__ import annotations

import json
import sys
import wave
from pathlib import Path
from unittest import TestCase

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
  sys.path.insert(0, str(SRC))

from sensoragent.contracts import ContractValidator


class AudioFixtureTest(TestCase):
  def test_command_wav_fixture_is_small_mono_16khz(self) -> None:
    path = ROOT / "tests" / "fixtures" / "audio" / "command.wav"

    self.assertTrue(path.exists())
    self.assertLess(path.stat().st_size, 20_000)
    with wave.open(str(path), "rb") as wav:
      self.assertEqual(wav.getnchannels(), 1)
      self.assertEqual(wav.getframerate(), 16_000)
      self.assertEqual(wav.getsampwidth(), 2)

  def test_audio_response_fixtures_match_contracts(self) -> None:
    validator = ContractValidator(ROOT / "contracts")
    transcribe = json.loads(
      (ROOT / "tests" / "fixtures" / "responses" / "audio_transcribe_expected.json")
      .read_text(encoding="utf-8")
    )
    speak = json.loads(
      (ROOT / "tests" / "fixtures" / "responses" / "audio_speak_expected.json")
      .read_text(encoding="utf-8")
    )

    validator.validate_tool_output("audio.transcribe", transcribe)
    validator.validate_tool_output("audio.speak", speak)
