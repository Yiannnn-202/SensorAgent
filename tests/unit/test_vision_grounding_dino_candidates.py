"""Tests for the independent Grounding DINO candidate policy tool."""

from __future__ import annotations

from pathlib import Path

from sensoragent.contracts import ContractValidator
from sensoragent.schemas import ToolCall, TraceContext
from sensoragent.tools.vision import (
  VisionDetection,
  VisionGroundingDinoCandidatesTool,
  VisionInferenceOptions,
  filter_cross_category_candidates,
)


ROOT = Path(__file__).resolve().parents[2]


def _detection(label: str, score: float, bbox: list[float]) -> VisionDetection:
  return VisionDetection(
    found=True,
    label=label,
    confidence=score,
    bbox_2d=bbox,
    object_id=f"{label}_{score}",
    source="fake_grounding_dino",
  )


def test_cross_class_filter_applies_classwise_nms_and_score_winner() -> None:
  decisions = filter_cross_category_candidates(
    [
      _detection("hex nut", 0.80, [0, 0, 10, 10]),
      _detection("hex nut", 0.60, [1, 1, 11, 11]),
      _detection("roller", 0.70, [0, 0, 10, 10]),
      _detection("short bolt", 0.79, [20, 20, 30, 30]),
    ],
    classwise_nms_iou=0.5,
    cross_class_iou=0.5,
    ambiguity_margin=0.03,
  )

  assert [item.status for item in decisions] == [
    "selected",
    "suppressed",
    "suppressed",
    "selected",
  ]
  assert decisions[1].rejection_reason == "same_class_nms"
  assert decisions[2].rejection_reason == "cross_class_overlap_lower_score"


def test_cross_class_filter_marks_close_scores_ambiguous() -> None:
  decisions = filter_cross_category_candidates(
    [
      _detection("hex nut", 0.80, [0, 0, 10, 10]),
      _detection("roller", 0.79, [0, 0, 10, 10]),
    ],
    cross_class_iou=0.5,
    ambiguity_margin=0.03,
  )

  assert [item.status for item in decisions] == ["ambiguous", "ambiguous"]
  assert all(
    item.rejection_reason == "cross_class_overlap_ambiguous"
    for item in decisions
  )


class _FakeMultiQueryDetector:
  def __init__(self) -> None:
    self.calls: list[str] = []

  def detect_all(
    self,
    *,
    query: str,
    image_path: str | None,
    depth_path: str | None,
    options: VisionInferenceOptions,
  ) -> list[VisionDetection]:
    del image_path, depth_path, options
    self.calls.append(query)
    return {
      "hex nut": [_detection("hex nut", 0.80, [0, 0, 10, 10])],
      "roller": [_detection("roller", 0.70, [0, 0, 10, 10])],
      "short bolt": [_detection("short bolt", 0.79, [20, 20, 30, 30])],
    }[query]

  def detect(self, **kwargs) -> VisionDetection:
    return self.detect_all(**kwargs)[0]


def test_candidate_tool_returns_structured_policy_result_without_registration() -> None:
  detector = _FakeMultiQueryDetector()
  tool = VisionGroundingDinoCandidatesTool(detector=detector)
  result = tool.run(
    ToolCall(
      tool="vision.grounding_dino_candidates",
      input={
        "image_path": "frame.jpg",
        "queries": ["hex nut", "roller", "short bolt"],
      },
      trace=TraceContext(),
    )
  )

  assert result.success
  assert detector.calls == ["hex nut", "roller", "short bolt"]
  assert len(result.output["selected"]) == 2
  assert result.output["suppressed"][0]["rejection_reason"] == (
    "cross_class_overlap_lower_score"
  )
  ContractValidator(ROOT / "contracts").validate_tool_output(
    "vision.grounding_dino_candidates", result.output
  )


def test_candidate_tool_rejects_missing_image_and_queries() -> None:
  tool = VisionGroundingDinoCandidatesTool(detector=_FakeMultiQueryDetector())
  result = tool.run(
    ToolCall(
      tool="vision.grounding_dino_candidates",
      input={"image_path": "frame.jpg"},
      trace=TraceContext(),
    )
  )

  assert not result.success
  assert "queries must be a non-empty list" in (result.error or "")
