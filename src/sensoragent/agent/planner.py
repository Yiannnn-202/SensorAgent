"""Planner interfaces for turning user input into executable plans."""

from __future__ import annotations

from typing import Protocol

from sensoragent.schemas import AgentPlan, PlanTargetKind


class Planner(Protocol):
  """Planner interface used by AgentRuntime."""

  def plan(self, user_input: str, input_data: dict) -> AgentPlan:
    """Create a structured plan for a user task."""


class StaticPlanner:
  """Deterministic planner used before the LLM planner exists."""

  def __init__(
    self,
    target: str = "industrial.sorting_config_pick_place_actionlist",
    target_kind: PlanTargetKind = PlanTargetKind.ACTIONLIST,
  ) -> None:
    self._target = target
    self._target_kind = target_kind

  def plan(self, user_input: str, input_data: dict) -> AgentPlan:
    return AgentPlan(
      target_kind=self._target_kind,
      target=self._target,
      input=dict(input_data),
      reason="Static planner selected the configured default target.",
    )
