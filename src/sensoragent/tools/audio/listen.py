"""Microphone listen-and-transcribe tool."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from sensoragent.integrations import AudioClient, AudioError, MicrophoneError
from sensoragent.integrations import MicrophoneRecorder
from sensoragent.schemas import ToolCall, ToolResult, ToolSpec


def _default_recording_path() -> str:
  timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
  return str(Path("logs") / "audio" / f"listen_{timestamp}.wav")


class AudioListenTranscribeTool:
  """Record one utterance and transcribe it."""

  spec = ToolSpec(
    name="audio.listen_transcribe",
    description="Record fixed-duration microphone audio and transcribe it.",
    tags=("audio", "microphone", "asr"),
    timeout_seconds=120,
  )

  def __init__(self, recorder: MicrophoneRecorder, client: AudioClient) -> None:
    self._recorder = recorder
    self._client = client

  def run(self, call: ToolCall) -> ToolResult:
    try:
      duration_seconds = float(call.input.get("duration_seconds", 5.0))
      sample_rate = int(call.input.get("sample_rate", 16000))
      language = str(call.input.get("language", "zh"))
      output_path = str(call.input.get("output_path") or _default_recording_path())
      recording = self._recorder.record_once(duration_seconds, output_path, sample_rate)
      transcript = self._client.transcribe_file(recording["audio_path"], language)
    except (AudioError, MicrophoneError, ValueError) as exc:
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
      },
    )
