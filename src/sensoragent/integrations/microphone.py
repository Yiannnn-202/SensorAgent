"""Microphone recording integrations."""

from __future__ import annotations

import shutil
import wave
from pathlib import Path
from typing import Protocol


class MicrophoneError(Exception):
  """Base class for microphone recording errors."""


class MicrophoneRecorder(Protocol):
  """Interface for fixed-duration microphone recording."""

  def record_once(
    self,
    duration_seconds: float,
    output_path: str,
    sample_rate: int = 16000,
  ) -> dict:
    """Record one utterance into a WAV file."""


class FakeMicrophoneRecorder:
  """Recorder used by tests; copies the committed WAV fixture."""

  def __init__(self, fixture_path: str = "tests/fixtures/audio/command.wav") -> None:
    self._fixture_path = Path(fixture_path)

  def record_once(
    self,
    duration_seconds: float,
    output_path: str,
    sample_rate: int = 16000,
  ) -> dict:
    if not self._fixture_path.is_file():
      raise MicrophoneError(f"Microphone fixture not found: {self._fixture_path}")
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(self._fixture_path, destination)
    duration_ms = 0
    with wave.open(str(destination), "rb") as wav:
      duration_ms = int(wav.getnframes() / float(wav.getframerate()) * 1000)
    return {
      "audio_path": str(destination),
      "duration_ms": duration_ms,
      "sample_rate": sample_rate,
    }


class SoundDeviceRecorder:
  """Fixed-duration recorder backed by the local system microphone."""

  def record_once(
    self,
    duration_seconds: float,
    output_path: str,
    sample_rate: int = 16000,
  ) -> dict:
    try:
      import numpy as np
      import sounddevice as sd
    except Exception as exc:
      raise MicrophoneError("sounddevice and numpy are required for microphone input") from exc

    if duration_seconds <= 0:
      raise MicrophoneError("duration_seconds must be positive")

    frames = int(duration_seconds * sample_rate)
    audio = sd.rec(frames, samplerate=sample_rate, channels=1, dtype="int16")
    sd.wait()
    samples = np.asarray(audio).reshape(-1)

    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(destination), "wb") as wav:
      wav.setnchannels(1)
      wav.setsampwidth(2)
      wav.setframerate(sample_rate)
      wav.writeframes(samples.tobytes())

    return {
      "audio_path": str(destination),
      "duration_ms": int(duration_seconds * 1000),
      "sample_rate": sample_rate,
    }
