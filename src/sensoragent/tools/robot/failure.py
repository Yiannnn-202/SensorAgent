"""Mock robot failure tools for workflow tests."""

from sensoragent.schemas import ToolCall, ToolResult, ToolSpec


class MockFailOncePickTool:
  """Fail the first pick attempt and succeed on the next attempt."""

  spec = ToolSpec(
    name="robot.mock_fail_once_pick",
    description="Mock pick tool that fails once before succeeding.",
  )

  def __init__(self) -> None:
    self.calls = 0

  def run(self, call: ToolCall) -> ToolResult:
    self.calls += 1
    if self.calls == 1:
      return ToolResult(tool=self.spec.name, success=False, error="PICK_FAILED")
    return ToolResult(
      tool=self.spec.name,
      success=True,
      output={
        "picked": True,
        "object_id": call.input.get("object_id", "mock_object_001"),
        "execution_id": "mock_retry_pick_exec_001",
      },
    )
