"""Configuration-driven object detection tool for simulation runs."""

from __future__ import annotations

from typing import Mapping

from sensoragent.schemas import ToolCall, ToolResult, ToolSpec


DEFAULT_GRASP_ORIENTATION = [0.0, 1.0, 0.0, 0.0]


def _profile_float(profile: Mapping[str, object], key: str, default: float) -> float:
  value = profile.get(key, default)
  if not isinstance(value, (int, float)) or isinstance(value, bool):
    raise ValueError(f"release_profiles.{key} must be numeric")
  return float(value)


def _profile_orientation(profile: Mapping[str, object]) -> list[float]:
  value = profile.get("grasp_orientation", DEFAULT_GRASP_ORIENTATION)
  if (
    not isinstance(value, (list, tuple))
    or len(value) != 4
    or not all(isinstance(item, (int, float)) and not isinstance(item, bool) for item in value)
  ):
    raise ValueError("release_profiles.grasp_orientation must contain four numbers")
  return [float(item) for item in value]


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

  def __init__(self, catalog: Mapping[str, list[float]] | None = None, release_profiles: Mapping[str, Mapping[str, object]] | None = None) -> None:
    self._catalog: dict[str, list[float]] = {}
    self._release_profiles = dict(release_profiles or {})
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
    profile = {
      **self._release_profiles.get("default", {}),
      **self._release_profiles.get(label, {}),
    }
    return ToolResult(
      tool=self.spec.name,
      success=True,
      output={
        "found": True,
        "label": label,
        "confidence": 1.0,
        "object_id": label,
        "pose_3d": pose_3d,
        "release_opening": _profile_float(profile, "opening", 0.0848),
        "release_z": _profile_float(profile, "place_z", 0.25),
        "pick_offset_z": _profile_float(profile, "pick_offset_z", 0.04),
        "grasp_orientation": _profile_orientation(profile),
      },
    )
