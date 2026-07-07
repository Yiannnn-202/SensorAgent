"""Structured task logging for SensorAgent."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from sensoragent.schemas import LogRecord, TraceContext


class TaskLogger:
  """In-memory logger with optional JSONL persistence."""

  def __init__(self, jsonl_path: Path | None = None) -> None:
    self._records: list[LogRecord] = []
    self._jsonl_path = jsonl_path
    if self._jsonl_path is not None:
      self._jsonl_path.parent.mkdir(parents=True, exist_ok=True)

  @property
  def records(self) -> list[LogRecord]:
    return list(self._records)

  def log(self, event: str, trace: TraceContext, payload: dict | None = None) -> LogRecord:
    """Append a structured log record."""

    record = LogRecord(
      event=event,
      task_id=trace.task_id,
      trace_id=trace.trace_id,
      payload=payload or {},
    )
    self._records.append(record)
    if self._jsonl_path is not None:
      with self._jsonl_path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")
    return record

  def events(self) -> Iterable[str]:
    """Return event names in emission order."""

    return [record.event for record in self._records]
