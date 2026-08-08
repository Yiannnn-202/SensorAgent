"""Competition-level evaluation metrics for agent task runs.

Mirrors the structure of :mod:`sensoragent.evaluation.vision` (per-row dict ->
aggregate summary -> acceptance thresholds -> persisted run) but operates on
*task-level* runs instead of per-image detection samples. The metric math is
intentionally independent: vision evaluation measures IoU on bounding boxes,
while this module measures end-to-end success, recovery behaviour, and failure
branch coverage on DecisionTree / ActionList runs.

The reducer is offline and decoupled from the runtime: ``extract_run_record``
normalizes a ``DecisionTreeResult`` / ``TaskState`` / serialized payload into a
``RunRecord``, ``summarize`` aggregates a batch, and ``evaluate_runs`` persists
``results.jsonl`` + ``summary.json``.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from sensoragent.recovery.failures import FailureType

_RUN_ID_PREFIX = "run_"


@dataclass
class RunRecord:
  """Normalized view of a single agent task run for aggregation."""

  run_id: str
  task_id: str | None = None
  selected_plan: dict[str, Any] = field(default_factory=dict)
  parsed_intent: dict[str, Any] | None = None
  final_status: str = "UNKNOWN"
  success: bool = False
  failure_type: str | None = None
  recovery_attempts: int = 0
  recovery_history: list[dict[str, Any]] = field(default_factory=list)
  node_names: list[str] = field(default_factory=list)
  error: str | None = None
  source: str = "unknown"

  def to_dict(self) -> dict[str, Any]:
    return asdict(self)


@dataclass(frozen=True)
class CompetitionThresholds:
  """Optional pass/fail gates for a competition evaluation run."""

  min_success_rate: float | None = None
  min_recovery_success_rate: float | None = None
  max_avg_recovery_cost: float | None = None
  min_branch_coverage: float | None = None


@dataclass(frozen=True)
class CompetitionEvaluationRun:
  """Persisted rows, aggregate summary, and acceptance result."""

  rows: tuple[dict[str, Any], ...]
  summary: dict[str, Any]
  failures: tuple[str, ...]

  @property
  def passed(self) -> bool:
    return not self.failures


# ---------------------------------------------------------------------------
# Extraction / normalization
# ---------------------------------------------------------------------------


def _coerce_output(value: Any) -> dict[str, Any]:
  """Return the run context dict from a result object or mapping."""

  output = getattr(value, "output", None)
  if isinstance(output, Mapping):
    return dict(output)
  if isinstance(value, Mapping):
    return dict(value)
  return {}


def _node_names_from(nodes: Any) -> list[str]:
  names: list[str] = []
  if not isinstance(nodes, Sequence) or isinstance(nodes, (str, bytes)):
    return names
  for node in nodes:
    if isinstance(node, Mapping):
      name = node.get("node") or node.get("name")
    else:
      name = getattr(node, "node", None) or getattr(node, "name", None)
    names.append(str(name) if name is not None else "")
  return names


def extract_run_record(
  result: Any,
  *,
  task_state: Any = None,
  run_id: str | None = None,
) -> RunRecord:
  """Normalize a workflow result or output dict into a :class:`RunRecord`.

  ``result`` may be a ``DecisionTreeResult`` / ``ActionListResult`` (uses
  ``.output`` / ``.success`` / ``.nodes``), a serialized payload with the same
  shape (a top-level ``output`` mapping plus ``success``), or a bare context
  dict. When ``task_state`` is supplied it is authoritative for the run outcome
  (``status``), identity (``task_id``), and selected plan.
  """

  if isinstance(result, Mapping):
    nested = result.get("output")
    context = dict(nested) if isinstance(nested, Mapping) else dict(result)
    result_success = bool(result.get("success", context.get("success", False)))
    error = result.get("error") or context.get("error")
    nodes_value = result.get("nodes") or []
    source = "dict"
  else:
    context = _coerce_output(result)
    result_success = bool(getattr(result, "success", False))
    error = getattr(result, "error", None)
    nodes_value = getattr(result, "nodes", []) or []
    source = type(result).__name__

  task_id: str | None = None
  selected_plan: dict[str, Any] = {}
  success = result_success
  final_status = "SUCCEEDED" if success else "FAILED"

  if task_state is not None:
    task_id = getattr(task_state, "task_id", None)
    plan = getattr(task_state, "plan", None)
    if hasattr(plan, "to_dict"):
      selected_plan = plan.to_dict()
    elif isinstance(plan, Mapping):
      selected_plan = dict(plan)
    status = getattr(task_state, "status", None)
    status_str = str(status).upper() if status is not None else ""
    if status_str:
      success = status_str == "SUCCEEDED"
      final_status = status_str
    source = "task_state"

  intent_value = (
    selected_plan.get("intent") if isinstance(selected_plan, Mapping) else None
  )
  parsed_intent = dict(intent_value) if isinstance(intent_value, Mapping) else None

  recovery_history = [
    dict(attempt)
    for attempt in (context.get("recovery_history") or [])
    if isinstance(attempt, Mapping)
  ]
  classification = context.get("classification")
  failure_type: str | None = None
  if isinstance(classification, Mapping):
    failure_type = classification.get("failure_type")
  elif isinstance(context.get("last_failure"), Mapping):
    failure_type = context["last_failure"].get("failure_type")

  return RunRecord(
    run_id=run_id or task_id or "",
    task_id=task_id,
    selected_plan=selected_plan,
    parsed_intent=parsed_intent,
    final_status=final_status,
    success=success,
    failure_type=failure_type,
    recovery_attempts=int(context.get("recovery_attempts") or 0),
    recovery_history=recovery_history,
    node_names=_node_names_from(nodes_value),
    error=error,
    source=source,
  )


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


def _mean(values: Sequence[float]) -> float | None:
  cleaned = [
    value
    for value in values
    if isinstance(value, (int, float)) and not isinstance(value, bool)
  ]
  return round(sum(cleaned) / len(cleaned), 6) if cleaned else None


def _safe_rate(numerator: int, denominator: int) -> float | None:
  return round(numerator / denominator, 6) if denominator else None


def _is_schema_error(error: str | None) -> bool:
  if not isinstance(error, str) or not error:
    return False
  lowered = error.lower()
  return any(
    token in lowered for token in ("schema", "validation", "missing required", "unknown ")
  )


def summarize(
  records: Sequence[RunRecord],
  *,
  baseline_success_rate: float | None = None,
) -> dict[str, Any]:
  """Aggregate a batch of run records into a competition metrics summary.

  ``baseline_success_rate`` is the end-to-end success rate of a *recovery
  disabled* baseline (provided later by the experiment runner). When supplied
  and strictly below 1, ``recovery_gain`` reports the classic lift
  ``(success_rate - baseline) / (1 - baseline)``; otherwise it is ``None``.
  """

  records = list(records)
  run_count = len(records)
  success_count = sum(1 for record in records if record.success)
  success_rate = _safe_rate(success_count, run_count)

  recovery_triggered = [record for record in records if record.recovery_attempts > 0]
  recovery_triggered_count = len(recovery_triggered)
  recovery_success_count = sum(1 for record in recovery_triggered if record.success)
  recovery_triggered_rate = _safe_rate(recovery_triggered_count, run_count)
  recovery_success_rate = _safe_rate(recovery_success_count, recovery_triggered_count)
  avg_recovery_cost = _mean(
    [float(record.recovery_attempts) for record in recovery_triggered]
  )

  recovery_gain: float | None = None
  if (
    baseline_success_rate is not None
    and success_rate is not None
    and baseline_success_rate < 1
  ):
    recovery_gain = round(
      (success_rate - baseline_success_rate) / (1 - baseline_success_rate), 6
    )

  attempt_failure_distribution: dict[str, int] = {}
  terminal_failure_distribution: dict[str, int] = {}
  strategy_distribution: dict[str, int] = {}
  observed_failure_types: set[str] = set()
  for record in records:
    for attempt in record.recovery_history:
      failure_type = attempt.get("failure_type")
      if isinstance(failure_type, str) and failure_type:
        attempt_failure_distribution[failure_type] = (
          attempt_failure_distribution.get(failure_type, 0) + 1
        )
        observed_failure_types.add(failure_type)
      strategy = attempt.get("strategy")
      if isinstance(strategy, str) and strategy:
        strategy_distribution[strategy] = strategy_distribution.get(strategy, 0) + 1
    if isinstance(record.failure_type, str) and record.failure_type:
      terminal_failure_distribution[record.failure_type] = (
        terminal_failure_distribution.get(record.failure_type, 0) + 1
      )
      observed_failure_types.add(record.failure_type)

  known_failure_types = len(FailureType)
  branch_coverage_rate = _safe_rate(len(observed_failure_types), known_failure_types)

  parsed_count = sum(
    1
    for record in records
    if record.selected_plan and record.selected_plan.get("target")
  )
  valid_count = sum(
    1
    for record in records
    if record.selected_plan
    and record.selected_plan.get("target")
    and not _is_schema_error(record.error)
  )

  return {
    "run_count": run_count,
    "success_count": success_count,
    "end_to_end_success_rate": success_rate,
    "recovery": {
      "triggered_count": recovery_triggered_count,
      "triggered_rate": recovery_triggered_rate,
      "success_rate": recovery_success_rate,
      "avg_recovery_cost": avg_recovery_cost,
      "recovery_gain": recovery_gain,
      "baseline_success_rate": baseline_success_rate,
    },
    "failure_type_distribution": attempt_failure_distribution,
    "terminal_failure_distribution": terminal_failure_distribution,
    "strategy_distribution": strategy_distribution,
    "branch_coverage": {
      "observed_failure_types": sorted(observed_failure_types),
      "known_failure_types": known_failure_types,
      "rate": branch_coverage_rate,
    },
    "planner": {
      "parse_accuracy": _safe_rate(parsed_count, run_count),
      "sequence_validity": _safe_rate(valid_count, run_count),
    },
    # Placeholders, populated once visual-verification postconditions and a
    # completeness audit land (later stages of the evaluation plan).
    "robot_logic_consistency": None,
    "sequence_completeness": None,
  }


def check_acceptance(
  summary: dict[str, Any],
  thresholds: CompetitionThresholds,
) -> tuple[str, ...]:
  """Compare aggregate metrics with requested acceptance gates."""

  failures: list[str] = []
  if thresholds.min_success_rate is not None:
    rate = summary.get("end_to_end_success_rate")
    if rate is None or rate < thresholds.min_success_rate:
      failures.append(
        f"end_to_end_success_rate {rate} < min_success_rate {thresholds.min_success_rate}"
      )

  recovery = summary.get("recovery") or {}
  recovery_triggered = bool(recovery.get("triggered_count"))
  if recovery_triggered and thresholds.min_recovery_success_rate is not None:
    rate = recovery.get("success_rate")
    if rate is None or rate < thresholds.min_recovery_success_rate:
      failures.append(
        f"recovery.success_rate {rate} < min_recovery_success_rate "
        f"{thresholds.min_recovery_success_rate}"
      )
  if recovery_triggered and thresholds.max_avg_recovery_cost is not None:
    cost = recovery.get("avg_recovery_cost")
    if cost is None or cost > thresholds.max_avg_recovery_cost:
      failures.append(
        f"recovery.avg_recovery_cost {cost} > max_avg_recovery_cost "
        f"{thresholds.max_avg_recovery_cost}"
      )

  if thresholds.min_branch_coverage is not None:
    rate = (summary.get("branch_coverage") or {}).get("rate")
    if rate is None or rate < thresholds.min_branch_coverage:
      failures.append(
        f"branch_coverage {rate} < min_branch_coverage {thresholds.min_branch_coverage}"
      )

  return tuple(failures)


def evaluate_runs(
  records_or_results: Iterable[Any],
  *,
  output_dir: Path | str,
  thresholds: CompetitionThresholds | None = None,
  baseline_success_rate: float | None = None,
) -> CompetitionEvaluationRun:
  """Normalize a batch of runs, aggregate, persist, and return the run.

  Each item may be a :class:`RunRecord`, a workflow result / output payload
  (passed through :func:`extract_run_record`), or a ``(result, task_state)``
  pair. Writes ``results.jsonl`` (one row per run) and ``summary.json`` into
  ``output_dir``.
  """

  output_dir = Path(output_dir)
  output_dir.mkdir(parents=True, exist_ok=True)

  records: list[RunRecord] = []
  for index, item in enumerate(records_or_results):
    if isinstance(item, RunRecord):
      record = item
    elif isinstance(item, tuple) and len(item) == 2:
      record = extract_run_record(item[0], task_state=item[1])
    else:
      record = extract_run_record(item)
    if not record.run_id:
      record.run_id = f"{_RUN_ID_PREFIX}{index}"
    records.append(record)

  rows = tuple(record.to_dict() for record in records)
  summary = summarize(records, baseline_success_rate=baseline_success_rate)
  failures = check_acceptance(summary, thresholds) if thresholds is not None else ()

  results_path = output_dir / "results.jsonl"
  with results_path.open("w", encoding="utf-8") as handle:
    for row in rows:
      handle.write(json.dumps(row, ensure_ascii=False) + "\n")

  summary_path = output_dir / "summary.json"
  with summary_path.open("w", encoding="utf-8") as handle:
    json.dump(summary, handle, ensure_ascii=False, indent=2)

  return CompetitionEvaluationRun(rows=rows, summary=summary, failures=failures)
