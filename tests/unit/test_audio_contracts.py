"""Contract tests for ASR/TTS tool payloads."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest import TestCase

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
  sys.path.insert(0, str(SRC))

from sensoragent.contracts import ContractValidator


class AudioContractTest(TestCase):
  def test_audio_transcribe_contract_accepts_expected_payloads(self) -> None:
    validator = ContractValidator(ROOT / "contracts")
    input_data = {
      "audio_path": "tests/fixtures/audio/command.wav",
      "language": "zh",
    }
    output_data = {
      "text": "把银色滚柱放到第三个格子",
      "confidence": 0.94,
      "language": "zh",
    }

    validator.validate_tool_input("audio.transcribe", input_data)
    validator.validate_tool_output("audio.transcribe", output_data)

  def test_audio_speak_contract_accepts_expected_payloads(self) -> None:
    validator = ContractValidator(ROOT / "contracts")
    input_data = {
      "text": "任务已完成",
      "voice": "default",
      "output_path": "logs/audio/task_001.wav",
      "play": False,
    }
    output_data = {
      "spoken": True,
      "audio_path": "logs/audio/task_001.wav",
      "duration_ms": 1200,
    }

    validator.validate_tool_input("audio.speak", input_data)
    validator.validate_tool_output("audio.speak", output_data)

  def test_audio_listen_transcribe_contract_accepts_expected_payloads(self) -> None:
    validator = ContractValidator(ROOT / "contracts")
    input_data = {
      "duration_seconds": 5,
      "sample_rate": 16000,
      "language": "zh",
      "output_path": "logs/audio/listen.wav",
    }
    output_data = {
      "audio_path": "logs/audio/listen.wav",
      "duration_ms": 250,
      "sample_rate": 16000,
      "text": "把银色滚柱放到第三个格子",
      "confidence": 0.94,
      "language": "zh",
    }

    validator.validate_tool_input("audio.listen_transcribe", input_data)
    validator.validate_tool_output("audio.listen_transcribe", output_data)
