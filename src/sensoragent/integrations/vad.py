"""Voice activity detection integrations."""

from __future__ import annotations

import wave
from collections import deque
from pathlib import Path
from queue import Empty, Queue
from typing import Protocol


class VadError(Exception):
  """Base class for VAD integration errors."""


class VadSegmenter(Protocol):
  """Interface for segmenting one speech utterance from a WAV file."""

  def segment_wav(self, audio_path: str, output_path: str | None = None) -> dict:
    """Return one speech segment from a WAV file."""


def _read_mono_16k_wav(path: Path):
  try:
    import numpy as np
  except Exception as exc:
    raise VadError("numpy is required for VAD") from exc

  if not path.is_file():
    raise VadError(f"Audio file not found: {path}")

  with wave.open(str(path), "rb") as wav:
    if wav.getnchannels() != 1:
      raise VadError("Only mono WAV input is currently supported for VAD")
    if wav.getframerate() != 16000:
      raise VadError("Only 16 kHz WAV input is currently supported for VAD")
    if wav.getsampwidth() != 2:
      raise VadError("Only 16-bit PCM WAV input is currently supported for VAD")
    frames = wav.readframes(wav.getnframes())

  samples = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
  return samples


def _write_mono_16k_wav(path: Path, samples) -> None:
  import numpy as np

  path.parent.mkdir(parents=True, exist_ok=True)
  samples_int16 = (np.clip(samples, -1.0, 1.0) * 32767).astype(np.int16)
  with wave.open(str(path), "wb") as wav:
    wav.setnchannels(1)
    wav.setsampwidth(2)
    wav.setframerate(16000)
    wav.writeframes(samples_int16.tobytes())


class SileroVadSegmenter:
  """Segment one speech utterance using a local Silero VAD ONNX model."""

  def __init__(
    self,
    model_path: str = "models/asr/vad/silero_vad.onnx",
    threshold: float = 0.5,
    min_speech_windows: int = 3,
    pre_roll_ms: int = 120,
    post_roll_ms: int = 500,
    max_utterance_sec: float = 15.0,
  ) -> None:
    self._model_path = Path(model_path)
    self._threshold = float(threshold)
    self._min_speech_windows = max(1, int(min_speech_windows))
    self._pre_roll_ms = int(pre_roll_ms)
    self._post_roll_ms = int(post_roll_ms)
    self._max_utterance_sec = float(max_utterance_sec)
    self._pre_roll_samples = int(16000 * int(pre_roll_ms) / 1000)
    self._post_roll_samples = int(16000 * int(post_roll_ms) / 1000)
    self._max_utterance_samples = int(16000 * float(max_utterance_sec))
    self._window_samples = 512

    if not self._model_path.is_file():
      raise VadError(f"VAD model file not found: {self._model_path}")
    try:
      import numpy as np
      import onnxruntime as ort
    except Exception as exc:
      raise VadError("onnxruntime and numpy are required for VAD") from exc

    providers = (
      ["CPUExecutionProvider"]
      if "CPUExecutionProvider" in set(ort.get_available_providers())
      else None
    )
    self._session = (
      ort.InferenceSession(str(self._model_path), providers=providers)
      if providers
      else ort.InferenceSession(str(self._model_path))
    )
    self._inputs = {item.name: item for item in self._session.get_inputs()}
    self._audio_input_name = self._resolve_audio_input_name()
    self._use_split_state = {"h0", "c0"}.issubset(self._inputs)
    self._use_short_split_state = (
      not self._use_split_state and {"h", "c"}.issubset(self._inputs)
    )
    self._use_combined_state = (
      not self._use_split_state
      and not self._use_short_split_state
      and "state" in self._inputs
    )
    self._sr_value = self._make_sample_rate_value(np)
    self._reset_state(np)

  def _resolve_audio_input_name(self) -> str:
    for name in self._inputs:
      if name not in {"h0", "c0", "h", "c", "state", "sr"}:
        return name
    return next(iter(self._inputs))

  def _resolved_shape(self, input_name: str, fallback: tuple[int, ...]) -> tuple[int, ...]:
    item = self._inputs[input_name]
    dims: list[int] = []
    for index, dim in enumerate(item.shape):
      if isinstance(dim, int) and dim > 0:
        dims.append(dim)
      elif index < len(fallback):
        dims.append(fallback[index])
      else:
        dims.append(1)
    return tuple(dims)

  def _make_sample_rate_value(self, np):
    if "sr" not in self._inputs:
      return None
    shape = self._inputs["sr"].shape
    if len(shape) == 0:
      return np.array(16000, dtype=np.int64)
    return np.array([16000], dtype=np.int64)

  def _reset_state(self, np) -> None:
    if self._use_split_state:
      self._h = np.zeros(self._resolved_shape("h0", (2, 1, 64)), dtype=np.float32)
      self._c = np.zeros(self._resolved_shape("c0", (2, 1, 64)), dtype=np.float32)
    elif self._use_short_split_state:
      self._h = np.zeros(self._resolved_shape("h", (2, 1, 64)), dtype=np.float32)
      self._c = np.zeros(self._resolved_shape("c", (2, 1, 64)), dtype=np.float32)
    elif self._use_combined_state:
      self._state = np.zeros(self._resolved_shape("state", (2, 1, 128)), dtype=np.float32)

  def _run_window(self, chunk) -> float:
    import numpy as np

    ort_inputs = {
      self._audio_input_name: chunk[np.newaxis, :].astype(np.float32),
    }
    if self._sr_value is not None:
      ort_inputs["sr"] = self._sr_value
    if self._use_split_state:
      ort_inputs["h0"] = self._h
      ort_inputs["c0"] = self._c
    elif self._use_short_split_state:
      ort_inputs["h"] = self._h
      ort_inputs["c"] = self._c
    elif self._use_combined_state:
      ort_inputs["state"] = self._state

    outputs = self._session.run(None, ort_inputs)
    prob = float(np.asarray(outputs[0]).reshape(-1)[0]) if outputs else 0.0
    if (self._use_split_state or self._use_short_split_state) and len(outputs) >= 3:
      self._h = np.asarray(outputs[1], dtype=np.float32)
      self._c = np.asarray(outputs[2], dtype=np.float32)
    elif self._use_combined_state and len(outputs) >= 2:
      self._state = np.asarray(outputs[1], dtype=np.float32)
    return prob

  def reset(self) -> None:
    import numpy as np

    self._reset_state(np)

  def speech_probability(self, chunk) -> float:
    import numpy as np

    samples = np.asarray(chunk, dtype=np.float32).reshape(-1)
    if samples.size < self._window_samples:
      samples = np.pad(samples, (0, self._window_samples - samples.size))
    elif samples.size > self._window_samples:
      samples = samples[: self._window_samples]
    return self._run_window(samples)

  def segment_wav(self, audio_path: str, output_path: str | None = None) -> dict:
    import numpy as np

    self._reset_state(np)
    source = Path(audio_path)
    samples = _read_mono_16k_wav(source)
    if samples.size == 0:
      raise VadError("No audio samples available for VAD")

    padded = np.concatenate(
      [samples, np.zeros(self._post_roll_samples + self._window_samples, dtype=np.float32)]
    )
    speech_start: int | None = None
    speech_end: int | None = None
    consecutive_speech = 0
    consecutive_silence = 0

    for start in range(0, padded.size - self._window_samples + 1, self._window_samples):
      window = padded[start : start + self._window_samples]
      is_speech = self._run_window(window) >= self._threshold
      if is_speech:
        consecutive_speech += 1
        consecutive_silence = 0
      else:
        consecutive_silence += 1

      if speech_start is None:
        if consecutive_speech >= self._min_speech_windows:
          raw_start = start - ((self._min_speech_windows - 1) * self._window_samples)
          speech_start = max(0, raw_start - self._pre_roll_samples)
      else:
        max_end = speech_start + self._max_utterance_samples
        if start >= max_end:
          speech_end = min(samples.size, max_end)
          break
        if (
          not is_speech
          and consecutive_silence * self._window_samples >= self._post_roll_samples
        ):
          speech_end = min(samples.size, start + self._window_samples)
          break

    if speech_start is None:
      raise VadError("NO_SPEECH_DETECTED")
    if speech_end is None:
      speech_end = min(samples.size, speech_start + self._max_utterance_samples)
    if speech_end <= speech_start:
      raise VadError("NO_SPEECH_DETECTED")

    segment = samples[speech_start:speech_end]
    destination = (
      Path(output_path)
      if output_path is not None
      else source.with_name(f"{source.stem}_utterance.wav")
    )
    _write_mono_16k_wav(destination, segment)
    return {
      "audio_path": str(destination),
      "start_ms": int(speech_start * 1000 / 16000),
      "end_ms": int(speech_end * 1000 / 16000),
      "duration_ms": int(segment.size * 1000 / 16000),
      "sample_rate": 16000,
    }


class SoundDeviceVadRecorder:
  """Record one utterance and stop when Silero VAD detects speech end."""

  def __init__(
    self,
    model_path: str = "models/asr/vad/silero_vad.onnx",
    threshold: float = 0.35,
    min_speech_windows: int = 2,
    pre_roll_ms: int = 120,
    post_roll_ms: int = 1800,
    tail_padding_ms: int = 700,
    max_utterance_sec: float = 15.0,
  ) -> None:
    self._segmenter = SileroVadSegmenter(
      model_path=model_path,
      threshold=threshold,
      min_speech_windows=min_speech_windows,
      pre_roll_ms=pre_roll_ms,
      post_roll_ms=post_roll_ms,
      max_utterance_sec=max_utterance_sec,
    )
    self._threshold = float(threshold)
    self._min_speech_windows = max(1, int(min_speech_windows))
    self._pre_roll_ms = int(pre_roll_ms)
    self._post_roll_ms = int(post_roll_ms)
    self._tail_padding_ms = int(tail_padding_ms)
    self._max_utterance_sec = float(max_utterance_sec)
    self._pre_roll_windows = max(
      1,
      int((int(pre_roll_ms) / 1000) * 16000 / self._segmenter._window_samples) + 1,
    )
    self._post_roll_samples = int(16000 * int(post_roll_ms) / 1000)
    self._tail_padding_samples = int(16000 * int(tail_padding_ms) / 1000)
    self._max_utterance_samples = int(16000 * float(max_utterance_sec))
    self._window_samples = self._segmenter._window_samples

  def with_overrides(self, overrides: dict | None):
    if not overrides:
      return self
    return SoundDeviceVadRecorder(
      model_path=str(self._segmenter._model_path),
      threshold=float(overrides.get("threshold", self._threshold)),
      min_speech_windows=int(
        overrides.get("min_speech_windows", self._min_speech_windows)
      ),
      pre_roll_ms=int(overrides.get("pre_roll_ms", self._pre_roll_ms)),
      post_roll_ms=int(overrides.get("post_roll_ms", self._post_roll_ms)),
      tail_padding_ms=int(overrides.get("tail_padding_ms", self._tail_padding_ms)),
      max_utterance_sec=float(
        overrides.get("max_utterance_sec", self._max_utterance_sec)
      ),
    )

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
      raise VadError("sounddevice and numpy are required for VAD microphone input") from exc

    if sample_rate != 16000:
      raise VadError("VAD microphone input currently requires 16 kHz sample rate")
    if duration_seconds <= 0:
      raise VadError("duration_seconds must be positive")

    self._segmenter.reset()
    audio_queue: Queue = Queue()

    def _callback(indata, frames, time_info, status) -> None:
      del frames, time_info
      if status:
        # Keep recording; sounddevice status is often recoverable.
        pass
      audio_queue.put(np.asarray(indata).reshape(-1).copy())

    pre_roll = deque(maxlen=self._pre_roll_windows + self._min_speech_windows)
    utterance_chunks: list = []
    speech_started = False
    consecutive_speech = 0
    consecutive_silence = 0
    samples_seen = 0
    speech_start_sample = 0
    max_samples = int(duration_seconds * sample_rate)

    with sd.InputStream(
      samplerate=sample_rate,
      channels=1,
      dtype="int16",
      blocksize=self._window_samples,
      callback=_callback,
    ):
      while samples_seen < max_samples:
        try:
          chunk_int16 = audio_queue.get(timeout=0.5)
        except Empty:
          continue

        if chunk_int16.size < self._window_samples:
          chunk_int16 = np.pad(chunk_int16, (0, self._window_samples - chunk_int16.size))
        elif chunk_int16.size > self._window_samples:
          chunk_int16 = chunk_int16[: self._window_samples]

        chunk = chunk_int16.astype(np.float32) / 32768.0
        prob = self._segmenter.speech_probability(chunk)
        is_speech = prob >= self._threshold
        samples_seen += self._window_samples

        if not speech_started:
          pre_roll.append(chunk.copy())
          if is_speech:
            consecutive_speech += 1
          else:
            consecutive_speech = 0
          if consecutive_speech >= self._min_speech_windows:
            speech_started = True
            utterance_chunks = list(pre_roll)
            speech_start_sample = max(
              0,
              samples_seen - sum(item.size for item in utterance_chunks),
            )
            consecutive_silence = 0
          continue

        utterance_chunks.append(chunk.copy())
        utterance_samples = sum(item.size for item in utterance_chunks)
        if is_speech:
          consecutive_silence = 0
        else:
          consecutive_silence += self._window_samples

        if (
          consecutive_silence >= self._post_roll_samples
          and utterance_samples + self._window_samples >= self._post_roll_samples
        ):
          break
        if utterance_samples >= self._max_utterance_samples:
          break

    if not speech_started or not utterance_chunks:
      raise VadError("NO_SPEECH_DETECTED")

    samples = np.concatenate(utterance_chunks)
    if samples.size > self._max_utterance_samples:
      samples = samples[: self._max_utterance_samples]
    if self._tail_padding_samples > 0:
      samples = np.concatenate(
        [samples, np.zeros(self._tail_padding_samples, dtype=np.float32)]
      )

    destination = Path(output_path)
    _write_mono_16k_wav(destination, samples)
    duration_ms = int(samples.size * 1000 / sample_rate)
    return {
      "audio_path": str(destination),
      "duration_ms": duration_ms,
      "sample_rate": sample_rate,
      "vad": {
        "enabled": True,
        "source": "silero_realtime",
        "start_ms": int(speech_start_sample * 1000 / sample_rate),
        "end_ms": int((speech_start_sample + samples.size) * 1000 / sample_rate),
        "duration_ms": duration_ms,
      },
    }
