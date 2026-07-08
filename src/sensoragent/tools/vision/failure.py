"""Mock vision failure tools for workflow tests."""

from sensoragent.schemas import ToolCall, ToolResult, ToolSpec


class MockNotFoundDetectTool:
  """Pretend that a detector ran successfully but found no object."""

  spec = ToolSpec(
    name="vision.mock_not_found",
    description="Mock detector returning found=false.",
  )

  def run(self, call: ToolCall) -> ToolResult:
    return ToolResult(
      tool=self.spec.name,
      success=True,
      output={"found": False, "objects": []},
    )
