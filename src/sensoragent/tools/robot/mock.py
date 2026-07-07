"""Mock robot tools for local tests."""

from sensoragent.schemas import ToolCall, ToolResult, ToolSpec


class MockPickTool:
  """Pretend to pick an object successfully."""

  spec = ToolSpec(name="robot.mock_pick", description="Mock robot pick tool.")

  def run(self, call: ToolCall) -> ToolResult:
    return ToolResult(
      tool=self.spec.name,
      success=True,
      output={
        "picked": True,
        "object_id": call.input.get("object_id", "mock_object_001"),
        "execution_id": "mock_pick_exec_001",
      },
    )


class MockPlaceTool:
  """Pretend to place an object successfully."""

  spec = ToolSpec(name="robot.mock_place", description="Mock robot place tool.")

  def run(self, call: ToolCall) -> ToolResult:
    return ToolResult(
      tool=self.spec.name,
      success=True,
      output={
        "placed": True,
        "target": call.input.get("target", "third bin cell"),
        "execution_id": "mock_place_exec_001",
      },
    )
