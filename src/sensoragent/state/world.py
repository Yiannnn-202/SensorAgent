"""Minimal competition world state for multi-instance sorting tasks."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping

from sensoragent._compat import StrEnum
from sensoragent.grounding import GroundedInstance


def _now() -> str:
  return datetime.now(timezone.utc).isoformat()


class ObjectStatus(StrEnum):
  ON_TABLE = "on_table"
  OBSERVED = "observed"
  SELECTED = "selected"
  HELD = "held"
  RELEASED = "released"
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
  confidence: float | None = None
  updated_at: str = field(default_factory=_now)


@dataclass
class BinCellState:
  target: str
  occupied_by: str | None = None
  status: str = "empty"
  observed_position: tuple[float, float, float] | None = None
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
      confidence=existing.confidence if existing is not None else None,
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

  def next_empty_cell(self, start_from: str | None = None) -> str | None:
    """Return the first empty cell in target order, optionally after a start.

    Batch tasks fill cells one per instance; when the requested starting cell
    is unavailable the scan continues from wherever that cell sits in the
    configured order. Returns None when every cell is occupied.
    """

    targets = tuple(self.bins)
    if start_from in targets:
      targets = targets[targets.index(start_from):]
    for target in targets:
      if self.bins[target].status == "empty":
        return target
    return None

  def merge_runtime_state(self, runtime_world_state: Mapping[str, Any]) -> None:
    """Merge a DecisionTree run-local world state into this persistent state.

    The run-local state is intentionally a loose dict so workflows can evolve
    without coupling to these dataclasses. This method normalizes only stable
    fields and preserves the raw event history for replay/reporting.
    """

    objects = runtime_world_state.get("objects")
    if isinstance(objects, Mapping):
      for instance_id, raw_object in objects.items():
        if not isinstance(instance_id, str) or not isinstance(raw_object, Mapping):
          continue
        existing = self.objects.get(instance_id)
        pose = _pose_tuple(raw_object.get("pose_3d")) or (
          existing.pose_3d if existing is not None else None
        )
        if pose is None:
          continue
        status = _object_status(raw_object.get("status"), existing.status if existing else ObjectStatus.OBSERVED)
        confidence = raw_object.get("confidence")
        self.objects[instance_id] = ObjectState(
          instance_id=instance_id,
          class_id=str(
            raw_object.get("class_id")
            or raw_object.get("label")
            or (existing.class_id if existing is not None else instance_id)
          ),
          pose_3d=pose,
          source=str(raw_object.get("source") or (existing.source if existing else "runtime_world_state")),
          status=status,
          target=(
            str(raw_object["target"])
            if raw_object.get("target") is not None
            else (existing.target if existing is not None else None)
          ),
          confidence=(
            float(confidence)
            if isinstance(confidence, (int, float)) and not isinstance(confidence, bool)
            else (existing.confidence if existing is not None else None)
          ),
        )

    bins = runtime_world_state.get("bins")
    if isinstance(bins, Mapping):
      for target, raw_bin in bins.items():
        if not isinstance(target, str) or not isinstance(raw_bin, Mapping):
          continue
        cell = self.bins.setdefault(target, BinCellState(target=target))
        occupied_by = raw_bin.get("occupied_by")
        if occupied_by is not None:
          cell.occupied_by = str(occupied_by)
        status = raw_bin.get("status")
        if isinstance(status, str) and status:
          cell.status = status
        observed_position = _pose_tuple(raw_bin.get("observed_position"))
        if observed_position is not None:
          cell.observed_position = observed_position
        cell.updated_at = _now()

    current_task = runtime_world_state.get("current_task")
    if isinstance(current_task, Mapping):
      self.current_task.update(dict(current_task))

    history = runtime_world_state.get("history")
    if isinstance(history, list):
      self.history.extend(
        dict(entry)
        for entry in history
        if isinstance(entry, Mapping)
      )
      self._record("runtime_world_state_merged", event_count=len(history))

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

  def record(self, event: str, **payload) -> None:
    """Append a caller-defined event (batch orchestration, run summaries)."""

    self._record(event, **payload)


def _pose_tuple(value: Any) -> tuple[float, float, float] | None:
  if not isinstance(value, (list, tuple)) or len(value) < 3:
    return None
  if not all(isinstance(item, (int, float)) and not isinstance(item, bool) for item in value[:3]):
    return None
  return (float(value[0]), float(value[1]), float(value[2]))


def _object_status(value: Any, default: ObjectStatus) -> ObjectStatus:
  if isinstance(value, ObjectStatus):
    return value
  if isinstance(value, str):
    try:
      return ObjectStatus(value)
    except ValueError:
      return default
  return default
