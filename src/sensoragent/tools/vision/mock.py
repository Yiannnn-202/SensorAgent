"""Mock vision tools for local end-to-end tests."""

from sensoragent.schemas import ToolCall, ToolResult, ToolSpec


class MockDetectTool:
  """Pretend to detect an object from a natural-language query."""

  spec = ToolSpec(
    name="vision.mock_detect",
    description="Mock object detection tool returning a deterministic object.",
  )

  def run(self, call: ToolCall) -> ToolResult:
    query = call.input.get("query", "object")
    return ToolResult(
      tool=self.spec.name,
      success=True,
      output={
        "found": True,
        "label": query,
        "confidence": 0.91,
        "object_id": "mock_object_001",
        "pose_3d": [0.42, -0.13, 0.08, 0.0, 0.0, 1.57],
      },
    )
