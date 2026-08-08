"""Continuously test realtime microphone -> Silero VAD utterance separation.

This script does not run ASR, the LLM planner, robot, or vision. It prints VAD
state transitions and writes one WAV per VAD-separated utterance.

Run from the repository root:

  PYTHONPATH=src .venv312/bin/python scripts/linux/stream_vad_pipeline.py
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import wave
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from queue import Empty, Queue


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
  sys.path.insert(0, str(SRC))

from sensoragent.config import load_config
from sensoragent.integrations import SileroVadSegmenter


WINDOW_SAMPLES = 512
SAMPLE_RATE = 16000


def _progress(message: str) -> None:
  print(message, file=sys.stderr, flush=True)


def _print_event(event: str, payload: dict) -> None:
  print(
    json.dumps(
      {
        "event": event,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **payload,
      },
      ensure_ascii=False,
    ),
    flush=True,
  )


def _write_mono_16k_wav(path: Path, samples) -> None:
  import numpy as np

  path.parent.mkdir(parents=True, exist_ok=True)
  samples_int16 = (np.clip(samples, -1.0, 1.0) * 32767).astype(np.int16)
  with wave.open(str(path), "wb") as wav:
    wav.setnchannels(1)
    wav.setsampwidth(2)
    wav.setframerate(SAMPLE_RATE)
    wav.writeframes(samples_int16.tobytes())


def _utterance_path(output_dir: Path, index: int) -> Path:
  timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
  return output_dir / f"stream_vad_{timestamp}_{index:03d}.wav"


def _build_segmenter(config_path: Path, args: argparse.Namespace) -> SileroVadSegmenter:
  config = load_config(config_path)
  audio_config = config.integrations.audio
  return SileroVadSegmenter(
    model_path=str(audio_config.get("vad_model_path", "models/asr/vad/silero_vad.onnx")),
    threshold=float(args.vad_threshold),
    min_speech_windows=int(args.min_speech_windows),
    pre_roll_ms=int(args.pre_roll_ms),
    post_roll_ms=int(args.post_roll_ms),
    max_utterance_sec=float(args.max_utterance_sec),
  )


def _build_parser() -> argparse.ArgumentParser:
  parser = argparse.ArgumentParser(
    description="Stream microphone audio through Silero VAD and print utterance boundaries.",
  )
  parser.add_argument(
    "--config",
    type=Path,
    default=ROOT / "configs" / "audio_robot_sim.yaml",
    help="Config with VAD model path.",
  )
  parser.add_argument("--vad-threshold", type=float, default=0.55)
  parser.add_argument("--min-rms", type=float, default=0.0)
  parser.add_argument("--min-speech-windows", type=int, default=2)
  parser.add_argument("--pre-roll-ms", type=int, default=120)
  parser.add_argument("--post-roll-ms", type=int, default=2500)
  parser.add_argument("--tail-padding-ms", type=int, default=700)
  parser.add_argument("--max-utterance-sec", type=float, default=15.0)
  parser.add_argument(
    "--status-interval-ms",
    type=int,
    default=1000,
    help="Print a level/status event at this interval while listening. 0 disables it.",
  )
  parser.add_argument(
    "--print-windows",
    action="store_true",
    help="Print every 32 ms VAD window. Very verbose.",
  )
  parser.add_argument(
    "--output-dir",
    type=Path,
    default=ROOT / "logs" / "audio",
    help="Directory for VAD-separated utterance WAVs.",
  )
  parser.add_argument(
    "--max-utterances",
    type=int,
    default=0,
    help="Stop after N utterances. 0 means run until Ctrl+C.",
  )
  return parser


def main() -> int:
  args = _build_parser().parse_args()
  args.output_dir.mkdir(parents=True, exist_ok=True)

  try:
    import numpy as np
    import sounddevice as sd
  except Exception as exc:
    raise SystemExit(f"sounddevice and numpy are required: {exc}") from exc

  segmenter = _build_segmenter(args.config, args)
  audio_queue: Queue = Queue()

  def _callback(indata, frames, time_info, status) -> None:
    del frames, time_info
    if status:
      _progress(f"[audio] sounddevice status={status}")
      _print_event("sounddevice_status", {"status": str(status)})
    audio_queue.put(np.asarray(indata).reshape(-1).copy())

  pre_roll_windows = max(
    1,
    int((args.pre_roll_ms / 1000) * SAMPLE_RATE / WINDOW_SAMPLES) + 1,
  )
  post_roll_samples = int(SAMPLE_RATE * args.post_roll_ms / 1000)
  tail_padding_samples = int(SAMPLE_RATE * args.tail_padding_ms / 1000)
  max_utterance_samples = int(SAMPLE_RATE * args.max_utterance_sec)
  status_interval_windows = (
    max(1, int(args.status_interval_ms / 1000 * SAMPLE_RATE / WINDOW_SAMPLES))
    if args.status_interval_ms > 0
    else 0
  )

  _print_event(
    "vad_stream_started",
    {
      "config": str(args.config),
      "sample_rate": SAMPLE_RATE,
      "window_ms": int(WINDOW_SAMPLES * 1000 / SAMPLE_RATE),
      "vad_threshold": args.vad_threshold,
      "min_rms": args.min_rms,
      "min_speech_windows": args.min_speech_windows,
      "pre_roll_ms": args.pre_roll_ms,
      "post_roll_ms": args.post_roll_ms,
      "tail_padding_ms": args.tail_padding_ms,
      "max_utterance_sec": args.max_utterance_sec,
    },
  )
  _progress(
    "[vad] stream started "
    f"threshold={args.vad_threshold} min_rms={args.min_rms} "
    f"pre_roll={args.pre_roll_ms}ms post_roll={args.post_roll_ms}ms"
  )
  _progress("Speak one sentence at a time. Press Ctrl+C to stop.")

  pre_roll = deque(maxlen=pre_roll_windows + max(1, args.min_speech_windows))
  utterance_chunks: list = []
  speech_started = False
  consecutive_speech = 0
  consecutive_silence = 0
  samples_seen = 0
  speech_start_sample = 0
  window_index = 0
  utterance_index = 0

  try:
    with sd.InputStream(
      samplerate=SAMPLE_RATE,
      channels=1,
      dtype="int16",
      blocksize=WINDOW_SAMPLES,
      callback=_callback,
    ):
      while args.max_utterances <= 0 or utterance_index < args.max_utterances:
        try:
          chunk_int16 = audio_queue.get(timeout=0.5)
        except Empty:
          continue

        if chunk_int16.size < WINDOW_SAMPLES:
          chunk_int16 = np.pad(chunk_int16, (0, WINDOW_SAMPLES - chunk_int16.size))
        elif chunk_int16.size > WINDOW_SAMPLES:
          chunk_int16 = chunk_int16[:WINDOW_SAMPLES]

        chunk = chunk_int16.astype(np.float32) / 32768.0
        rms = float(math.sqrt(float(np.mean(np.square(chunk))))) if chunk.size else 0.0
        prob = segmenter.speech_probability(chunk)
        is_speech = prob >= args.vad_threshold and rms >= args.min_rms
        samples_seen += WINDOW_SAMPLES
        window_index += 1

        if args.print_windows:
          _print_event(
            "vad_window",
            {
              "window_index": window_index,
              "time_ms": int(samples_seen * 1000 / SAMPLE_RATE),
              "probability": prob,
              "rms": rms,
              "is_speech": is_speech,
            },
          )
        elif status_interval_windows and window_index % status_interval_windows == 0:
          _progress(
            f"[vad] status state={'speech' if speech_started else 'waiting'} "
            f"prob={prob:.3f} rms={rms:.4f} speech={is_speech}"
          )
          _print_event(
            "vad_status",
            {
              "time_ms": int(samples_seen * 1000 / SAMPLE_RATE),
              "state": "speech" if speech_started else "waiting",
              "probability": prob,
              "rms": rms,
              "is_speech": is_speech,
            },
          )

        if not speech_started:
          pre_roll.append(chunk.copy())
          if is_speech:
            consecutive_speech += 1
          else:
            consecutive_speech = 0

          if consecutive_speech >= args.min_speech_windows:
            speech_started = True
            utterance_chunks = list(pre_roll)
            speech_start_sample = max(
              0,
              samples_seen - sum(item.size for item in utterance_chunks),
            )
            consecutive_silence = 0
            _print_event(
              "speech_started",
              {
                "start_ms": int(speech_start_sample * 1000 / SAMPLE_RATE),
                "probability": prob,
                "rms": rms,
              },
            )
            _progress(
              f"[vad] speech started start_ms={int(speech_start_sample * 1000 / SAMPLE_RATE)} "
              f"prob={prob:.3f} rms={rms:.4f}"
            )
          continue

        utterance_chunks.append(chunk.copy())
        utterance_samples = sum(item.size for item in utterance_chunks)
        if is_speech:
          consecutive_silence = 0
        else:
          consecutive_silence += WINDOW_SAMPLES

        should_end = consecutive_silence >= post_roll_samples
        reached_limit = utterance_samples >= max_utterance_samples
        if not should_end and not reached_limit:
          continue

        samples = np.concatenate(utterance_chunks)
        if samples.size > max_utterance_samples:
          samples = samples[:max_utterance_samples]
        if tail_padding_samples > 0:
          samples = np.concatenate(
            [samples, np.zeros(tail_padding_samples, dtype=np.float32)]
          )

        utterance_index += 1
        audio_path = _utterance_path(args.output_dir, utterance_index)
        _write_mono_16k_wav(audio_path, samples)
        duration_ms = int(samples.size * 1000 / SAMPLE_RATE)
        _print_event(
          "speech_ended",
          {
            "utterance_index": utterance_index,
            "reason": "max_utterance_sec" if reached_limit else "post_roll_silence",
            "audio_path": str(audio_path),
            "start_ms": int(speech_start_sample * 1000 / SAMPLE_RATE),
            "duration_ms": duration_ms,
            "silence_ms": int(consecutive_silence * 1000 / SAMPLE_RATE),
          },
        )
        _progress(
          f"[vad] speech ended utterance={utterance_index} "
          f"reason={'max_utterance_sec' if reached_limit else 'post_roll_silence'} "
          f"duration={duration_ms}ms path={audio_path}"
        )

        pre_roll.clear()
        utterance_chunks = []
        speech_started = False
        consecutive_speech = 0
        consecutive_silence = 0

  except KeyboardInterrupt:
    _progress("[vad] stream stopped reason=keyboard_interrupt")
    _print_event("vad_stream_stopped", {"reason": "keyboard_interrupt"})
    return 0

  _progress("[vad] stream stopped reason=max_utterances")
  _print_event("vad_stream_stopped", {"reason": "max_utterances"})
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
