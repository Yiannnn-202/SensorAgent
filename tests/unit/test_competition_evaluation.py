"""Tests for the competition evaluation metrics reducer."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from sensoragent.evaluation.competition import (
  CompetitionEvaluationRun,
  CompetitionThresholds,
  RunRecord,
  check_acceptance,
  evaluate_runs,
  extract_run_record,
  summarize,
)
from sensoragent.recovery.failures import FailureType


def _record(
  run_id: str,
  *,
  success: bool = True,
  recovery_attempts: int = 0,
  failure_type: str | None = None,
  recovery_history: tuple[dict, ...] = (),
  target: str | None = "industrial.recovery_pick_place_tree",
  error: str | None = None,
) -> RunRecord:
  return RunRecord(
    run_id=run_id,
    selected_plan=(
      {"target": target, "target_kind": "DECISION_TREE"} if target else {}
    ),
    success=success,
    recovery_attempts=recovery_attempts,
    failure_type=failure_type,
    recovery_history=list(recovery_history),
    error=error,
    final_status="SUCCEEDED" if success else "FAILED",
  )


class SummarizeMetricsTest(unittest.TestCase):
  def test_empty_batch_yields_none_rates(self) -> None:
    summary = summarize([])
    self.assertEqual(summary["run_count"], 0)
    self.assertIsNone(summary["end_to_end_success_rate"])
    self.assertIsNone(summary["recovery"]["success_rate"])
    self.assertIsNone(summary["recovery"]["avg_recovery_cost"])
    self.assertEqual(summary["failure_type_distribution"], {})

  def test_end_to_end_success_rate_and_recovery_rates(self) -> None:
    records = [
      _record("1", success=True, recovery_attempts=0),
      _record("2", success=False, recovery_attempts=1, failure_type="GRASP_EMPTY"),
      _record("3", success=True, recovery_attempts=2, failure_type="WRONG_BIN"),
      _record("4", success=False, recovery_attempts=1, failure_type="PICK_PLAN_FAILED"),
    ]
    summary = summarize(records)
    self.assertEqual(summary["run_count"], 4)
    self.assertEqual(summary["success_count"], 2)
    self.assertAlmostEqual(summary["end_to_end_success_rate"], 0.5)
    # Three runs triggered recovery; only record 3 ultimately succeeded.
    self.assertEqual(summary["recovery"]["triggered_count"], 3)
    self.assertAlmostEqual(summary["recovery"]["triggered_rate"], 0.75)
    self.assertAlmostEqual(summary["recovery"]["success_rate"], round(1 / 3, 6))
    self.assertAlmostEqual(summary["recovery"]["avg_recovery_cost"], round(4 / 3, 6))

  def test_failure_type_distribution_and_branch_coverage(self) -> None:
    records = [
      _record(
        "1",
        success=False,
        recovery_attempts=2,
        failure_type="WRONG_BIN",
        recovery_history=(
          {"failure_type": "GRASP_EMPTY", "strategy": "retry_pick_oriented"},
          {"failure_type": "WRONG_BIN", "strategy": "retry_place_candidates"},
        ),
      ),
      _record("2", success=True, recovery_attempts=0),
    ]
    summary = summarize(records)
    self.assertEqual(
      summary["failure_type_distribution"],
      {"GRASP_EMPTY": 1, "WRONG_BIN": 1},
    )
    self.assertEqual(summary["terminal_failure_distribution"], {"WRONG_BIN": 1})
    self.assertEqual(
      summary["strategy_distribution"],
      {"retry_pick_oriented": 1, "retry_place_candidates": 1},
    )
    self.assertEqual(
      summary["branch_coverage"]["known_failure_types"], len(FailureType)
    )
    self.assertEqual(
      summary["branch_coverage"]["observed_failure_types"],
      ["GRASP_EMPTY", "WRONG_BIN"],
    )
    self.assertAlmostEqual(
      summary["branch_coverage"]["rate"], round(2 / len(FailureType), 6)
    )

  def test_recovery_gain_only_when_baseline_below_one(self) -> None:
    records = [_record("1", success=True), _record("2", success=False)]
    # success_rate = 0.5, baseline 0.25 -> (0.5 - 0.25) / (1 - 0.25)
    summary = summarize(records, baseline_success_rate=0.25)
    self.assertAlmostEqual(
      summary["recovery"]["recovery_gain"], round((0.5 - 0.25) / 0.75, 6)
    )
    self.assertEqual(summary["recovery"]["baseline_success_rate"], 0.25)
    # No baseline -> not reported; baseline == 1 -> guarded against div-by-zero.
    self.assertIsNone(summarize(records)["recovery"]["recovery_gain"])
    self.assertIsNone(
      summarize(records, baseline_success_rate=1.0)["recovery"]["recovery_gain"]
    )

  def test_planner_metrics(self) -> None:
    records = [
      _record("1", success=True, target="industrial.recovery_pick_place_tree"),
      _record("2", success=False, target=None),
      _record(
        "3",
        success=False,
        target="industrial.recovery_pick_place_tree",
        error="missing required input",
      ),
    ]
    summary = summarize(records)
    # Two of three produced a plan target.
    self.assertAlmostEqual(summary["planner"]["parse_accuracy"], round(2 / 3, 6))
    # The schema-error run is excluded from sequence validity -> one of three.
    self.assertAlmostEqual(summary["planner"]["sequence_validity"], round(1 / 3, 6))


class ExtractRunRecordTest(unittest.TestCase):
  def test_from_serialized_decision_tree_result(self) -> None:
    payload = {
      "decision_tree": "industrial.recovery_pick_place_tree",
      "success": False,
      "error": None,
      "nodes": [{"node": "detect"}, {"node": "classify_failure"}],
      "output": {
        "recovery_attempts": 1,
        "classification": {"failure_type": "GRASP_EMPTY"},
        "recovery_history": [
          {
            "attempt": 1,
            "failure_type": "GRASP_EMPTY",
            "strategy": "retry_pick_oriented",
          }
        ],
      },
    }
    record = extract_run_record(payload, run_id="r1")
    self.assertFalse(record.success)
    self.assertEqual(record.recovery_attempts, 1)
    self.assertEqual(record.failure_type, "GRASP_EMPTY")
    self.assertEqual(len(record.recovery_history), 1)
    self.assertEqual(record.node_names, ["detect", "classify_failure"])
    self.assertEqual(record.source, "dict")

  def test_from_result_object(self) -> None:
    obj = SimpleNamespace(
      success=True,
      error=None,
      nodes=[SimpleNamespace(node="detect"), SimpleNamespace(node="success")],
      output={"recovery_attempts": 0},
    )
    record = extract_run_record(obj, run_id="r9")
    self.assertTrue(record.success)
    self.assertEqual(record.recovery_attempts, 0)
    self.assertEqual(record.node_names, ["detect", "success"])
    self.assertEqual(record.source, "SimpleNamespace")

  def test_task_state_is_authoritative_for_success_and_plan(self) -> None:
    class FakePlan:
      def to_dict(self) -> dict:
        return {
          "target": "industrial.pick_place_actionlist",
          "target_kind": "ACTIONLIST",
          "intent": {"object": "roller"},
        }

    class FakeTaskState:
      task_id = "task_123"
      plan = FakePlan()
      status = "SUCCEEDED"
      input = {"object_query": "roller"}

    context = {"recovery_attempts": 0}
    record = extract_run_record(context, task_state=FakeTaskState(), run_id="r1")
    self.assertTrue(record.success)
    self.assertEqual(record.final_status, "SUCCEEDED")
    self.assertEqual(record.task_id, "task_123")
    self.assertEqual(
      record.selected_plan["target"], "industrial.pick_place_actionlist"
    )
    self.assertEqual(record.parsed_intent, {"object": "roller"})
    self.assertEqual(record.source, "task_state")


class AcceptanceTest(unittest.TestCase):
  def test_passes_when_within_thresholds(self) -> None:
    summary = summarize([_record("1", success=True), _record("2", success=False)])
    thresholds = CompetitionThresholds(min_success_rate=0.4, min_branch_coverage=0.0)
    self.assertEqual(check_acceptance(summary, thresholds), ())

  def test_fails_below_success_threshold(self) -> None:
    summary = summarize([_record("1", success=False), _record("2", success=False)])
    failures = check_acceptance(
      summary, CompetitionThresholds(min_success_rate=0.5)
    )
    self.assertEqual(len(failures), 1)
    self.assertIn("end_to_end_success_rate", failures[0])

  def test_recovery_thresholds_skipped_when_no_recovery(self) -> None:
    summary = summarize([_record("1", success=True), _record("2", success=True)])
    failures = check_acceptance(
      summary,
      CompetitionThresholds(min_recovery_success_rate=0.9, max_avg_recovery_cost=0.1),
    )
    # No recovery triggered -> recovery gates are skipped.
    self.assertEqual(failures, ())


class EvaluateRunsTest(unittest.TestCase):
  def setUp(self) -> None:
    self.tmp = tempfile.TemporaryDirectory()
    self.output_dir = Path(self.tmp.name)

  def tearDown(self) -> None:
    self.tmp.cleanup()

  def test_writes_results_jsonl_and_summary_json(self) -> None:
    records = [
      _record("1", success=True),
      _record("2", success=False, recovery_attempts=1, failure_type="GRASP_EMPTY"),
    ]
    run = evaluate_runs(
      records, output_dir=self.output_dir, baseline_success_rate=0.25
    )
    self.assertIsInstance(run, CompetitionEvaluationRun)
    self.assertEqual(len(run.rows), 2)
    self.assertTrue(run.passed)

    lines = (self.output_dir / "results.jsonl").read_text(encoding="utf-8").strip().split("\n")
    self.assertEqual(len(lines), 2)
    self.assertEqual(json.loads(lines[0])["run_id"], "1")

    summary = json.loads((self.output_dir / "summary.json").read_text(encoding="utf-8"))
    self.assertEqual(summary["run_count"], 2)
    self.assertAlmostEqual(summary["end_to_end_success_rate"], 0.5)
    self.assertAlmostEqual(
      summary["recovery"]["recovery_gain"], round((0.5 - 0.25) / 0.75, 6)
    )

  def test_evaluator_normalizes_payloads_and_pairs(self) -> None:
    payload = {"success": True, "output": {"recovery_attempts": 0}, "nodes": []}
    pair = (
      {
        "success": False,
        "output": {
          "recovery_attempts": 1,
          "classification": {"failure_type": "GRASP_EMPTY"},
        },
      },
      None,
    )
    run = evaluate_runs([payload, pair], output_dir=self.output_dir)
    self.assertEqual(len(run.rows), 2)
    self.assertEqual(run.rows[0]["run_id"], "run_0")
    self.assertTrue(run.rows[0]["success"])
    self.assertFalse(run.rows[1]["success"])


if __name__ == "__main__":
  unittest.main()
