"""Strict Grounding DINO plus SAM 2 Tool adapter."""

from __future__ import annotations

from sensoragent.schemas import ToolCall, ToolResult, ToolSpec
from sensoragent.tools.vision.open_vocab import VisionOpenVocabularyDetectTool


class VisionGroundedSam2Tool(VisionOpenVocabularyDetectTool):
  """Expose the repository Grounding DINO + SAM 2 stack as one strict Tool.

  The detector and segmenter implementations stay in ``open_vocab``. This
  adapter fixes their composition and prevents callers from silently disabling
  SAM 2 or accepting a detector-box fallback.
  """

  spec = ToolSpec(
    name="vision.grounded_sam2",
    description=(
      "Detect a text-query object with Grounding DINO, require a SAM 2 mask, "
      "and optionally estimate its RGB-D position."
    ),
    version="0.1.0",
    tags=(
      "vision",
      "open-vocabulary",
      "grounding-dino",
      "sam2",
      "segmentation",
      "rgbd",
    ),
    timeout_seconds=300.0,
  )

  def __init__(self, **settings: object) -> None:
    settings = dict(settings)
    settings.update(
      {
        "backend": "grounding_dino",
        "refine_masks": True,
        "require_masks": True,
        "red_color_shortcut": False,
      }
    )
    super().__init__(**settings)

  def run(self, call: ToolCall) -> ToolResult:
    """Run the fixed detector-segmenter stack with strict mask semantics."""

    strict_input = dict(call.input)
    strict_input["refine_masks"] = True
    strict_input["require_masks"] = True
    return super().run(
      ToolCall(
        tool=self.spec.name,
        input=strict_input,
        trace=call.trace,
      )
    )
