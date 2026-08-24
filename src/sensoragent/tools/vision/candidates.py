"""Source-region candidate enumeration for constrained VLM reference resolution."""

from __future__ import annotations

from sensoragent.schemas import ToolCall, ToolResult, ToolSpec
from sensoragent.tools.vision.open_vocab import (
  VisionInferenceOptions,
  VisionOpenVocabularyDetectTool,
  _within_allowed_xy_polygon,
  _within_workspace,
)


class VisionListSourceCandidatesTool(VisionOpenVocabularyDetectTool):
  """List all fixed-class RGB-D candidates admitted by the source-region gate."""

  spec = ToolSpec(
    name="vision.list_source_candidates",
    description="List every fixed-class candidate localized inside the configured source region.",
    tags=("vision", "candidates", "segmentation", "rgbd", "safety"),
    timeout_seconds=300.0,
  )

  def run(self, call: ToolCall) -> ToolResult:
    image_path = call.input.get("image_path")
    if not isinstance(image_path, str) or not image_path:
      return ToolResult(tool=self.spec.name, success=False, error="image_path must be a non-empty string")
    if not hasattr(self._detector, "detect_all_classes"):
      return ToolResult(
        tool=self.spec.name,
        success=False,
        error="VISION_CANDIDATES_UNSUPPORTED: fixed-class detector is required",
      )
    try:
      options = self._validate_options(
        call,
        VisionInferenceOptions(
          box_threshold=self._box_threshold,
          text_threshold=self._text_threshold,
          device=self._device,
        ),
      )
      candidates = self._detector.detect_all_classes(image_path=image_path, options=options)
      base_xy_of = self._cloud_base_xy_estimator(
        call.input.get("cloud_path"),
        call.input.get("T_base_camera", self._t_base_camera),
      )
      if base_xy_of is None:
        return ToolResult(
          tool=self.spec.name,
          success=False,
          error="VISION_CANDIDATES_UNLOCALIZED: source-region filtering requires RGB-D geometry",
        )
      candidates = [candidate for candidate in candidates if _within_workspace(base_xy_of(candidate), self._workspace)]
      if self._allowed_xy_polygon is not None:
        candidates = [
          candidate for candidate in candidates
          if _within_allowed_xy_polygon(
            base_xy_of(candidate), self._allowed_xy_polygon, self._allowed_xy_margin_m,
          )
        ]
      localized = [
        self._localize_detection(
          candidate,
          depth_path=call.input.get("depth_path"),
          cloud_path=call.input.get("cloud_path"),
          camera_info_path=call.input.get("camera_info_path", self._camera_info_path),
          camera_info_inline=call.input.get("camera_info", self._camera_info),
          t_base_camera=call.input.get("T_base_camera", self._t_base_camera),
          t_world_camera=call.input.get("T_world_camera", self._t_world_camera),
          position_base_offset=call.input.get("position_base_offset", self._position_base_offset),
          depth_window=int(call.input.get("depth_window", self._depth_window)),
          depth_scale=float(call.input.get("depth_scale", self._depth_scale)),
          camera_frame=str(call.input.get("camera_frame", self._camera_frame)),
          base_frame=str(call.input.get("base_frame", self._base_frame)),
          world_frame=str(call.input.get("world_frame", self._world_frame)),
        )
        for candidate in candidates
      ]
      localized = [candidate for candidate in localized if candidate.found and candidate.position_base is not None]
      return ToolResult(
        tool=self.spec.name,
        success=True,
        output={"source": self._backend, "candidates": [candidate.to_output() for candidate in localized]},
      )
    except (FileNotFoundError, ImportError, OSError, ValueError) as exc:
      return ToolResult(tool=self.spec.name, success=False, error=f"VISION_CANDIDATES_FAILED: {exc}")
