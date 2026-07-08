"""Workflow selector interfaces."""

from __future__ import annotations

from typing import Protocol

from sensoragent.schemas import AgentPlan


class WorkflowSelector(Protocol):
  """Select or validate a plan before execution."""

  def select(self, plan: AgentPlan) -> AgentPlan:
    """Return the plan that should be executed."""


class IdentityWorkflowSelector:
  """Selector that accepts the planner output unchanged."""

  def select(self, plan: AgentPlan) -> AgentPlan:
    return plan
