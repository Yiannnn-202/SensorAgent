"""Batch experiment runner for competition evaluation.

Drives the industrial recovery DecisionTree across a list of scenarios on a
real (fake-backend) bundle, injecting scripted failures into individual tools
so recovery behaviour is exercised and collected into RunRecords for the
competition metrics reducer.

Decoupled from Gazebo/ROS: it builds the agent from a fake-backend config
(e.g. configs/competition_eval.yaml), wraps specific tools with _SequenceTool to
plant failures, runs the recovery tree directly via
``bundle.decision_tree_runtime.run`` (bypassing the planner — object_query and
target are known per scenario), and feeds each DecisionTreeResult into
extract_run_record. Injection covers tool_runtime only; skill-level injections
(e.g. GRASP_EMPTY via robot.verify_grasp) are left for a later stage.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import yaml

from sensoragent.agent import build_agent_from_config
from sensoragent.evaluation.competition import RunRecord, extract_run_record
from sensoragent.schemas import ToolCall, ToolResult, TraceContext
from sensoragent.tools.base import Tool

TREE_NAME = "industrial.recovery_pick_place_tree"


@dataclass(frozen=True)
class Injection:
  """Scripted results for one tool, consumed in order before delegating."""

  tool: str
  results: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class Scenario:
  """One recovery-tree run with optional failure injections."""

  name: str
  object_query: str
  target: str
  injections: tuple[Injection, ...] = ()
  spatial_constraint: dict[str, Any] | None = None
  max_recovery_attempts: int | None = None

  @property
  def is_nominal(self) -> bool:
    return not self.injections

  def request_input(self) -> dict[str, Any]:
    request: dict[str, Any] = {
      "object_query": self.object_query,
      "target": self.target,
    }
    if self.spatial_constraint is not None:
      request["spatial_constraint"] = self.spatial_constraint
    if self.max_recovery_attempts is not None:
      request["max_recovery_attempts"] = self.max_recovery_attempts
    return request


def load_scenarios(path: Path | str) -> list[Scenario]:
  """Load scenarios from a YAML file with a top-level ``scenarios`` list."""

  raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
  entries = raw.get("scenarios") if isinstance(raw, dict) else None
  if not isinstance(entries, list):
    raise ValueError(f"No 'scenarios' list found in {path}")
  scenarios: list[Scenario] = []
  for entry in entries:
    if not isinstance(entry, dict):
      raise ValueError(f"Scenario entry must be a mapping: {entry!r}")
    injections = tuple(
      Injection(
        tool=str(item["tool"]),
        results=tuple(item.get("results") or ()),
      )
      for item in (entry.get("injections") or ())
      if isinstance(item, dict) and item.get("tool")
    )
    scenarios.append(
      Scenario(
        name=str(entry["name"]),
        object_query=str(entry["object_query"]),
        target=str(entry["target"]),
        injections=injections,
        spatial_constraint=entry.get("spatial_constraint"),
        max_recovery_attempts=entry.get("max_recovery_attempts"),
      )
    )
  return scenarios


class _SequenceTool:
  """Wrap a real tool; return scripted ToolResults in order, then delegate."""

  def __init__(self, wrapped: Tool, results: tuple[dict[str, Any], ...]) -> None:
    self.spec = wrapped.spec
    self._wrapped = wrapped
    self._results = results
    self._index = 0

  def run(self, call: ToolCall) -> ToolResult:
    if self._index < len(self._results):
      scripted = self._results[self._index]
      self._index += 1
      return ToolResult(
        tool=self.spec.name,
        success=bool(scripted.get("success", False)),
        output=scripted.get("output"),
        error=scripted.get("error"),
      )
    return self._wrapped.run(call)


def _inject_and_run(
  bundle: Any,
  tree: Any,
  scenario: Scenario,
  trace: TraceContext,
) -> Any:
  """Wrap scenario tools, run the tree, then restore the original registry."""

  registry = bundle.tool_registry
  original = dict(registry._tools)  # noqa: SLF001 — save/restore isolation
  try:
    for injection in scenario.injections:
      wrapped = registry.get(injection.tool)
      registry._tools[injection.tool] = _SequenceTool(  # noqa: SLF001
        wrapped, injection.results
      )
    return bundle.decision_tree_runtime.run(tree, scenario.request_input(), trace)
  finally:
    registry._tools = original  # noqa: SLF001


def run_batch(
  scenarios: Sequence[Scenario],
  config_path: Path | str,
  *,
  baseline_success_rate: float | None = None,
) -> tuple[list[RunRecord], float | None]:
  """Run every scenario on one fake-backend bundle; return records + baseline.

  An explicit ``baseline_success_rate`` override wins; otherwise the success
  rate of nominal (injection-free) scenarios is used. Note a nominal baseline is
  typically 1.0, for which ``recovery_gain`` is undefined — a strict
  no-recovery baseline (max_recovery_attempts=0 variant) is a later stage.
  """

  bundle = build_agent_from_config(Path(config_path))
  tree = bundle.decision_trees[TREE_NAME]
  records: list[RunRecord] = []
  nominal_success = 0
  nominal_total = 0
  for scenario in scenarios:
    result = _inject_and_run(bundle, tree, scenario, TraceContext())
    record = extract_run_record(result, run_id=scenario.name)
    records.append(record)
    if scenario.is_nominal:
      nominal_total += 1
      if record.success:
        nominal_success += 1
  nominal_rate = (
    round(nominal_success / nominal_total, 6) if nominal_total else None
  )
  baseline = (
    baseline_success_rate
    if baseline_success_rate is not None
    else nominal_rate
  )
  return records, baseline
