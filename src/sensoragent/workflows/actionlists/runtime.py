"""Sequential ActionList runtime."""

from __future__ import annotations

import re
from typing import Any

from sensoragent.logger import TaskLogger
from sensoragent.schemas import (
  ActionList,
  ActionListResult,
  ActionStep,
  ActionStepKind,
  ActionStepResult,
  TraceContext,
)
from sensoragent.skills import SkillRuntime
from sensoragent.tools import ToolRuntime
from sensoragent.workflows.errors import WorkflowExecutionError, WorkflowTemplateError


_TEMPLATE_PATTERN = re.compile(r"^\{\{\s*([a-zA-Z_][a-zA-Z0-9_\.]*)\s*\}\}$")


def _resolve_path(context: dict[str, Any], path: str) -> Any:
  value: Any = context
  for part in path.split("."):
    if not isinstance(value, dict) or part not in value:
      raise WorkflowTemplateError(f"Unknown workflow variable: {path}")
    value = value[part]
  return value


def _render_value(value: Any, context: dict[str, Any]) -> Any:
  if isinstance(value, str):
    match = _TEMPLATE_PATTERN.match(value)
    if match:
      return _resolve_path(context, match.group(1))
    return value
  if isinstance(value, list):
    return [_render_value(item, context) for item in value]
  if isinstance(value, dict):
    return {key: _render_value(item, context) for key, item in value.items()}
  return value


class ActionListRuntime:
  """Executes ActionList steps sequentially."""

  def __init__(
    self,
    tool_runtime: ToolRuntime,
    skill_runtime: SkillRuntime,
    logger: TaskLogger,
  ) -> None:
    self._tool_runtime = tool_runtime
    self._skill_runtime = skill_runtime
    self._logger = logger

  def _invoke_step(
    self,
    step: ActionStep,
    rendered_input: dict,
    trace: TraceContext,
  ):
    if step.kind == ActionStepKind.TOOL:
      return self._tool_runtime.invoke(step.target, rendered_input, trace)
    if step.kind == ActionStepKind.SKILL:
      return self._skill_runtime.invoke(step.target, rendered_input, trace)
    raise WorkflowExecutionError(f"Unsupported action step kind: {step.kind}")

  def run(
    self,
    actionlist: ActionList,
    input_data: dict,
    trace: TraceContext,
  ) -> ActionListResult:
    """Run an ActionList from first step to last step."""

    context: dict[str, Any] = dict(input_data)
    step_results: list[ActionStepResult] = []
    self._logger.log(
      "actionlist_started",
      trace,
      {"actionlist": actionlist.name, "input": input_data},
    )

    for step in actionlist.steps:
      self._logger.log(
        "action_step_started",
        trace,
        {"actionlist": actionlist.name, "step": step.name, "target": step.target},
      )
      try:
        rendered_input = _render_value(step.input, context)
        if not isinstance(rendered_input, dict):
          raise WorkflowTemplateError(f"Step input must render to object: {step.name}")
        result = self._invoke_step(step, rendered_input, trace)
        step_result = ActionStepResult(
          step=step.name,
          success=result.success,
          output=result.output,
          error=result.error,
        )
      except Exception as exc:
        step_result = ActionStepResult(step=step.name, success=False, error=str(exc))

      step_results.append(step_result)
      if step.save_as and step_result.success:
        context[step.save_as] = step_result.output

      self._logger.log(
        "action_step_finished",
        trace,
        {
          "actionlist": actionlist.name,
          "step": step.name,
          "success": step_result.success,
          "output": step_result.output,
          "error": step_result.error,
        },
      )

      if not step_result.success and step.stop_on_failure:
        result = ActionListResult(
          actionlist=actionlist.name,
          success=False,
          steps=step_results,
          output=context,
          error=step_result.error,
        )
        self._logger.log(
          "actionlist_finished",
          trace,
          {
            "actionlist": actionlist.name,
            "success": result.success,
            "error": result.error,
          },
        )
        return result

    result = ActionListResult(
      actionlist=actionlist.name,
      success=all(step.success for step in step_results),
      steps=step_results,
      output=context,
      error=None,
    )
    self._logger.log(
      "actionlist_finished",
      trace,
      {"actionlist": actionlist.name, "success": result.success, "error": result.error},
    )
    return result
