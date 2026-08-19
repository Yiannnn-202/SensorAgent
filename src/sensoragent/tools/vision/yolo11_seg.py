"""Fixed-class YOLO11 segmentation Tool adapter."""

from __future__ import annotations

from sensoragent.schemas import ToolCall, ToolResult, ToolSpec
from sensoragent.tools.vision.open_vocab import VisionOpenVocabularyDetectTool


class VisionYolo11SegDetectTool(VisionOpenVocabularyDetectTool):
  """Run a fixed-class Ultralytics YOLO11 segmentation model.

  The generic open-vocabulary tool already owns common candidate selection,
  RGB-D localization, overlays, and stable detection output. This adapter fixes
  the backend to a trained YOLO11 segmentation checkpoint and requires the
  model's native instance masks, so a detector-box or SAM2 fallback cannot be
  mistaken for a YOLO11-seg result.
  """

  spec = ToolSpec(
    name="vision.yolo11_seg_detect",
    description=(
      "Detect a fixed-class object with a YOLO11 segmentation checkpoint, "
      "require its native instance mask, and optionally estimate RGB-D position."
    ),
    tags=(
      "vision",
      "yolo11",
      "segmentation",
      "fixed-class",
      "rgbd",
      "experimental",
    ),
    timeout_seconds=300.0,
  )

  def __init__(self, **settings: object) -> None:
    settings = dict(settings)
    settings.update(
      {
        "backend": "yolo11_seg",
        "refine_masks": False,
        "require_masks": True,
        "red_color_shortcut": False,
      }
    )
    super().__init__(**settings)

  def run(self, call: ToolCall) -> ToolResult:
    """Run the fixed YOLO11-seg path with mandatory native masks."""

    strict_input = dict(call.input)
    strict_input["refine_masks"] = False
    strict_input["require_masks"] = True
    return super().run(
      ToolCall(
        tool=self.spec.name,
        input=strict_input,
        trace=call.trace,
      )
    )
