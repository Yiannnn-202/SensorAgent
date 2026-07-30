"""Continuously test microphone -> VAD/fixed-window capture -> SenseVoice ASR.

By default this is an utterance streaming test: microphone audio streams into
VAD, VAD cuts one utterance after speech plus silence, then SenseVoice
transcribes that utterance. It repeats until Ctrl+C.

Use ``--capture-mode fixed`` to bypass VAD and transcribe fixed-duration chunks.
That is useful when raw recordings are audible but Silero VAD does not fire.

Run from the repository root:

  PYTHONPATH=src .venv312/bin/python scripts/linux/stream_asr_pipeline.py
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import wave
from datetime import UTC, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
  sys.path.insert(0, str(SRC))

from sensoragent.config import load_config
from sensoragent.integrations import LocalAudioClient, SoundDeviceVadRecorder, VadError


def _progress(message: str) -> None:
  print(message, file=sys.stderr, flush=True)


def _recording_path(output_dir: Path, index: int) -> Path:
  timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
  return output_dir / f"stream_asr_{timestamp}_{index:03d}.wav"


def _build_recorder(config_path: Path, args: argparse.Namespace) -> SoundDeviceVadRecorder:
  config = load_config(config_path)
  audio_config = config.integrations.audio
  return SoundDeviceVadRecorder(
    model_path=str(audio_config.get("vad_model_path", "models/asr/vad/silero_vad.onnx")),
    threshold=float(args.vad_threshold),
    min_rms=float(args.vad_min_rms),
    min_speech_windows=int(audio_config.get("vad_min_speech_windows", 2)),
    pre_roll_ms=int(audio_config.get("vad_pre_roll_ms", 120)),
    post_roll_ms=int(args.vad_post_roll_ms),
    tail_padding_ms=int(audio_config.get("vad_tail_padding_ms", 700)),
    max_utterance_sec=float(args.max_utterance_sec),
  )


def _build_asr_client(config_path: Path) -> LocalAudioClient:
  config = load_config(config_path)
  audio_config = config.integrations.audio
  return LocalAudioClient(
    asr_model_dir=str(audio_config.get("asr_model_dir", "models/asr/sense-voice")),
    tts_model_dir=str(audio_config.get("tts_model_dir", "models/tts")),
    asr_provider=str(audio_config.get("asr_provider", "cpu")),
    asr_num_threads=int(audio_config.get("asr_num_threads", 4)),
  )


def _write_mono_16k_wav(path: Path, samples) -> None:
  import numpy as np

  path.parent.mkdir(parents=True, exist_ok=True)
  samples = np.asarray(samples, dtype=np.int16).reshape(-1)
  with wave.open(str(path), "wb") as wav:
    wav.setnchannels(1)
    wav.setsampwidth(2)
    wav.setframerate(16000)
    wav.writeframes(samples.tobytes())


def _record_fixed(duration_seconds: float, output_path: Path) -> dict:
  import numpy as np
  import sounddevice as sd

  frames = int(duration_seconds * 16000)
  _progress(f"[audio] fixed capture start duration={duration_seconds:g}s")
  audio = sd.rec(frames, samplerate=16000, channels=1, dtype="int16")
  sd.wait()
  samples = np.asarray(audio, dtype=np.int16).reshape(-1)
  _write_mono_16k_wav(output_path, samples)
  float_samples = samples.astype("float32") / 32768.0
  rms = float(np.sqrt(np.mean(np.square(float_samples)))) if samples.size else 0.0
  peak = float(np.max(np.abs(float_samples))) if samples.size else 0.0
  return {
    "audio_path": str(output_path),
    "duration_ms": int(samples.size * 1000 / 16000),
    "sample_rate": 16000,
    "rms": rms,
    "peak": peak,
  }


def _print_event(event: str, payload: dict) -> None:
  print(
    json.dumps(
      {
        "event": event,
        "timestamp": datetime.now(UTC).isoformat(),
        **payload,
      },
      ensure_ascii=False,
    ),
    flush=True,
  )


def _build_parser() -> argparse.ArgumentParser:
  parser = argparse.ArgumentParser(
    description="Loop over microphone -> realtime VAD -> SenseVoice ASR.",
  )
  parser.add_argument(
    "--config",
    type=Path,
    default=ROOT / "configs" / "audio_robot_sim.yaml",
    help="Config with local audio model paths and VAD defaults.",
  )
  parser.add_argument(
    "--capture-mode",
    choices=("vad", "fixed"),
    default="vad",
    help="Use realtime VAD utterance capture or fixed-duration chunks.",
  )
  parser.add_argument(
    "--listen-window",
    type=float,
    default=15.0,
    help=(
      "Maximum seconds to wait for one VAD utterance, or fixed chunk length "
      "when --capture-mode fixed."
    ),
  )
  parser.add_argument(
    "--max-utterance-sec",
    type=float,
    default=15.0,
    help="Maximum captured speech duration for one utterance.",
  )
  parser.add_argument("--language", default="zh")
  parser.add_argument("--vad-threshold", type=float, default=0.55)
  parser.add_argument("--vad-min-rms", type=float, default=0.0)
  parser.add_argument("--vad-post-roll-ms", type=int, default=1000)
  parser.add_argument(
    "--output-dir",
    type=Path,
    default=ROOT / "logs" / "audio",
    help="Directory for captured utterance WAV files.",
  )
  parser.add_argument(
    "--max-utterances",
    type=int,
    default=0,
    help="Stop after N successful utterances. 0 means run until Ctrl+C.",
  )
  parser.add_argument(
    "--show-empty",
    action="store_true",
    help="Print ASR events even when SenseVoice returns an empty transcript.",
  )
  return parser


def main() -> int:
  args = _build_parser().parse_args()
  args.output_dir.mkdir(parents=True, exist_ok=True)

  recorder = _build_recorder(args.config, args)
  asr_client = _build_asr_client(args.config)

  _print_event(
    "stream_started",
    {
      "config": str(args.config),
      "language": args.language,
      "capture_mode": args.capture_mode,
      "listen_window": args.listen_window,
      "vad": {
        "threshold": args.vad_threshold,
        "min_rms": args.vad_min_rms,
        "post_roll_ms": args.vad_post_roll_ms,
      },
    },
  )
  _progress(
    "[asr] stream started "
    f"mode={args.capture_mode} language={args.language} "
    f"listen_window={args.listen_window:g}s"
  )
  _progress("Speak one command at a time. Press Ctrl+C to stop.")

  utterance_index = 0
  successes = 0
  try:
    while args.max_utterances <= 0 or successes < args.max_utterances:
      utterance_index += 1
      audio_path = _recording_path(args.output_dir, utterance_index)
      _print_event(
        "listening",
        {
          "utterance_index": utterance_index,
          "audio_path": str(audio_path),
        },
      )
      _progress(f"[audio] listening utterance={utterance_index} path={audio_path}")
      if args.capture_mode == "fixed":
        recording = _record_fixed(args.listen_window, audio_path)
      else:
        try:
          _progress(
            "[vad] waiting for utterance "
            f"threshold={args.vad_threshold} post_roll={args.vad_post_roll_ms}ms"
          )
          recording = recorder.record_once(args.listen_window, str(audio_path), 16000)
        except VadError as exc:
          _progress(f"[vad] fail utterance={utterance_index} error={exc}")
          _print_event(
            "vad_error",
            {
              "utterance_index": utterance_index,
              "error": str(exc),
            },
          )
          continue

      _progress(
        f"[audio] captured utterance={utterance_index} "
        f"duration={recording['duration_ms']}ms path={recording['audio_path']}"
      )
      _progress(f"[asr] transcribing utterance={utterance_index}")
      transcript = asr_client.transcribe_file(recording["audio_path"], args.language)
      text = str(transcript.get("text", ""))
      _progress(
        f"[asr] transcript utterance={utterance_index} "
        f"text={json.dumps(text, ensure_ascii=False)}"
      )
      if text or args.show_empty:
        _print_event(
          "transcript",
          {
            "utterance_index": utterance_index,
            "audio_path": recording["audio_path"],
            "duration_ms": recording["duration_ms"],
            "rms": recording.get("rms"),
            "peak": recording.get("peak"),
            "vad": recording.get("vad"),
            "text": text,
            "confidence": transcript.get("confidence"),
            "language": transcript.get("language"),
          },
        )
      if text:
        successes += 1
  except KeyboardInterrupt:
    _progress("[asr] stream stopped reason=keyboard_interrupt")
    _print_event("stream_stopped", {"reason": "keyboard_interrupt"})
    return 0
  finally:
    time.sleep(0.05)

  _progress("[asr] stream stopped reason=max_utterances")
  _print_event("stream_stopped", {"reason": "max_utterances"})
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
