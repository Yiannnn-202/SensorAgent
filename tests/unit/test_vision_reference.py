"""Tests for constrained VLM visual-reference selection."""

from sensoragent.schemas import ToolCall, TraceContext
from sensoragent.tools.vision.reference import VisionResolveReferenceTool


class _FakeVlm:
  def __init__(self, response: dict) -> None:
    self.response = response
    self.calls: list[tuple[str, str, str]] = []

  def complete_vision_json(self, system_prompt: str, user_prompt: str, image_path: str) -> dict:
    self.calls.append((system_prompt, user_prompt, image_path))
    return self.response


def _call(candidates: list[dict]) -> ToolCall:
  return ToolCall(
    tool="vision.resolve_reference",
    input={
      "instruction": "把这个黑色零件放到格子里",
      "image_path": "frame.png",
      "candidates": candidates,
    },
    trace=TraceContext(),
  )


def test_reference_tool_returns_only_selected_existing_candidate() -> None:
  client = _FakeVlm({"object_id": "roller_001", "confidence": 0.91, "reason": "唯一黑色候选"})
  result = VisionResolveReferenceTool(client).run(_call([
    {"object_id": "roller_001", "label": "roller", "bbox_2d": [10, 10, 30, 30]},
    {"object_id": "bolt_001", "label": "short_bolt", "bbox_2d": [40, 10, 60, 30]},
  ]))

  assert result.success
  assert result.output == {
    "object_id": "roller_001",
    "label": "roller",
    "confidence": 0.91,
    "reason": "唯一黑色候选",
    "candidate": {"object_id": "roller_001", "label": "roller", "bbox_2d": [10, 10, 30, 30]},
  }
  assert "roller_001" in client.calls[0][1]


def test_reference_tool_rejects_vlm_invented_candidate_id() -> None:
  result = VisionResolveReferenceTool(
    _FakeVlm({"object_id": "invented_001", "confidence": 0.99})
  ).run(_call([{"object_id": "roller_001", "label": "roller"}]))

  assert not result.success
  assert result.error == "REFERENCE_AMBIGUOUS: VLM did not select an allowed candidate"


def test_reference_tool_accepts_kimi_selected_object_id_alias() -> None:
  result = VisionResolveReferenceTool(
    _FakeVlm({"selected_object_id": "roller_001", "confidence": 0.8})
  ).run(_call([{"object_id": "roller_001", "label": "roller"}]))

  assert result.success


def test_reference_tool_selects_left_ordinal_without_vlm() -> None:
  client = _FakeVlm({})
  call = _call([
    {"object_id": "short bolt_001", "label": "short bolt", "center_px": [10, 20]},
    {"object_id": "short bolt_002", "label": "short bolt", "center_px": [30, 20]},
  ])
  call = ToolCall(tool=call.tool, input={**call.input, "instruction": "螺栓", "spatial_constraint": {"relation": "left", "ordinal": 2}}, trace=call.trace)
  result = VisionResolveReferenceTool(client).run(call)

  assert result.success
  assert result.output["object_id"] == "short bolt_002"
  assert not client.calls
