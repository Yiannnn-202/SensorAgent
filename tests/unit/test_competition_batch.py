"""Tests for the competition batch runner."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import TestCase

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
  sys.path.insert(0, str(SRC))

from sensoragent.agent import build_agent_from_config
from sensoragent.evaluation.batch import (
  TREE_NAME,
  Injection,
  Scenario,
  _inject_and_run,
  _SequenceTool,
  load_scenarios,
  run_batch,
)
from sensoragent.schemas import ToolCall, ToolResult, ToolSpec, TraceContext

COMPETITION_EVAL = ROOT / "configs" / "competition_eval.yaml"
SCENARIOS_YAML = ROOT / "tests" / "fixtures" / "competition" / "scenarios.yaml"


class _FakeTool:
  def __init__(self, name: str) -> None:
    self.spec = ToolSpec(name=name, description="fake")
    self.calls = 0

  def run(self, call: ToolCall) -> ToolResult:
    self.calls += 1
    return ToolResult(tool=self.spec.name, success=True, output={"real": True})


class SequenceToolTest(TestCase):
  def test_returns_scripted_results_then_delegates(self) -> None:
    wrapped = _FakeTool("x")
    sequenced = _SequenceTool(
      wrapped,
      (
        {"success": False, "error": "boom"},
        {"success": True, "output": {"scripted": True}},
      ),
    )
    call = ToolCall(tool="x", input={}, trace=TraceContext())

    first = sequenced.run(call)
    self.assertFalse(first.success)
    self.assertEqual(first.error, "boom")

    second = sequenced.run(call)
    self.assertTrue(second.success)
    self.assertEqual(second.output, {"scripted": True})

    # Sequence exhausted -> delegate to the wrapped tool.
    third = sequenced.run(call)
    self.assertTrue(third.success)
    self.assertEqual(third.output, {"real": True})
    self.assertEqual(wrapped.calls, 1)


class LoadScenariosTest(TestCase):
  def test_loads_fixture_file(self) -> None:
    scenarios = load_scenarios(SCENARIOS_YAML)
    self.assertGreater(len(scenarios), 1)
    names = [scenario.name for scenario in scenarios]
    self.assertIn("nominal", names)
    self.assertIn("pick_plan_failed", names)
    nominal = next(s for s in scenarios if s.name == "nominal")
    self.assertTrue(nominal.is_nominal)
    injected = next(s for s in scenarios if s.name == "pick_plan_failed")
    self.assertEqual(len(injected.injections), 1)
    self.assertEqual(injected.injections[0].tool, "robot.plan_top_down_pick")

  def test_rejects_file_without_scenarios_list(self) -> None:
    import tempfile

    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as handle:
      handle.write("other: 1\n")
      path = Path(handle.name)
    with self.assertRaises(ValueError):
      load_scenarios(path)


class InjectAndRunTest(TestCase):
  def setUp(self) -> None:
    self.bundle = build_agent_from_config(COMPETITION_EVAL)
    self.tree = self.bundle.decision_trees[TREE_NAME]

  def test_registry_restored_after_injection(self) -> None:
    before = dict(self.bundle.tool_registry._tools)  # noqa: SLF001
    scenario = Scenario(
      name="pick_plan_failed",
      object_query="roller",
      target="bin_cell_3",
      injections=(
        Injection(
          tool="robot.plan_top_down_pick",
          results=({"success": False, "error": "PLAN_TOP_DOWN_PICK failed: IK unreachable"},),
        ),
      ),
    )
    _inject_and_run(self.bundle, self.tree, scenario, TraceContext())
    after = dict(self.bundle.tool_registry._tools)  # noqa: SLF001
    # Same keys, and the original tool object is restored (not the wrapper).
    self.assertEqual(before.keys(), after.keys())
    self.assertIs(
      before["robot.plan_top_down_pick"], after["robot.plan_top_down_pick"]
    )


class RunBatchTest(TestCase):
  def test_run_batch_collects_records_and_baseline(self) -> None:
    scenarios = (
      Scenario(name="nominal", object_query="roller", target="bin_cell_3"),
      Scenario(
        name="pick_plan_failed",
        object_query="roller",
        target="bin_cell_3",
        injections=(
          Injection(
            tool="robot.plan_top_down_pick",
            results=(
              {"success": False, "error": "PLAN_TOP_DOWN_PICK failed: IK unreachable"},
            ),
          ),
        ),
      ),
    )
    records, baseline = run_batch(scenarios, COMPETITION_EVAL)

    self.assertEqual(len(records), 2)
    by_name = {record.run_id: record for record in records}

    nominal = by_name["nominal"]
    injected = by_name["pick_plan_failed"]
    self.assertTrue(nominal.success, msg=f"nominal failed: {nominal.error}")
    # Injection triggers recovery; the planted failure classifies as PICK_PLAN_FAILED.
    self.assertGreater(injected.recovery_attempts, 0)
    self.assertEqual(injected.failure_type, "PICK_PLAN_FAILED")
    # Nominal succeeded -> baseline 1.0 (recovery_gain undefined at baseline=1).
    self.assertAlmostEqual(baseline, 1.0)

  def test_explicit_baseline_overrides_nominal(self) -> None:
    scenarios = (Scenario(name="nominal", object_query="roller", target="bin_cell_3"),)
    _, baseline = run_batch(scenarios, COMPETITION_EVAL, baseline_success_rate=0.4)
    self.assertAlmostEqual(baseline, 0.4)


if __name__ == "__main__":
  unittest.main()
