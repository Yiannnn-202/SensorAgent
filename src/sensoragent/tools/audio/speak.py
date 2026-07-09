"""TTS tool adapter."""

from sensoragent.integrations import AudioClient, AudioError
from sensoragent.schemas import ToolCall, ToolResult, ToolSpec


class AudioSpeakTool:
  """Synthesize speech through the configured AudioClient."""

  spec = ToolSpec(
    name="audio.speak",
    description="Synthesize speech from text.",
    tags=("audio", "tts"),
    timeout_seconds=120,
  )

  def __init__(self, client: AudioClient) -> None:
    self._client = client

  def run(self, call: ToolCall) -> ToolResult:
    try:
      output = self._client.speak_text(
        text=str(call.input["text"]),
        output_path=(
          str(call.input["output_path"]) if call.input.get("output_path") else None
        ),
        voice=str(call.input.get("voice", "default")),
        play=bool(call.input.get("play", False)),
      )
    except KeyError as exc:
      return ToolResult(tool=self.spec.name, success=False, error=f"Missing field: {exc}")
    except AudioError as exc:
      return ToolResult(tool=self.spec.name, success=False, error=str(exc))
    return ToolResult(tool=self.spec.name, success=True, output=output)
