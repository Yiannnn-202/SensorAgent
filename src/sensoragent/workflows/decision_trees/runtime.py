"""DecisionTree runtime."""

from __future__ import annotations

from typing import Any

from sensoragent.logger import TaskLogger
from sensoragent.schemas import (
  ConditionOperator,
  DecisionCondition,
  DecisionNode,
  DecisionNodeKind,
  DecisionNodeResult,
  DecisionTree,
  DecisionTreeResult,
  TraceContext,
)
from sensoragent.skills import SkillRuntime
from sensoragent.tools import ToolRuntime
from sensoragent.workflows.actionlists.runtime import ActionListRuntime
from sensoragent.workflows.actionlists.runtime import _render_value, _resolve_path
from sensoragent.workflows.errors import WorkflowExecutionError


_DEFAULT_MAX_RECOVERY_ATTEMPTS = 2


def _recovery_attempt_limit(context: dict[str, Any]) -> int:
  """Resolve the global recovery-attempt budget from the tree context."""

  value = context.get("max_recovery_attempts")
  if isinstance(value, int) and not isinstance(value, bool) and value > 0:
    return value
  return _DEFAULT_MAX_RECOVERY_ATTEMPTS


class DecisionTreeRuntime:
  """Executes DecisionTree nodes until a terminal result is reached."""

  def __init__(
    self,
    tool_runtime: ToolRuntime,
    skill_runtime: SkillRuntime,
    actionlist_runtime: ActionListRuntime,
    actionlists: dict[str, object],
    logger: TaskLogger,
  ) -> None:
    self._tool_runtime = tool_runtime
    self._skill_runtime = skill_runtime
    self._actionlist_runtime = actionlist_runtime
    self._actionlists = actionlists
    self._logger = logger

  def _evaluate_condition(self, condition: DecisionCondition, context: dict[str, Any]) -> bool:
    try:
      value = _resolve_path(context, condition.path)
    except Exception:
      if condition.operator == ConditionOperator.EXISTS:
        return False
      raise

    if condition.operator == ConditionOperator.EXISTS:
      return True
    if condition.operator == ConditionOperator.EQUALS:
      return value == condition.value
    if condition.operator == ConditionOperator.TRUTHY:
      return bool(value)
    raise WorkflowExecutionError(f"Unsupported condition operator: {condition.operator}")

  def _invoke_node(self, node: DecisionNode, rendered_input: dict, trace: TraceContext):
    if node.kind == DecisionNodeKind.TOOL:
      return self._tool_runtime.invoke(node.target or "", rendered_input, trace)
    if node.kind == DecisionNodeKind.SKILL:
      return self._skill_runtime.invoke(node.target or "", rendered_input, trace)
    if node.kind == DecisionNodeKind.ACTIONLIST:
      actionlist = self._actionlists.get(node.target or "")
      if actionlist is None:
        raise WorkflowExecutionError(f"Unknown actionlist: {node.target}")
      return self._actionlist_runtime.run(actionlist, rendered_input, trace)
    raise WorkflowExecutionError(f"Node kind is not invokable: {node.kind}")

  def _run_invokable_node(
    self,
    node: DecisionNode,
    context: dict[str, Any],
    trace: TraceContext,
  ) -> DecisionNodeResult:
    rendered_input = _render_value(node.input, context)
    if not isinstance(rendered_input, dict):
      raise WorkflowExecutionError(f"Node input must render to object: {node.name}")
    # Optional inputs use None defaults so templates resolve without sending
    # null into tool contracts that require a concrete typed value.
    rendered_input = {key: value for key, value in rendered_input.items() if value is not None}

    last_result = None
    attempts = max(0, node.max_retries) + 1
    for attempt in range(1, attempts + 1):
      last_result = self._invoke_node(node, rendered_input, trace)
      if last_result.success:
        return DecisionNodeResult(
          node=node.name,
          success=True,
          attempts=attempt,
          output=last_result.output,
          error=None,
        )
      self._logger.log(
        "decision_node_attempt_failed",
        trace,
        {
          "node": node.name,
          "attempt": attempt,
          "max_retries": node.max_retries,
          "error": last_result.error,
        },
      )

    return DecisionNodeResult(
      node=node.name,
      success=False,
      attempts=attempts,
      output=last_result.output if last_result else None,
      error=last_result.error if last_result else "Node execution failed",
    )

  def run(self, tree: DecisionTree, input_data: dict, trace: TraceContext) -> DecisionTreeResult:
    """Run a DecisionTree from its start node."""

    max_nodes = int(input_data.get("max_decision_nodes", 100))
    nodes = {node.name: node for node in tree.nodes}
    if tree.start not in nodes:
      return DecisionTreeResult(
        decision_tree=tree.name,
        success=False,
        nodes=[],
        output=dict(input_data),
        error=f"Unknown start node: {tree.start}",
      )

    context: dict[str, Any] = {**tree.input_defaults, **input_data}
    max_recovery_attempts = _recovery_attempt_limit(context)
    recovery_attempts = 0
    results: list[DecisionNodeResult] = []
    current_name: str | None = tree.start
    self._logger.log("decision_tree_started", trace, {"decision_tree": tree.name})

    while current_name is not None:
      if len(results) >= max_nodes:
        final = DecisionTreeResult(
          tree.name,
          False,
          results,
          context,
          f"DecisionTree exceeded max_decision_nodes={max_nodes}",
        )
        self._logger.log(
          "decision_tree_finished",
          trace,
          {"decision_tree": tree.name, "success": False, "error": final.error},
        )
        return final
      node = nodes.get(current_name)
      if node is None:
        final = DecisionTreeResult(
          decision_tree=tree.name,
          success=False,
          nodes=results,
          output=context,
          error=f"Unknown decision node: {current_name}",
        )
        self._logger.log(
          "decision_tree_finished",
          trace,
          {"decision_tree": tree.name, "success": False, "error": final.error},
        )
        return final

      # Global recovery budget: each entry into recovery.classify_failure counts
      # as one recovery attempt; short-circuit to failure once the configured
      # limit is exceeded, complementing the max_decision_nodes hard cap.
      if (
        node.kind == DecisionNodeKind.TOOL
        and node.target == "recovery.classify_failure"
      ):
        recovery_attempts += 1
        if recovery_attempts > max_recovery_attempts:
          final = DecisionTreeResult(
            tree.name,
            False,
            results,
            context,
            f"DecisionTree exceeded max_recovery_attempts={max_recovery_attempts}",
          )
          self._logger.log(
            "decision_tree_finished",
            trace,
            {"decision_tree": tree.name, "success": False, "error": final.error},
          )
          return final

      self._logger.log(
        "decision_node_started",
        trace,
        {"decision_tree": tree.name, "node": node.name, "kind": node.kind},
      )

      rendered_input = {}
      if node.kind == DecisionNodeKind.TERMINAL:
        success = bool(node.terminal_success)
        result = DecisionNodeResult(node=node.name, success=success, output=context)
      elif node.kind == DecisionNodeKind.CONDITION:
        if node.condition is None:
          result = DecisionNodeResult(
            node=node.name,
            success=False,
            error="Condition node missing condition",
          )
        else:
          success = self._evaluate_condition(node.condition, context)
          result = DecisionNodeResult(
            node=node.name,
            success=success,
            output={"condition": success},
          )
      else:
        try:
          result = self._run_invokable_node(node, context, trace)
        except Exception as exc:
          result = DecisionNodeResult(node=node.name, success=False, error=str(exc))

      results.append(result)
      if node.save_as and result.success:
        context[node.save_as] = result.output
      if not result.success and node.kind != DecisionNodeKind.TERMINAL:
        context["last_failure"] = {
          "node": node.name,
          "failed_step": node.name,
          "target": node.target,
          "kind": node.kind.value,
          "input": rendered_input if node.kind != DecisionNodeKind.CONDITION else node.input,
          "output": result.output,
          "error": result.error,
          "attempts": result.attempts,
        }

      self._logger.log(
        "decision_node_finished",
        trace,
        {
          "decision_tree": tree.name,
          "node": node.name,
          "success": result.success,
          "attempts": result.attempts,
          "error": result.error,
        },
      )

      if node.kind == DecisionNodeKind.TERMINAL:
        final = DecisionTreeResult(
          tree.name,
          result.success,
          results,
          context,
          result.error,
        )
        self._logger.log(
          "decision_tree_finished",
          trace,
          {"decision_tree": tree.name, "success": final.success, "error": final.error},
        )
        return final

      current_name = node.on_success if result.success else node.on_failure
      if current_name is None:
        final = DecisionTreeResult(
          tree.name,
          result.success,
          results,
          context,
          result.error,
        )
        self._logger.log(
          "decision_tree_finished",
          trace,
          {"decision_tree": tree.name, "success": final.success, "error": final.error},
        )
        return final

    final = DecisionTreeResult(tree.name, True, results, context, None)
    self._logger.log(
      "decision_tree_finished",
      trace,
      {"decision_tree": tree.name, "success": True, "error": None},
    )
    return final
