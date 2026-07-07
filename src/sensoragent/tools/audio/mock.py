"""Mock audio tools for local tests."""

from sensoragent.schemas import ToolCall, ToolResult, ToolSpec


class MockTranscribeTool:
  """Pretend to transcribe an audio command."""

  spec = ToolSpec(
    name="audio.mock_transcribe",
    description="Mock ASR tool returning deterministic text.",
  )

  def run(self, call: ToolCall) -> ToolResult:
    text = call.input.get("text", "put the silver roller into the third bin cell")
    return ToolResult(
      tool=self.spec.name,
      success=True,
      output={"text": text, "confidence": 0.95, "language": "en"},
    )
