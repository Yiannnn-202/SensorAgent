"""Diagnose local microphone, VAD, and ASR without running the Agent.

Run from the repository root:

  PYTHONPATH=src .venv312/bin/python scripts/linux/test_audio_input_pipeline.py --mode raw
  PYTHONPATH=src .venv312/bin/python scripts/linux/test_audio_input_pipeline.py --mode vad
  PYTHONPATH=src .venv312/bin/python scripts/linux/test_audio_input_pipeline.py --mode asr --audio-path logs/audio/raw_probe.wav
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import wave
from datetime import UTC, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
  sys.path.insert(0, str(SRC))

from sensoragent.config import load_config
from sensoragent.integrations import LocalAudioClient, SoundDeviceVadRecorder


def _progress(message: str) -> None:
  print(message, file=sys.stderr, flush=True)


def _default_audio_path(prefix: str) -> Path:
  timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
  return ROOT / "logs" / "audio" / f"{prefix}_{timestamp}.wav"


def _write_mono_16k_wav(path: Path, samples) -> None:
  import numpy as np

  path.parent.mkdir(parents=True, exist_ok=True)
  samples = np.asarray(samples, dtype=np.int16).reshape(-1)
  with wave.open(str(path), "wb") as wav:
    wav.setnchannels(1)
    wav.setsampwidth(2)
    wav.setframerate(16000)
    wav.writeframes(samples.tobytes())


def _audio_stats(samples) -> dict:
  import numpy as np

  float_samples = np.asarray(samples, dtype=np.float32).reshape(-1) / 32768.0
  if float_samples.size == 0:
    return {"samples": 0, "rms": 0.0, "peak": 0.0}
  rms = float(math.sqrt(float(np.mean(np.square(float_samples)))))
  peak = float(np.max(np.abs(float_samples)))
  return {
    "samples": int(float_samples.size),
    "duration_ms": int(float_samples.size * 1000 / 16000),
    "rms": rms,
    "peak": peak,
  }


def _record_raw(duration_seconds: float, output_path: Path) -> dict:
  import numpy as np
  import sounddevice as sd

  frames = int(duration_seconds * 16000)
  _progress(f"[audio] raw recording start duration={duration_seconds:.1f}s")
  audio = sd.rec(frames, samplerate=16000, channels=1, dtype="int16")
  sd.wait()
  samples = np.asarray(audio, dtype=np.int16).reshape(-1)
  _write_mono_16k_wav(output_path, samples)
  _progress(f"[audio] raw recording saved path={output_path}")
  return {
    "audio_path": str(output_path),
    "sample_rate": 16000,
    **_audio_stats(samples),
  }


def _record_vad(config_path: Path, duration_seconds: float, output_path: Path, args) -> dict:
  config = load_config(config_path)
  audio_config = config.integrations.audio
  recorder = SoundDeviceVadRecorder(
    model_path=str(audio_config.get("vad_model_path", "models/asr/vad/silero_vad.onnx")),
    threshold=float(args.vad_threshold),
    min_rms=float(args.vad_min_rms),
    min_speech_windows=int(audio_config.get("vad_min_speech_windows", 2)),
    pre_roll_ms=int(audio_config.get("vad_pre_roll_ms", 120)),
    post_roll_ms=int(args.vad_post_roll_ms),
    tail_padding_ms=int(audio_config.get("vad_tail_padding_ms", 700)),
    max_utterance_sec=float(audio_config.get("vad_max_utterance_sec", 15.0)),
  )
  _progress(
    f"[vad] recording start max_duration={duration_seconds:.1f}s "
    f"threshold={args.vad_threshold} min_rms={args.vad_min_rms} "
    f"post_roll={args.vad_post_roll_ms}ms"
  )
  return recorder.record_once(duration_seconds, str(output_path), 16000)


def _transcribe(config_path: Path, audio_path: Path, language: str) -> dict:
  config = load_config(config_path)
  audio_config = config.integrations.audio
  client = LocalAudioClient(
    asr_model_dir=str(audio_config.get("asr_model_dir", "models/asr/sense-voice")),
    tts_model_dir=str(audio_config.get("tts_model_dir", "models/tts")),
    asr_provider=str(audio_config.get("asr_provider", "cpu")),
    asr_num_threads=int(audio_config.get("asr_num_threads", 4)),
  )
  return client.transcribe_file(str(audio_path), language)


def _print_devices() -> None:
  import sounddevice as sd

  print("# sounddevice devices")
  print(sd.query_devices())
  print(f"# default device: {sd.default.device}")
  print()


def _build_parser() -> argparse.ArgumentParser:
  parser = argparse.ArgumentParser(
    description="Test SensorAgent microphone, realtime VAD, and SenseVoice ASR.",
  )
  parser.add_argument(
    "--mode",
    choices=("devices", "raw", "vad", "asr", "all"),
    default="all",
    help="Which part of the audio input pipeline to test.",
  )
  parser.add_argument(
    "--config",
    type=Path,
    default=ROOT / "configs" / "audio_robot_sim.yaml",
    help="Config with audio model paths and VAD defaults.",
  )
  parser.add_argument("--duration", type=float, default=5.0)
  parser.add_argument("--audio-path", type=Path, default=None)
  parser.add_argument("--language", default="zh")
  parser.add_argument("--vad-threshold", type=float, default=0.55)
  parser.add_argument("--vad-min-rms", type=float, default=0.0)
  parser.add_argument("--vad-post-roll-ms", type=int, default=1000)
  parser.add_argument(
    "--probe-silero",
    action="store_true",
    help="For --mode asr, also print Silero VAD probability stats for the WAV.",
  )
  return parser


def _probe_silero(config_path: Path, audio_path: Path, args) -> dict:
  import numpy as np
  from sensoragent.integrations import SileroVadSegmenter
  from sensoragent.integrations.vad import _read_mono_16k_wav

  config = load_config(config_path)
  audio_config = config.integrations.audio
  segmenter = SileroVadSegmenter(
    model_path=str(audio_config.get("vad_model_path", "models/asr/vad/silero_vad.onnx")),
    threshold=float(args.vad_threshold),
    min_speech_windows=int(audio_config.get("vad_min_speech_windows", 2)),
    pre_roll_ms=int(audio_config.get("vad_pre_roll_ms", 120)),
    post_roll_ms=int(args.vad_post_roll_ms),
    max_utterance_sec=float(audio_config.get("vad_max_utterance_sec", 15.0)),
  )
  samples = _read_mono_16k_wav(audio_path)
  probs = []
  rms_values = []
  for start in range(0, max(0, samples.size - 512 + 1), 512):
    chunk = samples[start:start + 512]
    probs.append(segmenter.speech_probability(chunk))
    rms_values.append(float(np.sqrt(np.mean(np.square(chunk)))))
  hits = [
    prob
    for prob, rms in zip(probs, rms_values, strict=False)
    if prob >= args.vad_threshold and rms >= args.vad_min_rms
  ]
  return {
    "windows": len(probs),
    "threshold": args.vad_threshold,
    "min_rms": args.vad_min_rms,
    "max_probability": max(probs) if probs else 0.0,
    "mean_probability": float(np.mean(probs)) if probs else 0.0,
    "max_rms": max(rms_values) if rms_values else 0.0,
    "speech_windows": len(hits),
  }


def main() -> int:
  args = _build_parser().parse_args()
  _progress(f"[probe] mode={args.mode} config={args.config}")

  if args.mode in {"devices", "raw", "vad", "all"}:
    _progress("[audio] listing sounddevice devices")
    _print_devices()
  if args.mode == "devices":
    return 0

  raw_path = args.audio_path or _default_audio_path("raw_probe")
  vad_path = args.audio_path or _default_audio_path("vad_probe")
  results: dict[str, object] = {}

  if args.mode in {"raw", "all"}:
    raw_result = _record_raw(args.duration, raw_path)
    _progress(
      f"[audio] raw stats rms={raw_result['rms']:.4f} "
      f"peak={raw_result['peak']:.4f}"
    )
    results["raw"] = raw_result
    print(json.dumps({"raw": raw_result}, ensure_ascii=False, indent=2))
    print()

  asr_input: Path | None = None
  if args.mode in {"vad", "all"}:
    vad_result = _record_vad(args.config, args.duration, vad_path, args)
    _progress(
      f"[vad] captured duration={vad_result['duration_ms']}ms "
      f"path={vad_result['audio_path']}"
    )
    results["vad"] = vad_result
    asr_input = Path(vad_result["audio_path"])
    print(json.dumps({"vad": vad_result}, ensure_ascii=False, indent=2))
    print()

  if args.mode == "asr":
    if args.audio_path is None:
      raise SystemExit("--audio-path is required for --mode asr")
    asr_input = args.audio_path
  elif args.mode == "all":
    asr_input = asr_input or raw_path

  if args.mode in {"asr", "all"} and asr_input is not None:
    _progress(f"[asr] transcribing path={asr_input}")
    transcript = _transcribe(args.config, asr_input, args.language)
    _progress(f"[asr] transcript text={json.dumps(transcript.get('text', ''), ensure_ascii=False)}")
    results["asr"] = transcript
    print(json.dumps({"asr": transcript}, ensure_ascii=False, indent=2))
    if args.probe_silero:
      print(json.dumps({"silero_probe": _probe_silero(args.config, asr_input, args)}, ensure_ascii=False, indent=2))

  return 0


if __name__ == "__main__":
  raise SystemExit(main())
