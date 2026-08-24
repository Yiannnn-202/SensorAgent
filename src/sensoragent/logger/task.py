"""Structured task logging for SensorAgent."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Iterable

from sensoragent.schemas import LogRecord, TraceContext


def _target_from_payload(payload: dict) -> str:
  if payload.get("tool"):
    return str(payload["tool"])
  if payload.get("skill"):
    return str(payload["skill"])
  if payload.get("decision_tree"):
    return str(payload["decision_tree"])
  if payload.get("actionlist"):
    return str(payload["actionlist"])
  return ""


def _format_console_event(event: str, payload: dict) -> str | None:
  """Return a concise human-readable progress line for important events."""

  if event == "listen_task_started":
    return f"[listen] config={payload.get('config')} planner={payload.get('planner')}"
  if event == "listen_task_transcribed":
    output = payload.get("output") or {}
    text = str(output.get("text", "")).strip()
    return (
      f"[audio] transcribed {output.get('duration_ms')} ms "
      f"text={json.dumps(text, ensure_ascii=False)}"
    )
  if event == "listen_task_agent_started":
    task_input = payload.get("input") or {}
    return (
      "[agent] planning from transcript "
      f"text={json.dumps(task_input.get('user_input', ''), ensure_ascii=False)}"
    )
  if event == "listen_task_finished":
    return (
      f"[listen] finished success={payload.get('success')} "
      f"status={payload.get('status')} error={payload.get('error')}"
    )
  if event == "listen_task_failed":
    return (
      f"[listen] failed stage={payload.get('stage')} "
      f"error={payload.get('error')}"
    )

  if event == "tool_call_started":
    return f"[tool] start {_target_from_payload(payload)}"
  if event == "tool_call_attempt_failed":
    return (
      f"[tool] retry {_target_from_payload(payload)} "
      f"attempt={payload.get('attempt')} error={payload.get('error')}"
    )
  if event == "tool_call_finished":
    status = "ok" if payload.get("success") else "fail"
    return (
      f"[tool] {status} {_target_from_payload(payload)} "
      f"error={payload.get('error')}"
    )

  if event == "skill_call_started":
    return f"[skill] start {_target_from_payload(payload)}"
  if event == "skill_call_finished":
    status = "ok" if payload.get("success") else "fail"
    return (
      f"[skill] {status} {_target_from_payload(payload)} "
      f"error={payload.get('error')}"
    )

  if event == "agent_request_started":
    target = (
      payload.get("decision_tree")
      or payload.get("actionlist")
      or payload.get("skill")
      or "unknown"
    )
    return f"[agent] execute {target}"
  if event == "agent_request_finished":
    status = "ok" if payload.get("success") else "fail"
    return f"[agent] {status} error={payload.get('error')}"

  if event == "decision_tree_started":
    return f"[tree] start {payload.get('decision_tree')}"
  if event == "decision_node_started":
    return (
      f"[tree] node {payload.get('node')} "
      f"kind={payload.get('kind')}"
    )
  if event == "decision_node_attempt_failed":
    return (
      f"[tree] retry node={payload.get('node')} "
      f"attempt={payload.get('attempt')} error={payload.get('error')}"
    )
  if event == "decision_node_finished":
    status = "ok" if payload.get("success") else "fail"
    return (
      f"[tree] {status} node={payload.get('node')} "
      f"attempts={payload.get('attempts')} error={payload.get('error')}"
    )
  if event == "decision_tree_finished":
    status = "ok" if payload.get("success") else "fail"
    return f"[tree] {status} {payload.get('decision_tree')} error={payload.get('error')}"

  if event == "actionlist_started":
    return f"[actionlist] start {payload.get('actionlist')}"
  if event == "action_step_started":
    return f"[actionlist] step {payload.get('step')} target={payload.get('target')}"
  if event == "action_step_finished":
    status = "ok" if payload.get("success") else "fail"
    return (
      f"[actionlist] {status} step={payload.get('step')} "
      f"error={payload.get('error')}"
    )
  if event == "actionlist_finished":
    status = "ok" if payload.get("success") else "fail"
    return f"[actionlist] {status} {payload.get('actionlist')} error={payload.get('error')}"

  if event == "llm_plan_started":
    return f"[llm] request input={json.dumps(payload.get('user_input', ''), ensure_ascii=False)}"
  if event == "llm_plan_finished":
    return f"[llm] plan target={payload.get('target')} kind={payload.get('target_kind')}"

  if event == "task_started":
    return f"[agent] task start input={json.dumps(payload.get('user_input', ''), ensure_ascii=False)}"
  if event == "task_planned":
    return f"[agent] task plan target={payload.get('plan', {}).get('target')}"
  if event == "task_succeeded":
    return f"[agent] task ok task_id={payload.get('task_id')}"
  if event == "task_failed":
    return f"[agent] task fail error={payload.get('error')}"

  return None


class TaskLogger:
  """In-memory logger with optional JSONL persistence."""

  def __init__(
    self,
    jsonl_path: Path | None = None,
    *,
    console: bool = False,
    progress_path: Path | None = None,
  ) -> None:
    self._records: list[LogRecord] = []
    self._jsonl_path = jsonl_path
    self._progress_path = progress_path
    self._console = console
    if self._jsonl_path is not None:
      self._jsonl_path.parent.mkdir(parents=True, exist_ok=True)
    if self._progress_path is not None:
      self._progress_path.parent.mkdir(parents=True, exist_ok=True)

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
    # Format the human-readable line once and emit to whichever sinks are
    # enabled. Unknown events return None from _format_console_event and are
    # skipped by both sinks, so neither produces noise.
    line: str | None = None
    if self._console or self._progress_path is not None:
      line = _format_console_event(event, record.payload)
    if line is not None:
      if self._console :
        print(line, file=sys.stderr, flush=True)
      if self._progress_path is not None:
        # record.timestamp is the fixed-format ISO output of utc_now_iso();
        # slice the leading "YYYY-MM-DD HH:MM:SS" for ordered offline reading.
        stamp = record.timestamp[:19].replace("T", " ")
        with self._progress_path.open("a", encoding="utf-8") as stream:
          stream.write(f"{stamp} {line}\n")
    return record

  def events(self) -> Iterable[str]:
    """Return event names in emission order."""

    return [record.event for record in self._records]
