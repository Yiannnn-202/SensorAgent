"""Dual-branch industrial vision routing.

The competition vision stack intentionally has two perception branches:
YOLO11-seg for stable fixed industrial classes, and GroundingDINO+SAM2 for
open-vocabulary queries and long-tail language references. This module keeps
that policy explicit while preserving the existing branch-specific Tools.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from sensoragent.schemas import ToolCall, ToolResult, ToolSpec
from sensoragent.tools.base import Tool
from sensoragent.tools.vision.grounded_sam2 import VisionGroundedSam2Tool
from sensoragent.tools.vision.labels import (
  DEFAULT_INDUSTRIAL_LABELS,
  query_mentions_industrial_label,
)
from sensoragent.tools.vision.yolo11_seg import VisionYolo11SegDetectTool


_FIXED_BRANCH = "yolo11_seg"
_OPEN_BRANCH = "grounding_dino"
_BRANCH_TO_TOOL = {
  _FIXED_BRANCH: "vision.yolo11_seg_detect",
  _OPEN_BRANCH: "vision.grounded_sam2",
}


@dataclass(frozen=True)
class VisionBranchAttempt:
  """Compact record of one branch invocation."""

  branch: str
  tool: str
  success: bool
  confidence: float | None = None
  error: str | None = None

  def to_output(self) -> dict[str, object]:
    output: dict[str, object] = {
      "branch": self.branch,
      "tool": self.tool,
      "success": self.success,
    }
    if self.confidence is not None:
      output["confidence"] = self.confidence
    if self.error is not None:
      output["error"] = self.error
    return output


class VisionDualBranchDetectTool:
  """Route one detection request through YOLO11-seg and GroundingDINO branches."""

  spec = ToolSpec(
    name="vision.dual_branch_detect",
    description=(
      "Detect an industrial object through a YOLO11-seg fixed-class branch "
      "and an industrial GroundingDINO open-vocabulary branch."
    ),
    tags=("vision", "dual-branch", "yolo11", "grounding-dino", "segmentation"),
    timeout_seconds=600.0,
  )

  def __init__(
    self,
    *,
    route_policy: str = "industrial_first",
    fallback_on_error: bool = True,
    min_fixed_confidence: float | None = None,
    industrial_labels: list[str] | tuple[str, ...] | None = None,
    yolo11_seg: Mapping[str, object] | None = None,
    grounding_dino: Mapping[str, object] | None = None,
    fixed_branch: Tool | None = None,
    open_branch: Tool | None = None,
    **common_settings: object,
  ) -> None:
    normalized_policy = str(route_policy).strip().casefold().replace("-", "_")
    if normalized_policy not in {
      "industrial_first",
      "open_first",
      "fixed_only",
      "open_only",
    }:
      raise ValueError(
        "route_policy must be industrial_first, open_first, fixed_only, or open_only"
      )
    if min_fixed_confidence is not None and not 0.0 <= float(min_fixed_confidence) <= 1.0:
      raise ValueError("min_fixed_confidence must be between 0 and 1")
    self._route_policy = normalized_policy
    self._fallback_on_error = bool(fallback_on_error)
    self._min_fixed_confidence = (
      float(min_fixed_confidence) if min_fixed_confidence is not None else None
    )
    self._industrial_labels = tuple(industrial_labels or DEFAULT_INDUSTRIAL_LABELS)
    self._fixed_branch = fixed_branch or VisionYolo11SegDetectTool(
      **{**common_settings, **dict(yolo11_seg or {})}
    )
    self._open_branch = open_branch or VisionGroundedSam2Tool(
      **{**common_settings, **dict(grounding_dino or {})}
    )

  def _route_order(self, query: str, force_branch: object = None) -> tuple[str, ...]:
    if isinstance(force_branch, str) and force_branch:
      branch = force_branch.strip().casefold().replace("-", "_")
      if branch in {"fixed", "yolo", "yolo11", "yolo11_seg"}:
        return (_FIXED_BRANCH,)
      if branch in {"open", "grounding", "grounding_dino", "grounded_sam2"}:
        return (_OPEN_BRANCH,)
      raise ValueError("force_branch must be yolo11_seg or grounding_dino")
    if self._route_policy == "fixed_only":
      return (_FIXED_BRANCH,)
    if self._route_policy == "open_only":
      return (_OPEN_BRANCH,)
    if self._route_policy == "open_first":
      return (_OPEN_BRANCH, _FIXED_BRANCH) if self._fallback_on_error else (_OPEN_BRANCH,)
    if query_mentions_industrial_label(query, self._industrial_labels):
      return (_FIXED_BRANCH, _OPEN_BRANCH) if self._fallback_on_error else (_FIXED_BRANCH,)
    return (_OPEN_BRANCH, _FIXED_BRANCH) if self._fallback_on_error else (_OPEN_BRANCH,)

  def _branch_tool(self, branch: str) -> Tool:
    if branch == _FIXED_BRANCH:
      return self._fixed_branch
    if branch == _OPEN_BRANCH:
      return self._open_branch
    raise ValueError(f"Unknown vision branch: {branch}")

  def _record_attempt(self, branch: str, result: ToolResult) -> VisionBranchAttempt:
    confidence = None
    if isinstance(result.output, dict) and isinstance(result.output.get("confidence"), (int, float)):
      confidence = float(result.output["confidence"])
    return VisionBranchAttempt(
      branch=branch,
      tool=result.tool,
      success=result.success,
      confidence=confidence,
      error=result.error,
    )

  def _accepted(self, branch: str, result: ToolResult) -> bool:
    if not result.success or not isinstance(result.output, dict):
      return False
    if branch != _FIXED_BRANCH or self._min_fixed_confidence is None:
      return True
    confidence = result.output.get("confidence")
    return isinstance(confidence, (int, float)) and float(confidence) >= self._min_fixed_confidence

  def _with_pipeline_output(
    self,
    result: ToolResult,
    *,
    selected_branch: str | None,
    route_order: tuple[str, ...],
    attempts: list[VisionBranchAttempt],
  ) -> ToolResult:
    output = dict(result.output or {})
    pipeline: dict[str, object] = {
      "name": "dual_branch",
      "route_order": list(route_order),
      "fallback_used": selected_branch is not None and route_order[0] != selected_branch,
      "attempts": [attempt.to_output() for attempt in attempts],
    }
    if selected_branch is not None:
      pipeline["selected_branch"] = selected_branch
    output["vision_pipeline"] = pipeline
    return ToolResult(
      tool=self.spec.name,
      success=result.success,
      output=output,
      error=result.error,
    )

  def run(self, call: ToolCall) -> ToolResult:
    """Run the preferred branch first and fall back when configured."""

    query = call.input.get("query")
    if not isinstance(query, str) or not query.strip():
      return ToolResult(
        tool=self.spec.name,
        success=False,
        error="query must be a non-empty string",
      )
    try:
      route_order = self._route_order(query, call.input.get("force_branch"))
    except ValueError as exc:
      return ToolResult(tool=self.spec.name, success=False, error=str(exc))
    attempts: list[VisionBranchAttempt] = []
    last_result: ToolResult | None = None
    for branch in route_order:
      tool = self._branch_tool(branch)
      result = tool.run(
        ToolCall(
          tool=_BRANCH_TO_TOOL[branch],
          input=dict(call.input),
          trace=call.trace,
        )
      )
      attempts.append(self._record_attempt(branch, result))
      last_result = result
      if self._accepted(branch, result):
        return self._with_pipeline_output(
          result,
          selected_branch=branch,
          route_order=route_order,
          attempts=attempts,
        )
    if last_result is None:
      return ToolResult(
        tool=self.spec.name,
        success=False,
        error="VISION_BRANCH_ROUTING_FAILED: no branch was selected",
      )
    return self._with_pipeline_output(
      last_result,
      selected_branch=None,
      route_order=route_order,
      attempts=attempts,
    )
