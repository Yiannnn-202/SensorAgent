"""Tests for the competition dual-branch vision router."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
  sys.path.insert(0, str(SRC))

from sensoragent.agent import build_agent_from_config
from sensoragent.contracts import ContractValidator
from sensoragent.schemas import ToolCall, ToolResult, ToolSpec, TraceContext
from sensoragent.tools.vision import (
  VisionDualBranchDetectTool,
  query_mentions_industrial_label,
)


class _RecordingBranch:
  def __init__(
    self,
    *,
    name: str,
    success: bool,
    confidence: float,
    source: str,
  ) -> None:
    self.spec = ToolSpec(name=name, description="recording branch")
    self.calls: list[dict] = []
    self._success = success
    self._confidence = confidence
    self._source = source

  def run(self, call: ToolCall) -> ToolResult:
    self.calls.append(dict(call.input))
    output = {
      "found": self._success,
      "label": str(call.input["query"]),
      "confidence": self._confidence,
      "source": self._source,
    }
    if self._success:
      output.update(
        {
          "object_id": f"{self._source}_001",
          "bbox_2d": [1.0, 2.0, 3.0, 4.0],
          "mask_polygons": [[[1.0, 2.0], [3.0, 2.0], [3.0, 4.0]]],
        }
      )
      return ToolResult(tool=call.tool, success=True, output=output)
    return ToolResult(
      tool=call.tool,
      success=False,
      output=output,
      error="OBJECT_NOT_FOUND",
    )


def _call(query: str, **input_data: object) -> ToolCall:
  return ToolCall(
    tool="vision.dual_branch_detect",
    input={"query": query, "image_path": "frame.jpg", **input_data},
    trace=TraceContext(),
  )


def test_industrial_query_routes_to_yolo11_first() -> None:
  yolo = _RecordingBranch(
    name="vision.yolo11_seg_detect",
    success=True,
    confidence=0.91,
    source="yolo11_seg",
  )
  grounding = _RecordingBranch(
    name="vision.grounded_sam2",
    success=True,
    confidence=0.80,
    source="grounding_dino_sam2",
  )
  result = VisionDualBranchDetectTool(
    fixed_branch=yolo,
    open_branch=grounding,
  ).run(_call("六角螺母"))

  assert result.success
  assert result.tool == "vision.dual_branch_detect"
  assert result.output["source"] == "yolo11_seg"
  assert result.output["vision_pipeline"]["selected_branch"] == "yolo11_seg"
  assert result.output["vision_pipeline"]["route_order"] == [
    "yolo11_seg",
    "grounding_dino",
  ]
  assert len(yolo.calls) == 1
  assert not grounding.calls
  ContractValidator(ROOT / "contracts").validate_tool_output(
    "vision.dual_branch_detect",
    result.output,
  )


def test_unknown_query_routes_to_grounding_dino_first() -> None:
  yolo = _RecordingBranch(
    name="vision.yolo11_seg_detect",
    success=True,
    confidence=0.91,
    source="yolo11_seg",
  )
  grounding = _RecordingBranch(
    name="vision.grounded_sam2",
    success=True,
    confidence=0.80,
    source="grounding_dino_sam2",
  )
  result = VisionDualBranchDetectTool(
    fixed_branch=yolo,
    open_branch=grounding,
  ).run(_call("带蓝色把手的夹具"))

  assert result.success
  assert result.output["source"] == "grounding_dino_sam2"
  assert result.output["vision_pipeline"]["selected_branch"] == "grounding_dino"
  assert result.output["vision_pipeline"]["route_order"] == [
    "grounding_dino",
    "yolo11_seg",
  ]
  assert len(grounding.calls) == 1
  assert not yolo.calls


def test_yolo11_failure_falls_back_to_grounding_dino() -> None:
  yolo = _RecordingBranch(
    name="vision.yolo11_seg_detect",
    success=False,
    confidence=0.0,
    source="yolo11_seg",
  )
  grounding = _RecordingBranch(
    name="vision.grounded_sam2",
    success=True,
    confidence=0.84,
    source="grounding_dino_sam2",
  )
  result = VisionDualBranchDetectTool(
    fixed_branch=yolo,
    open_branch=grounding,
  ).run(_call("滚柱"))

  assert result.success
  assert result.output["source"] == "grounding_dino_sam2"
  pipeline = result.output["vision_pipeline"]
  assert pipeline["fallback_used"]
  assert [attempt["branch"] for attempt in pipeline["attempts"]] == [
    "yolo11_seg",
    "grounding_dino",
  ]


def test_force_branch_runs_only_requested_branch() -> None:
  yolo = _RecordingBranch(
    name="vision.yolo11_seg_detect",
    success=True,
    confidence=0.91,
    source="yolo11_seg",
  )
  grounding = _RecordingBranch(
    name="vision.grounded_sam2",
    success=True,
    confidence=0.80,
    source="grounding_dino_sam2",
  )
  result = VisionDualBranchDetectTool(
    fixed_branch=yolo,
    open_branch=grounding,
  ).run(_call("滚柱", force_branch="grounding_dino"))

  assert result.success
  assert result.output["source"] == "grounding_dino_sam2"
  assert result.output["vision_pipeline"]["route_order"] == ["grounding_dino"]
  assert not yolo.calls
  assert len(grounding.calls) == 1


def test_industrial_label_detection_supports_competition_aliases() -> None:
  assert query_mentions_industrial_label("帮我把滚柱放到第三个格子")
  assert query_mentions_industrial_label("取出左侧的 short bolt")
  assert not query_mentions_industrial_label("带蓝色把手的夹具")


def test_dual_branch_example_config_registers_without_loading_models() -> None:
  bundle = build_agent_from_config(ROOT / "configs" / "vision_dual_branch.example.yaml")

  assert bundle.tool_registry.names() == ["vision.dual_branch_detect"]

