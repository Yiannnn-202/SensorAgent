"""Configuration-driven object detection tool for simulation runs."""

from __future__ import annotations

from typing import Mapping

from sensoragent.schemas import ToolCall, ToolResult, ToolSpec


class VisionConfigDetectTool:
  """Return a preconfigured object pose keyed by the operator's query string.

  Meant as a bridge between LLM-produced intents and Gazebo scenes where the
  object catalog is known. Replace with a real detector for perception-driven
  runs.
  """

  spec = ToolSpec(
    name="vision.config_detect",
    description="Return a preconfigured pose for a known object query.",
    tags=("vision", "config"),
  )

  def __init__(self, catalog: Mapping[str, list[float]] | None = None) -> None:
    self._catalog: dict[str, list[float]] = {}
    for key, value in (catalog or {}).items():
      self._catalog[key] = [float(item) for item in value]
      lowered = key.lower()
      if lowered != key:
        self._catalog.setdefault(lowered, self._catalog[key])

  def register(self, name: str, pose_3d: list[float]) -> None:
    self._catalog[name] = [float(item) for item in pose_3d]

  def _lookup(self, query: str) -> tuple[str, list[float]] | None:
    if query in self._catalog:
      return query, list(self._catalog[query])
    lowered = query.lower()
    if lowered in self._catalog:
      return lowered, list(self._catalog[lowered])
    for name, pose in self._catalog.items():
      if lowered in name.lower() or name.lower() in lowered:
        return name, list(pose)
    return None

  def run(self, call: ToolCall) -> ToolResult:
    query = call.input.get("query")
    if not isinstance(query, str) or not query:
      return ToolResult(
        tool=self.spec.name,
        success=False,
        error="query must be a non-empty string",
      )
    match = self._lookup(query)
    if match is None:
      return ToolResult(
        tool=self.spec.name,
        success=False,
        output={"found": False, "label": query, "confidence": 0.0},
        error=f"OBJECT_NOT_FOUND: no configured object matches '{query}'",
      )
    label, pose_3d = match
    return ToolResult(
      tool=self.spec.name,
      success=True,
      output={
        "found": True,
        "label": label,
        "confidence": 1.0,
        "object_id": label,
        "pose_3d": pose_3d,
      },
    )
