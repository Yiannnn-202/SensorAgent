"""Tests for the optional fixed-class YOLO11 segmentation Tool."""

from __future__ import annotations

from sensoragent.agent import build_agent_from_config
from sensoragent.contracts import ContractValidator
from sensoragent.schemas import ToolCall, TraceContext
from sensoragent.tools.vision import VisionDetection, VisionYolo11SegDetectTool


class _NativeMaskBackend:
  def detect(self, *, query, image_path, depth_path, options):
    del image_path, depth_path, options
    return VisionDetection(
      found=True,
      label=query,
      confidence=0.91,
      bbox_2d=[10.0, 20.0, 30.0, 40.0],
      mask_polygons=[[[10.0, 20.0], [30.0, 20.0], [30.0, 40.0]]],
      source="yolo11_seg",
    )


class _BoxOnlyBackend:
  def detect(self, *, query, image_path, depth_path, options):
    del image_path, depth_path, options
    return VisionDetection(
      found=True,
      label=query,
      confidence=0.91,
      bbox_2d=[10.0, 20.0, 30.0, 40.0],
      source="yolo11_seg",
    )


def test_yolo11_seg_requires_a_native_mask() -> None:
  result = VisionYolo11SegDetectTool(detector=_BoxOnlyBackend()).run(
    ToolCall(
      tool="vision.yolo11_seg_detect",
      input={"query": "roller", "image_path": "frame.png"},
      trace=TraceContext(),
    )
  )

  assert not result.success
  assert "require_masks=true" in (result.error or "")


def test_yolo11_seg_returns_the_stable_mask_detection_contract() -> None:
  tool = VisionYolo11SegDetectTool(detector=_NativeMaskBackend())
  input_data = {"query": "roller", "image_path": "frame.png"}
  result = tool.run(
    ToolCall(
      tool="vision.yolo11_seg_detect",
      input=input_data,
      trace=TraceContext(),
    )
  )

  assert result.success, result.error
  assert result.output["mask_polygons"] == [
    [[10.0, 20.0], [30.0, 20.0], [30.0, 40.0]]
  ]
  ContractValidator().validate_tool_output("vision.yolo11_seg_detect", result.output)


def test_yolo11_seg_example_config_registers_without_loading_weights() -> None:
  bundle = build_agent_from_config("configs/vision_yolo11_seg.example.yaml")
  tool = bundle.tool_registry.get("vision.yolo11_seg_detect")

  assert isinstance(tool, VisionYolo11SegDetectTool)
  assert tool._backend == "yolo11_seg"
  assert tool._require_masks
  assert not tool._refine_masks
