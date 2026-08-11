"""Tests for the strict Grounding DINO + SAM 2 Tool adapter."""

from __future__ import annotations

from pathlib import Path

from sensoragent.agent import build_agent_from_config
from sensoragent.contracts import ContractValidator
from sensoragent.schemas import ToolCall, TraceContext
from sensoragent.tools.vision import (
  VisionDetection,
  VisionGroundedSam2Tool,
  VisionInferenceOptions,
)


ROOT = Path(__file__).resolve().parents[2]


class _BoxDetector:
  def detect(
    self,
    *,
    query: str,
    image_path: str | None,
    depth_path: str | None,
    options: VisionInferenceOptions,
  ) -> VisionDetection:
    del image_path, depth_path, options
    return VisionDetection(
      found=True,
      label=query,
      confidence=0.9,
      bbox_2d=[1.0, 1.0, 5.0, 5.0],
      source="fake_grounding_dino",
    )

  def detect_all(
    self,
    *,
    query: str,
    image_path: str | None,
    depth_path: str | None,
    options: VisionInferenceOptions,
  ) -> list[VisionDetection]:
    return [
      self.detect(
        query=query,
        image_path=image_path,
        depth_path=depth_path,
        options=options,
      )
    ]


class _SceneDetector:
  def detect_all(self, **kwargs) -> list[VisionDetection]:
    del kwargs
    return [
      VisionDetection(
        found=True,
        label="red block",
        confidence=0.95,
        bbox_2d=[80.0, 1.0, 95.0, 16.0],
        source="fake_grounding_dino",
      ),
      VisionDetection(
        found=True,
        label="red block",
        confidence=0.70,
        bbox_2d=[10.0, 10.0, 30.0, 30.0],
        source="fake_grounding_dino",
      ),
    ]

  def detect(self, **kwargs) -> VisionDetection:
    return self.detect_all(**kwargs)[0]


class _MaskRefiner:
  def segment(self, *, image_path: str, bbox_2d, device: str | None):
    del image_path, bbox_2d, device
    return [[[1.0, 1.0], [5.0, 1.0], [5.0, 5.0], [1.0, 5.0]]]


class _EmptyMaskRefiner:
  def segment(self, *, image_path: str, bbox_2d, device: str | None):
    del image_path, bbox_2d, device
    return []


class _NotFoundDetector:
  def detect(
    self,
    *,
    query: str,
    image_path: str | None,
    depth_path: str | None,
    options: VisionInferenceOptions,
  ) -> VisionDetection:
    del image_path, depth_path, options
    return VisionDetection(
      found=False,
      label=query,
      confidence=0.0,
      source="fake_grounding_dino",
    )


def _call(**input_data: object) -> ToolCall:
  return ToolCall(
    tool="vision.grounded_sam2",
    input={"query": "red block", "image_path": "frame.jpg", **input_data},
    trace=TraceContext(),
  )


def test_grounded_sam2_requires_and_returns_a_real_mask() -> None:
  tool = VisionGroundedSam2Tool(
    detector=_BoxDetector(),
    mask_refiner=_MaskRefiner(),
  )

  result = tool.run(_call(refine_masks=False, require_masks=False))

  assert result.success
  assert result.tool == "vision.grounded_sam2"
  assert result.output["bbox_2d"] == [1.0, 1.0, 5.0, 5.0]
  assert result.output["mask_polygons"]
  assert result.output["mask_area_px"] == 16.0
  ContractValidator(ROOT / "contracts").validate_tool_output(
    "vision.grounded_sam2", result.output
  )


def test_grounded_sam2_fails_instead_of_falling_back_to_a_box() -> None:
  tool = VisionGroundedSam2Tool(
    detector=_BoxDetector(),
    mask_refiner=_EmptyMaskRefiner(),
  )

  result = tool.run(_call())

  assert not result.success
  assert result.tool == "vision.grounded_sam2"
  assert "VISION_BACKEND_ERROR" in (result.error or "")
  assert "returned no mask" in (result.error or "")


def test_grounded_sam2_not_found_output_matches_contract() -> None:
  tool = VisionGroundedSam2Tool(
    detector=_NotFoundDetector(),
    mask_refiner=_EmptyMaskRefiner(),
  )

  result = tool.run(_call())

  assert not result.success
  assert result.error == "OBJECT_NOT_FOUND"
  assert result.output == {
    "found": False,
    "label": "red block",
    "confidence": 0.0,
    "source": "fake_grounding_dino",
  }
  ContractValidator(ROOT / "contracts").validate_tool_output(
    "vision.grounded_sam2", result.output
  )


def test_grounded_sam2_config_registers_without_loading_models() -> None:
  bundle = build_agent_from_config(ROOT / "configs" / "vision_grounded_sam2.yaml")

  assert bundle.tool_registry.names() == ["vision.grounded_sam2"]


def test_scene_aware_example_config_reaches_the_tool() -> None:
  bundle = build_agent_from_config(
    ROOT / "configs" / "vision_scene_aware.example.yaml"
  )
  tool = bundle.tool_registry.get("vision.grounded_sam2")

  assert tool._candidate_policy == "scene_aware"
  assert tool._scene_profile.name == "industrial_tabletop_v1"
  assert tool._scene_profile.image_size == (424.0, 240.0)


def test_grounded_sam2_refines_the_scene_aware_winner() -> None:
  tool = VisionGroundedSam2Tool(
    detector=_SceneDetector(),
    mask_refiner=_MaskRefiner(),
  )

  result = tool.run(
    _call(
      candidate_policy="scene_aware",
      scene_profile={"workspace_roi": [0.0, 0.0, 50.0, 50.0]},
    )
  )

  assert result.success
  assert result.output["bbox_2d"] == [10.0, 10.0, 30.0, 30.0]
  assert result.output["candidate_policy"] == "scene_aware"
  assert result.output["mask_polygons"]
