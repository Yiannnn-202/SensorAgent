"""Microphone listen, VAD, and transcribe tool."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from sensoragent.integrations import AudioClient, AudioError, MicrophoneError, VadError
from sensoragent.integrations import MicrophoneRecorder
from sensoragent.integrations import VadSegmenter
from sensoragent.schemas import ToolCall, ToolResult, ToolSpec


def _default_recording_path() -> str:
  timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
  return str(Path("logs") / "audio" / f"listen_vad_{timestamp}.wav")


class AudioListenVadTranscribeTool:
  """Record microphone audio and transcribe one speech command."""

  spec = ToolSpec(
    name="audio.listen_vad_transcribe",
    description="Record microphone audio, apply VAD-capable ASR, and return text.",
    tags=("audio", "microphone", "vad", "asr"),
    timeout_seconds=180,
  )

  def __init__(
    self,
    recorder: MicrophoneRecorder,
    client: AudioClient,
    segmenter: VadSegmenter | None = None,
  ) -> None:
    self._recorder = recorder
    self._client = client
    self._segmenter = segmenter

  def run(self, call: ToolCall) -> ToolResult:
    try:
      duration_seconds = float(call.input.get("duration_seconds", 8.0))
      sample_rate = int(call.input.get("sample_rate", 16000))
      language = str(call.input.get("language", "zh"))
      output_path = str(call.input.get("output_path") or _default_recording_path())
      vad_config = call.input.get("vad", {})
      if vad_config is None:
        vad_config = {}
      if not isinstance(vad_config, dict):
        raise ValueError("vad must be an object when provided")

      recorder = self._recorder
      if hasattr(recorder, "with_overrides"):
        recorder = recorder.with_overrides(vad_config)
      recording = recorder.record_once(duration_seconds, output_path, sample_rate)
      if "vad" in recording:
        recording_vad = recording["vad"]
        segment = {
          "audio_path": recording["audio_path"],
          "start_ms": recording_vad.get("start_ms", 0),
          "end_ms": recording_vad.get("end_ms", recording["duration_ms"]),
          "duration_ms": recording_vad.get("duration_ms", recording["duration_ms"]),
          "sample_rate": recording["sample_rate"],
        }
        asr_audio_path = recording["audio_path"]
        vad_source = str(recording_vad.get("source", "silero_realtime"))
      elif self._segmenter is not None:
        segment_path = str(Path(recording["audio_path"]).with_name(
          f"{Path(recording['audio_path']).stem}_utterance.wav"
        ))
        segment = self._segmenter.segment_wav(recording["audio_path"], segment_path)
        asr_audio_path = segment["audio_path"]
        vad_source = "silero"
      else:
        segment = {
          "audio_path": recording["audio_path"],
          "start_ms": 0,
          "end_ms": recording["duration_ms"],
          "duration_ms": recording["duration_ms"],
          "sample_rate": recording["sample_rate"],
        }
        asr_audio_path = recording["audio_path"]
        vad_source = "disabled"
      transcript = self._client.transcribe_file(asr_audio_path, language)
    except (AudioError, MicrophoneError, VadError, ValueError) as exc:
      return ToolResult(tool=self.spec.name, success=False, error=str(exc))

    return ToolResult(
      tool=self.spec.name,
      success=True,
      output={
        "audio_path": recording["audio_path"],
        "duration_ms": recording["duration_ms"],
        "sample_rate": recording["sample_rate"],
        "text": transcript["text"],
        "confidence": transcript["confidence"],
        "language": transcript["language"],
        "vad": {
          "enabled": vad_source != "disabled",
          "source": vad_source,
          "audio_path": segment["audio_path"],
          "start_ms": segment["start_ms"],
          "end_ms": segment["end_ms"],
          "duration_ms": segment["duration_ms"],
          "config": vad_config,
        },
      },
    )
