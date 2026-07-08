"""In-memory task persistence."""

from __future__ import annotations

from sensoragent.state.task import TaskState


class InMemoryTaskStore:
  """Simple task result persistence for local development and tests."""

  def __init__(self) -> None:
    self._tasks: dict[str, TaskState] = {}

  def save(self, task: TaskState) -> None:
    self._tasks[task.task_id] = task

  def get(self, task_id: str) -> TaskState | None:
    return self._tasks.get(task_id)

  def list(self) -> list[TaskState]:
    return list(self._tasks.values())
