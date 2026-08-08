"""Fixture-driven planner tests across command categories.

Loads parametric cases from ``tests/fixtures/planner/cases.jsonl`` and runs
each through :class:`LLMPlanner` with a :class:`FakeJsonClient`. Categories
cover standard, synonymous, ambiguous (spatial), missing-target, and invalid
commands, as called out by the Phase 8 planner-test plan.

Scope note: the LLM is mocked, so these cases exercise the planner's
parsing/normalization contract (whitelist enforcement, ``target_kind``
validation, intent extraction, spatial mirroring) against representative
payloads — not the LLM's command understanding, which belongs to an
integration/eval suite.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest import TestCase

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
  sys.path.insert(0, str(SRC))

from sensoragent.agent import LLMPlanner
from sensoragent.schemas import PlanTargetKind

FIXTURES = ROOT / "tests" / "fixtures" / "planner" / "cases.jsonl"


class FakeJsonClient:
  def __init__(self, payload: dict) -> None:
    self.payload = payload

  def complete_json(self, system_prompt: str, user_prompt: str) -> dict:
    return self.payload


def _load_cases() -> list[dict]:
  with FIXTURES.open(encoding="utf-8") as handle:
    return [json.loads(line) for line in handle if line.strip()]


class PlannerFixtureTest(TestCase):
  def test_cases_cover_all_categories(self) -> None:
    """Guard: the fixture file must exercise every required category."""

    categories = {case["category"] for case in _load_cases()}
    self.assertSetEqual(
      categories,
      {"standard", "synonymous", "ambiguous", "missing_target", "invalid_object"},
    )

  def test_all_fixture_cases(self) -> None:
    cases = _load_cases()
    self.assertGreater(len(cases), 0, "planner fixture file has no cases")

    for case in cases:
      with self.subTest(category=case["category"], desc=case["description"]):
        planner = LLMPlanner(
          FakeJsonClient(case["llm_payload"]),
          allowed_targets=tuple(case["allowed_targets"]),
          allowed_place_targets=tuple(case.get("allowed_place_targets", ())),
        )

        if case.get("expects_error"):
          with self.assertRaises(ValueError):
            planner.plan(case["user_input"], {})
          continue

        plan = planner.plan(case["user_input"], {})

        if "expected_target_kind" in case:
          self.assertEqual(
            plan.target_kind, PlanTargetKind(case["expected_target_kind"])
          )
        if "expected_target" in case:
          self.assertEqual(plan.target, case["expected_target"])
        for key, value in case.get("expected_input", {}).items():
          self.assertEqual(plan.input.get(key), value, f"input.{key} mismatch")
        if "expected_intent_action" in case:
          self.assertIsNotNone(plan.intent, "expected an intent on the plan")
          self.assertEqual(plan.intent["action"], case["expected_intent_action"])
        if "expected_spatial" in case:
          self.assertIsNotNone(plan.intent, "expected an intent for spatial")
          self.assertEqual(plan.intent["spatial"], case["expected_spatial"])
          self.assertEqual(
            plan.input.get("spatial_constraint"),
            case["expected_spatial"],
            "spatial_constraint must mirror intent.spatial",
          )
