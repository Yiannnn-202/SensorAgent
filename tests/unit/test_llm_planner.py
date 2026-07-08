"""Unit tests for LLMPlanner."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest import TestCase

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
  sys.path.insert(0, str(SRC))

from sensoragent.agent import LLMPlanner
from sensoragent.schemas import PlanTargetKind


class FakeJsonClient:
  def __init__(self, payload: dict) -> None:
    self.payload = payload
    self.calls: list[tuple[str, str]] = []

  def complete_json(self, system_prompt: str, user_prompt: str) -> dict:
    self.calls.append((system_prompt, user_prompt))
    return self.payload


class LLMPlannerTest(TestCase):
  def test_llm_planner_returns_agent_plan(self) -> None:
    client = FakeJsonClient(
      {
        "target_kind": "actionlist",
        "target": "mock.pick_place_actionlist",
        "input": {
          "object_query": "silver roller",
          "target": "third bin cell",
        },
        "reason": "The task matches pick-and-place.",
      }
    )
    planner = LLMPlanner(client)

    plan = planner.plan("put the roller into the third cell", {})

    self.assertEqual(plan.target_kind, PlanTargetKind.ACTIONLIST)
    self.assertEqual(plan.target, "mock.pick_place_actionlist")
    self.assertEqual(plan.input["object_query"], "silver roller")
    self.assertEqual(plan.reason, "The task matches pick-and-place.")
    self.assertEqual(len(client.calls), 1)

  def test_llm_planner_rejects_unknown_target(self) -> None:
    planner = LLMPlanner(
      FakeJsonClient(
        {
          "target_kind": "actionlist",
          "target": "dangerous.workflow",
          "input": {},
        }
      )
    )

    with self.assertRaises(ValueError):
      planner.plan("do something unsafe", {})
