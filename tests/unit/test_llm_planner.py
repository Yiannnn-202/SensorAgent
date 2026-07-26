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

  def test_llm_planner_reads_top_level_intent(self) -> None:
    client = FakeJsonClient(
      {
        "target_kind": "actionlist",
        "target": "mock.pick_place_actionlist",
        "input": {"object_query": "roller", "target": "bin_cell_3"},
        "intent": {
          "object": "roller",
          "action": "pick_place",
          "target": "bin_cell_3",
        },
        "reason": "Standard pick-and-place.",
      }
    )
    plan = LLMPlanner(client).plan("put roller into bin_cell_3", {})
    self.assertEqual(plan.intent, {
      "object": "roller",
      "action": "pick_place",
      "target": "bin_cell_3",
    })

  def test_llm_planner_extracts_spatial_constraint(self) -> None:
    client = FakeJsonClient(
      {
        "target_kind": "actionlist",
        "target": "mock.pick_place_actionlist",
        "input": {
          "object_query": "扳手",
          "target": "bin_cell_3",
          "spatial_constraint": {"relation": "left", "ordinal": 1},
        },
        "intent": {
          "object": "扳手",
          "action": "pick_place",
          "target": "bin_cell_3",
          "spatial": {"relation": "left", "ordinal": 1},
        },
        "reason": "Left wrench pick-and-place.",
      }
    )
    plan = LLMPlanner(client).plan("把左侧的扳手放到料箱第三格", {})
    self.assertEqual(plan.input["object_query"], "扳手")
    self.assertEqual(
      plan.input["spatial_constraint"], {"relation": "left", "ordinal": 1}
    )
    self.assertEqual(plan.intent["spatial"], {"relation": "left", "ordinal": 1})

  def test_llm_planner_falls_back_to_intent_in_reason(self) -> None:
    """Legacy prompt v2 kept intent inside reason. Fallback path must still parse it."""

    client = FakeJsonClient(
      {
        "target_kind": "actionlist",
        "target": "mock.pick_place_actionlist",
        "input": {"object_query": "滚柱", "target": "bin_cell_3"},
        "reason": (
          "intent={\"object\":\"滚柱\",\"action\":\"pick_place\",\"target\":\"bin_cell_3\"};"
          " place operation."
        ),
      }
    )
    plan = LLMPlanner(client).plan("把滚柱放到 bin_cell_3", {})
    self.assertIsNotNone(plan.intent)
    self.assertEqual(plan.intent["action"], "pick_place")
    self.assertEqual(plan.intent["target"], "bin_cell_3")

  def test_llm_planner_intent_defaults_to_none(self) -> None:
    client = FakeJsonClient(
      {
        "target_kind": "actionlist",
        "target": "mock.pick_place_actionlist",
        "input": {"object_query": "roller", "target": ""},
        "reason": "no intent field, no fallback string",
      }
    )
    plan = LLMPlanner(client).plan("something", {})
    self.assertIsNone(plan.intent)
