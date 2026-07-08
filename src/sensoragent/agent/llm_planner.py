"""LLM-backed planner implementation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol

from sensoragent.schemas import AgentPlan, PlanTargetKind


class JsonPlanningClient(Protocol):
  """Client interface required by LLMPlanner."""

  def complete_json(self, system_prompt: str, user_prompt: str) -> dict:
    """Return a JSON object from an LLM call."""


class LLMPlanner:
  """Planner that asks an LLM to produce an AgentPlan JSON object."""

  def __init__(
    self,
    client: JsonPlanningClient,
    prompt_path: Path | None = None,
    allowed_targets: tuple[str, ...] = ("mock.pick_place_actionlist",),
  ) -> None:
    self._client = client
    self._prompt_path = prompt_path or (
      Path(__file__).parent / "prompts" / "intent_to_workflow.md"
    )
    self._allowed_targets = allowed_targets

  def plan(self, user_input: str, input_data: dict) -> AgentPlan:
    system_prompt = self._prompt_path.read_text(encoding="utf-8")
    user_prompt = json.dumps(
      {
        "user_input": user_input,
        "initial_input": input_data,
        "allowed_targets": list(self._allowed_targets),
      },
      ensure_ascii=False,
      indent=2,
    )
    raw_plan = self._client.complete_json(system_prompt, user_prompt)
    target = str(raw_plan.get("target", ""))
    if target not in self._allowed_targets:
      raise ValueError(f"LLM selected unsupported target: {target}")
    target_kind = PlanTargetKind(str(raw_plan.get("target_kind", "")))
    plan_input = raw_plan.get("input", {})
    if not isinstance(plan_input, dict):
      raise ValueError("LLM plan input must be an object")
    return AgentPlan(
      target_kind=target_kind,
      target=target,
      input=plan_input,
      reason=str(raw_plan.get("reason", "")),
    )
