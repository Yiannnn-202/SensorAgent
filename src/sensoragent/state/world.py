"""Minimal competition world state for multi-instance sorting tasks."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import StrEnum

from sensoragent.grounding import GroundedInstance


def _now() -> str:
  return datetime.now(timezone.utc).isoformat()


class ObjectStatus(StrEnum):
  ON_TABLE = "on_table"
  SELECTED = "selected"
  HELD = "held"
  PLACED = "placed"
  UNKNOWN = "unknown"


@dataclass
class ObjectState:
  instance_id: str
  class_id: str
  pose_3d: tuple[float, float, float]
  source: str
  status: ObjectStatus = ObjectStatus.ON_TABLE
  target: str | None = None
  updated_at: str = field(default_factory=_now)


@dataclass
class BinCellState:
  target: str
  occupied_by: str | None = None
  status: str = "empty"
  updated_at: str = field(default_factory=_now)


class CompetitionWorldState:
  """Track task-local object and bin state without claiming persistent SLAM."""

  def __init__(self, place_targets: tuple[str, ...]) -> None:
    self.objects: dict[str, ObjectState] = {}
    self.bins = {
      target: BinCellState(target=target)
      for target in place_targets
    }
    self.current_task: dict = {}
    self.history: list[dict] = []

  @property
  def placed_instances(self) -> set[str]:
    return {
      instance_id
      for instance_id, state in self.objects.items()
      if state.status == ObjectStatus.PLACED
    }

  @property
  def unavailable_instances(self) -> set[str]:
    return {
      instance_id
      for instance_id, state in self.objects.items()
      if state.status in {ObjectStatus.PLACED, ObjectStatus.UNKNOWN}
    }

  def observe(self, instance: GroundedInstance) -> None:
    existing = self.objects.get(instance.instance_id)
    if existing is not None and existing.status == ObjectStatus.PLACED:
      return
    self.objects[instance.instance_id] = ObjectState(
      instance_id=instance.instance_id,
      class_id=instance.class_id,
      pose_3d=instance.pose_3d,
      source=instance.source,
      status=existing.status if existing is not None else ObjectStatus.ON_TABLE,
    )

  def select(self, instance_id: str, target: str | None) -> None:
    state = self.objects[instance_id]
    state.status = ObjectStatus.SELECTED
    state.target = target
    state.updated_at = _now()
    self.current_task = {
      "instance_id": instance_id,
      "target": target,
      "step": "selected",
      "recovery_attempts": 0,
    }
    self._record("object_selected", instance_id=instance_id, target=target)

  def mark_placed(self, instance_id: str, target: str) -> None:
    state = self.objects[instance_id]
    state.status = ObjectStatus.PLACED
    state.target = target
    state.updated_at = _now()
    cell = self.bins[target]
    cell.occupied_by = instance_id
    cell.status = "occupied"
    cell.updated_at = _now()
    self.current_task["step"] = "completed"
    self._record("object_placed", instance_id=instance_id, target=target)

  def mark_failed(self, instance_id: str, error: str) -> None:
    state = self.objects[instance_id]
    state.status = ObjectStatus.UNKNOWN
    state.updated_at = _now()
    self.current_task["step"] = "failed"
    self.current_task["error"] = error
    self._record("task_failed", instance_id=instance_id, error=error)

  def increment_recovery(self) -> None:
    attempts = int(self.current_task.get("recovery_attempts", 0)) + 1
    self.current_task["recovery_attempts"] = attempts
    self._record("recovery_started", attempt=attempts)

  def target_available(self, target: str) -> bool:
    cell = self.bins.get(target)
    return cell is not None and cell.status == "empty"

  def to_dict(self) -> dict:
    return {
      "objects": {
        key: asdict(value)
        for key, value in self.objects.items()
      },
      "bins": {
        key: asdict(value)
        for key, value in self.bins.items()
      },
      "current_task": dict(self.current_task),
      "history": list(self.history),
    }

  def _record(self, event: str, **payload) -> None:
    self.history.append({"event": event, "timestamp": _now(), **payload})
