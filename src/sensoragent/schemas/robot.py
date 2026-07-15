"""Robot motion schemas shared by tools and skills."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


def _numeric_tuple(value: Any, size: int, field: str) -> tuple[float, ...]:
  if not isinstance(value, (list, tuple)) or len(value) != size:
    raise ValueError(f"{field} must contain {size} numeric values")
  if not all(isinstance(item, (int, float)) and not isinstance(item, bool) for item in value):
    raise ValueError(f"{field} must contain {size} numeric values")
  return tuple(float(item) for item in value)


@dataclass(frozen=True)
class RobotPose:
  """Backend-neutral Cartesian pose."""

  position: tuple[float, float, float]
  orientation: tuple[float, float, float, float]
  frame_id: str = "base_link"

  @classmethod
  def from_dict(cls, value: dict[str, Any]) -> "RobotPose":
    if not isinstance(value, dict):
      raise ValueError("pose must be an object")
    frame_id = value.get("frame_id", "base_link")
    if not isinstance(frame_id, str) or not frame_id:
      raise ValueError("pose.frame_id must be a non-empty string")
    return cls(
      position=_numeric_tuple(value.get("position"), 3, "pose.position"),
      orientation=_numeric_tuple(value.get("orientation"), 4, "pose.orientation"),
      frame_id=frame_id,
    )

  def to_dict(self) -> dict[str, Any]:
    return {
      "position": list(self.position),
      "orientation": list(self.orientation),
      "frame_id": self.frame_id,
    }

  def offset_z(self, distance: float) -> "RobotPose":
    x, y, z = self.position
    return RobotPose(
      position=(x, y, z + float(distance)),
      orientation=self.orientation,
      frame_id=self.frame_id,
    )


@dataclass(frozen=True)
class PickPlan:
  """Cartesian waypoints for a top-down pick."""

  approach: RobotPose
  pregrasp: RobotPose
  grasp: RobotPose
  lift: RobotPose

  @classmethod
  def from_dict(cls, value: dict[str, Any]) -> "PickPlan":
    if not isinstance(value, dict):
      raise ValueError("plan must be an object")
    return cls(
      approach=RobotPose.from_dict(value.get("approach")),
      pregrasp=RobotPose.from_dict(value.get("pregrasp")),
      grasp=RobotPose.from_dict(value.get("grasp")),
      lift=RobotPose.from_dict(value.get("lift")),
    )

  def to_dict(self) -> dict[str, Any]:
    return {
      "approach": self.approach.to_dict(),
      "pregrasp": self.pregrasp.to_dict(),
      "grasp": self.grasp.to_dict(),
      "lift": self.lift.to_dict(),
    }


@dataclass(frozen=True)
class PlacePlan:
  """Cartesian waypoints for a place operation."""

  approach: RobotPose
  place: RobotPose
  retreat: RobotPose

  @classmethod
  def from_dict(cls, value: dict[str, Any]) -> "PlacePlan":
    if not isinstance(value, dict):
      raise ValueError("plan must be an object")
    return cls(
      approach=RobotPose.from_dict(value.get("approach")),
      place=RobotPose.from_dict(value.get("place")),
      retreat=RobotPose.from_dict(value.get("retreat")),
    )

  def to_dict(self) -> dict[str, Any]:
    return {
      "approach": self.approach.to_dict(),
      "place": self.place.to_dict(),
      "retreat": self.retreat.to_dict(),
    }
