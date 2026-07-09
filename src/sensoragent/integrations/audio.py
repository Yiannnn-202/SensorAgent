"""Audio integration clients for ASR and TTS."""

from __future__ import annotations

import re
import shutil
import struct
import subprocess
import wave
from pathlib import Path
from typing import Protocol


class AudioError(Exception):
  """Base class for audio integration errors."""


class AudioInputError(AudioError):
  """Raised when audio input is invalid or missing."""


class AudioModelError(AudioError):
  """Raised when local model files or model dependencies are unavailable."""


class AudioClient(Protocol):
  """Audio integration interface used by audio tools."""

  def transcribe_file(self, audio_path: str, language: str = "zh") -> dict:
    """Transcribe an audio file into text."""

  def speak_text(
    self,
    text: str,
    output_path: str | None = None,
    voice: str = "default",
    play: bool = False,
  ) -> dict:
    """Synthesize speech from text."""


class FakeAudioClient:
  """Deterministic audio client for tests and local Agent dry-runs."""

  def transcribe_file(self, audio_path: str, language: str = "zh") -> dict:
    return {
      "text": "把银色滚柱放到第三个格子",
      "confidence": 0.94,
      "language": language,
    }

  def speak_text(
    self,
    text: str,
    output_path: str | None = None,
    voice: str = "default",
    play: bool = False,
  ) -> dict:
    return {
      "spoken": True,
      "audio_path": output_path or "logs/audio/fake_tts.wav",
      "duration_ms": 1200,
    }


_HALLUCINATION_BLACKLIST = {"mm", "hmm", "uh", "um", "the the", "yeah yeah"}


def _clean_sensevoice_tags(text: str) -> str:
  return re.sub(r"<\|.*?\|>", "", text).strip()


def _is_hallucination(text: str) -> bool:
  text = text.strip()
  if len(text) <= 1:
    return True
  words = text.lower().split()
  if len(words) > 3 and words[0] == words[1] == words[2]:
    return True
  return text.lower() in _HALLUCINATION_BLACKLIST


def _read_mono_16k_wav(path: Path):
  try:
    import numpy as np
  except Exception as exc:
    raise AudioModelError("numpy is required for local ASR") from exc

  if not path.is_file():
    raise AudioInputError(f"Audio file not found: {path}")

  with wave.open(str(path), "rb") as wav:
    if wav.getnchannels() != 1:
      raise AudioInputError("Only mono WAV input is currently supported")
    if wav.getframerate() != 16000:
      raise AudioInputError("Only 16 kHz WAV input is currently supported")
    if wav.getsampwidth() != 2:
      raise AudioInputError("Only 16-bit PCM WAV input is currently supported")
    frames = wav.readframes(wav.getnframes())

  samples = [
    struct.unpack_from("<h", frames, offset)[0] / 32768.0
    for offset in range(0, len(frames), 2)
  ]
  return np.asarray(samples, dtype=np.float32)


class LocalAudioClient:
  """Local model-backed ASR/TTS client.

  ASR uses SenseVoice through sherpa-onnx. TTS currently supports the Piper-VITS
  layout used by the reviewed Radish TTS server. The Baker/icefall TTS layout
  is detected and reported as unsupported until its sherpa-onnx backend is
  confirmed.
  """

  def __init__(
    self,
    asr_model_dir: str = "models/asr/sense-voice",
    tts_model_dir: str = "models/tts",
    asr_provider: str = "cpu",
    asr_num_threads: int = 4,
  ) -> None:
    self._asr_model_dir = Path(asr_model_dir)
    self._tts_model_dir = Path(tts_model_dir)
    self._asr_provider = asr_provider
    self._asr_num_threads = asr_num_threads
    self._recognizers: dict[str, object] = {}
    self._tts_engine = None
    self._tts_voice = "default"

  def _load_asr(self, language: str):
    if language in self._recognizers:
      return self._recognizers[language]

    try:
      import sherpa_onnx
    except Exception as exc:
      raise AudioModelError("sherpa_onnx is required for local ASR") from exc

    model_path = self._asr_model_dir / "model.int8.onnx"
    tokens_path = self._asr_model_dir / "tokens.txt"
    if not model_path.is_file() or not tokens_path.is_file():
      raise AudioModelError(f"SenseVoice model files missing under {self._asr_model_dir}")

    recognizer = sherpa_onnx.OfflineRecognizer.from_sense_voice(
      model=str(model_path),
      tokens=str(tokens_path),
      num_threads=self._asr_num_threads,
      provider=self._asr_provider,
      language=language,
      use_itn=True,
    )
    self._recognizers[language] = recognizer
    return recognizer

  def transcribe_file(self, audio_path: str, language: str = "zh") -> dict:
    audio = _read_mono_16k_wav(Path(audio_path))
    recognizer = self._load_asr(language)

    stream = recognizer.create_stream()
    stream.accept_waveform(16000, audio.tolist())
    recognizer.decode_stream(stream)

    raw_text = stream.result.text.strip()
    clean_text = _clean_sensevoice_tags(raw_text) if raw_text else ""
    if not clean_text or _is_hallucination(clean_text):
      clean_text = ""

    return {
      "text": clean_text,
      "confidence": 1.0 if clean_text else 0.0,
      "language": language,
    }

  def _find_vits_assets(self) -> tuple[Path, Path, Path] | None:
    candidates = [
      self._tts_model_dir,
      self._tts_model_dir / "vits-piper-en_US-glados",
    ]
    for directory in candidates:
      model_path = directory / "en_US-glados.onnx"
      tokens_path = directory / "tokens.txt"
      data_dir = directory / "espeak-ng-data"
      if model_path.is_file() and tokens_path.is_file() and data_dir.is_dir():
        return model_path, tokens_path, data_dir
    return None

  def _load_tts(self):
    if self._tts_engine is not None:
      return self._tts_engine

    try:
      import sherpa_onnx
    except Exception as exc:
      raise AudioModelError("sherpa_onnx is required for local TTS") from exc

    vits_assets = self._find_vits_assets()
    if vits_assets is None:
      if (self._tts_model_dir / "model-steps-3.onnx").exists():
        raise AudioModelError(
          "Detected Baker/icefall TTS assets, but this backend is not wired yet"
        )
      raise AudioModelError(f"TTS model assets missing under {self._tts_model_dir}")

    model_path, tokens_path, data_dir = vits_assets
    config = sherpa_onnx.OfflineTtsConfig(
      model=sherpa_onnx.OfflineTtsModelConfig(
        vits=sherpa_onnx.OfflineTtsVitsModelConfig(
          model=str(model_path),
          tokens=str(tokens_path),
          data_dir=str(data_dir),
        ),
        num_threads=2,
        debug=False,
        provider="cpu",
      ),
      rule_fsts="",
      max_num_sentences=1,
    )
    self._tts_engine = sherpa_onnx.OfflineTts(config)
    self._tts_voice = "vits-piper"
    return self._tts_engine

  def _speak_with_cli(self, text: str, output_path: str | None) -> dict | None:
    acoustic_model = self._tts_model_dir / "model-steps-3.onnx"
    vocoder = self._tts_model_dir / "vocos-22khz-univ.onnx"
    if not acoustic_model.is_file() or not vocoder.is_file():
      return None

    executable = shutil.which("sherpa-onnx-offline-tts")
    if executable is None:
      raise AudioModelError(
        "Detected Baker/icefall TTS assets, but sherpa-onnx-offline-tts is not installed"
      )

    destination = Path(output_path or "logs/audio/tts_output.wav")
    destination.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
      [
        executable,
        "--model",
        str(acoustic_model),
        "--vocoder",
        str(vocoder),
        "--text",
        text,
        "--output",
        str(destination),
      ],
      check=True,
      capture_output=True,
      text=True,
    )
    duration_ms = 0
    try:
      with wave.open(str(destination), "rb") as wav:
        duration_ms = int(wav.getnframes() / float(wav.getframerate()) * 1000)
    except Exception:
      duration_ms = 0
    return {
      "spoken": True,
      "audio_path": str(destination),
      "duration_ms": duration_ms,
    }

  def speak_text(
    self,
    text: str,
    output_path: str | None = None,
    voice: str = "default",
    play: bool = False,
  ) -> dict:
    if play:
      raise AudioInputError("Local playback is intentionally disabled in SensorAgent")
    if not text:
      raise AudioInputError("TTS text is required")

    cli_result = self._speak_with_cli(text, output_path)
    if cli_result is not None:
      return cli_result

    try:
      import numpy as np
    except Exception as exc:
      raise AudioModelError("numpy is required for local TTS") from exc

    tts = self._load_tts()
    audio = tts.generate(text)
    samples = np.asarray(audio.samples)
    if samples.size == 0:
      raise AudioModelError("TTS produced no audio")

    destination = Path(output_path or "logs/audio/tts_output.wav")
    destination.parent.mkdir(parents=True, exist_ok=True)
    _write_wav(destination, samples, int(audio.sample_rate))
    duration_ms = int(samples.shape[0] / float(audio.sample_rate) * 1000)
    return {
      "spoken": True,
      "audio_path": str(destination),
      "duration_ms": duration_ms,
    }


def _write_wav(path: Path, samples, sample_rate: int) -> None:
  import numpy as np

  samples_int16 = (np.clip(samples, -1.0, 1.0) * 32767).astype(np.int16)
  with wave.open(str(path), "wb") as wav:
    wav.setnchannels(1)
    wav.setsampwidth(2)
    wav.setframerate(sample_rate)
    wav.writeframes(samples_int16.tobytes())
