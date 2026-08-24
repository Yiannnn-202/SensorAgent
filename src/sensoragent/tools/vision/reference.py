"""Constrained VLM resolution of natural-language visual references."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Protocol

from sensoragent.schemas import ToolCall, ToolResult, ToolSpec


class VisionJsonClient(Protocol):
  def complete_vision_json(self, system_prompt: str, user_prompt: str, image_path: str) -> dict:
    """Return structured VLM output for one image."""


class VisionResolveReferenceTool:
  """Choose one already-localized candidate from a natural-language reference."""

  spec = ToolSpec(
    name="vision.resolve_reference",
    description="Use a VLM to select exactly one pre-localized visual candidate.",
    tags=("vision", "vlm", "reference", "safety"),
    timeout_seconds=40.0,
  )

  def __init__(self, client: VisionJsonClient) -> None:
    self._client = client

  def run(self, call: ToolCall) -> ToolResult:
    instruction = call.input.get("instruction")
    image_path = call.input.get("image_path")
    candidates = call.input.get("candidates")
    spatial_constraint = call.input.get("spatial_constraint")
    if not isinstance(instruction, str) or not instruction.strip():
      return ToolResult(tool=self.spec.name, success=False, error="instruction must be a non-empty string")
    if not isinstance(image_path, str) or not image_path:
      return ToolResult(tool=self.spec.name, success=False, error="image_path must be a non-empty string")
    if not isinstance(candidates, list) or not candidates:
      return ToolResult(tool=self.spec.name, success=False, error="candidates must be a non-empty list")
    if spatial_constraint is not None and not isinstance(spatial_constraint, Mapping):
      return ToolResult(tool=self.spec.name, success=False, error="spatial_constraint must be an object when provided")

    allowed: list[dict] = []
    candidate_ids: set[str] = set()
    for candidate in candidates:
      if not isinstance(candidate, Mapping):
        return ToolResult(tool=self.spec.name, success=False, error="every candidate must be an object")
      object_id = candidate.get("object_id")
      label = candidate.get("label")
      if not isinstance(object_id, str) or not object_id or not isinstance(label, str) or not label:
        return ToolResult(tool=self.spec.name, success=False, error="candidates require non-empty object_id and label")
      if object_id in candidate_ids:
        return ToolResult(tool=self.spec.name, success=False, error=f"duplicate candidate object_id: {object_id}")
      candidate_ids.add(object_id)
      allowed.append({
        "object_id": object_id,
        "label": label,
        "bbox_2d": candidate.get("bbox_2d"),
        "center_px": candidate.get("center_px"),
      })

    aliases = {
      "短螺栓": "short bolt", "螺栓": "short bolt", "六角螺母": "hex nut",
      "螺母": "hex nut", "滚轮": "roller", "滚柱": "roller",
    }
    expected_label = next((label for phrase, label in aliases.items() if phrase in instruction), None)
    matching = [candidate for candidate in candidates if expected_label is None or candidate["label"].casefold() == expected_label]
    relation = spatial_constraint.get("relation") if isinstance(spatial_constraint, Mapping) else None
    ordinal = spatial_constraint.get("ordinal", 1) if isinstance(spatial_constraint, Mapping) else 1
    if isinstance(ordinal, int) and ordinal >= 1 and relation in {"left", "right"}:
      positioned = [candidate for candidate in matching if isinstance(candidate.get("center_px"), list)]
      positioned.sort(key=lambda candidate: float(candidate["center_px"][0]), reverse=relation == "right")
      if len(positioned) >= ordinal:
        matching = [positioned[ordinal - 1]]
    if expected_label is not None and len(matching) == 1:
      chosen = matching[0]
      return ToolResult(
        tool=self.spec.name,
        success=True,
        output={
          "object_id": chosen["object_id"], "label": chosen["label"], "confidence": 1.0,
          "reason": "deterministic candidate label and spatial selection", "candidate": dict(chosen),
        },
      )

    system_prompt = (
      "Select exactly one object_id from the provided candidates that matches the operator's "
      "visual reference. Never invent an ID, coordinate, or robot action. Return JSON only: "
      '{"object_id":"...","confidence":0.0,"reason":"..."}. Copy object_id exactly. '
      "If the reference is ambiguous, return object_id as an empty string and confidence 0."
    )
    user_prompt = json.dumps(
      {"instruction": instruction, "spatial_constraint": spatial_constraint, "candidates": allowed},
      ensure_ascii=False,
    )
    try:
      response = self._client.complete_vision_json(system_prompt, user_prompt, image_path)
    except Exception as exc:
      return ToolResult(tool=self.spec.name, success=False, error=f"VLM_REFERENCE_FAILED: {exc}")
    object_id = None
    if isinstance(response, Mapping):
      object_id = response.get("object_id", response.get("selected_object_id", response.get("pick_object_id")))
    if isinstance(object_id, str):
      object_id = object_id.strip()
    confidence = response.get("confidence") if isinstance(response, Mapping) else None
    if object_id not in candidate_ids:
      return ToolResult(
        tool=self.spec.name,
        success=False,
        error="REFERENCE_AMBIGUOUS: VLM did not select an allowed candidate",
      )
    if not isinstance(confidence, (int, float)) or isinstance(confidence, bool) or not 0.0 <= float(confidence) <= 1.0:
      return ToolResult(tool=self.spec.name, success=False, error="VLM_REFERENCE_INVALID: confidence must be between 0 and 1")
    chosen = next(candidate for candidate in candidates if candidate["object_id"] == object_id)
    return ToolResult(
      tool=self.spec.name,
      success=True,
      output={
        "object_id": object_id,
        "label": chosen["label"],
        "confidence": float(confidence),
        "reason": str(response.get("reason", "")),
        "candidate": dict(chosen),
      },
    )
