"""ASR tool adapter."""

from sensoragent.integrations import AudioClient, AudioError
from sensoragent.schemas import ToolCall, ToolResult, ToolSpec


class AudioTranscribeTool:
  """Transcribe an audio file through the configured AudioClient."""

  spec = ToolSpec(
    name="audio.transcribe",
    description="Transcribe an audio file into text.",
    tags=("audio", "asr"),
    timeout_seconds=60,
  )

  def __init__(self, client: AudioClient) -> None:
    self._client = client

  def run(self, call: ToolCall) -> ToolResult:
    try:
      output = self._client.transcribe_file(
        audio_path=str(call.input["audio_path"]),
        language=str(call.input.get("language", "zh")),
      )
    except KeyError as exc:
      return ToolResult(tool=self.spec.name, success=False, error=f"Missing field: {exc}")
    except AudioError as exc:
      return ToolResult(tool=self.spec.name, success=False, error=str(exc))
    return ToolResult(tool=self.spec.name, success=True, output=output)
