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
from sensoragent.schemas.core import utc_now_iso
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


def _deep_merge(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
  """Merge nested dicts without mutating either input."""

  merged = dict(left)
  for key, value in right.items():
    existing = merged.get(key)
    if isinstance(existing, dict) and isinstance(value, dict):
      merged[key] = _deep_merge(existing, value)
    else:
      merged[key] = value
  return merged


def _ensure_world_state(context: dict[str, Any]) -> dict[str, Any]:
  """Return the run-local world state dict, creating missing sections."""

  world = context.get("world_state")
  if not isinstance(world, dict):
    world = {}
    context["world_state"] = world
  objects = world.get("objects")
  if not isinstance(objects, dict):
    world["objects"] = {}
  bins = world.get("bins")
  if not isinstance(bins, dict):
    world["bins"] = {}
  current_task = world.get("current_task")
  if not isinstance(current_task, dict):
    world["current_task"] = {}
  history = world.get("history")
  if not isinstance(history, list):
    world["history"] = []
  return world


def _world_record(context: dict[str, Any], event: str, **payload: Any) -> None:
  world = _ensure_world_state(context)
  world["history"].append({"event": event, "timestamp": utc_now_iso(), **payload})


def _numeric_position(value: Any) -> list[float] | None:
  if isinstance(value, dict):
    for key in ("pose_3d", "position_base", "position", "object_position"):
      position = _numeric_position(value.get(key))
      if position is not None:
        return position
    return None
  if not isinstance(value, list) or len(value) < 3:
    return None
  if not all(isinstance(item, (int, float)) and not isinstance(item, bool) for item in value[:3]):
    return None
  return [float(item) for item in value[:3]]


def _active_object_id(context: dict[str, Any], output: dict[str, Any] | None = None) -> str | None:
  output = output or {}
  for candidate in (
    output.get("object_id"),
    output.get("instance_id"),
    context.get("active_object_id"),
    (context.get("object") or {}).get("object_id") if isinstance(context.get("object"), dict) else None,
    context.get("object_query"),
  ):
    if isinstance(candidate, str) and candidate:
      return candidate
  return None


def _observe_object(
  context: dict[str, Any],
  output: dict[str, Any],
  *,
  node_name: str,
) -> None:
  if output.get("found") is False:
    return
  object_id = _active_object_id(context, output)
  if object_id is None:
    return
  position = _numeric_position(output)
  world = _ensure_world_state(context)
  existing = world["objects"].get(object_id)
  target = (existing or {}).get("target") or context.get("target")
  status = (existing or {}).get("status", "observed")
  if status not in {"held", "placed"}:
    status = "observed"
  world["objects"][object_id] = {
    **(existing or {}),
    "object_id": object_id,
    "label": output.get("label", (existing or {}).get("label", object_id)),
    "pose_3d": position,
    "confidence": output.get("confidence", (existing or {}).get("confidence")),
    "source": output.get("source", (existing or {}).get("source", "unknown")),
    "status": status,
    "target": target,
    "updated_at": utc_now_iso(),
  }
  world["current_task"].update(
    {
      "object_id": object_id,
      "target": context.get("target"),
      "step": "observed",
      "last_node": node_name,
    }
  )
  context["active_object_id"] = object_id
  _world_record(
    context,
    "object_observed",
    node=node_name,
    object_id=object_id,
    position=position,
    confidence=output.get("confidence"),
    source=output.get("source", "unknown"),
  )


def _mark_object_status(
  context: dict[str, Any],
  status: str,
  *,
  node_name: str,
  output: dict[str, Any] | None = None,
) -> None:
  object_id = _active_object_id(context, output)
  if object_id is None:
    return
  world = _ensure_world_state(context)
  existing = world["objects"].get(object_id, {"object_id": object_id})
  existing.update(
    {
      "status": status,
      "target": existing.get("target") or context.get("target"),
      "updated_at": utc_now_iso(),
    }
  )
  if output:
    existing["last_output"] = output
  world["objects"][object_id] = existing
  world["current_task"].update(
    {
      "object_id": object_id,
      "target": context.get("target"),
      "step": status,
      "last_node": node_name,
    }
  )
  _world_record(context, f"object_{status}", node=node_name, object_id=object_id)


def _update_bin_state(
  context: dict[str, Any],
  output: dict[str, Any],
  *,
  node_name: str,
  success: bool,
) -> None:
  target = output.get("target") or context.get("target")
  if not isinstance(target, str) or not target:
    return
  object_id = _active_object_id(context)
  position = _numeric_position(output)
  world = _ensure_world_state(context)
  existing = world["bins"].get(target, {"target": target})
  if success and bool(output.get("in_target", True)):
    existing.update(
      {
        "status": "occupied",
        "occupied_by": object_id,
        "observed_position": position,
        "updated_at": utc_now_iso(),
      }
    )
    world["bins"][target] = existing
    _mark_object_status(context, "placed", node_name=node_name, output=output)
    _world_record(
      context,
      "object_placed_in_target",
      node=node_name,
      object_id=object_id,
      target=target,
      observed_position=position,
    )
  else:
    existing.update(
      {
        "status": "mismatch",
        "occupied_by": existing.get("occupied_by"),
        "observed_position": position,
        "updated_at": utc_now_iso(),
      }
    )
    world["bins"][target] = existing
    _world_record(
      context,
      "object_not_in_target",
      node=node_name,
      object_id=object_id,
      target=target,
      observed_position=position,
      error=output.get("error"),
    )


def _update_world_state(
  node: DecisionNode,
  result: DecisionNodeResult,
  context: dict[str, Any],
) -> None:
  output = result.output if isinstance(result.output, dict) else {}
  if result.success:
    if node.target in {"vision.config_detect", "vision.open_vocab_detect", "vision.grounded_sam2"}:
      _observe_object(context, output, node_name=node.name)
    elif node.target == "robot.pick":
      _mark_object_status(context, "held", node_name=node.name, output=output)
    elif node.target == "robot.verify_grasp" and output.get("held") is True:
      _mark_object_status(context, "held", node_name=node.name, output=output)
    elif node.target == "robot.verify_place" and output.get("released") is True:
      _mark_object_status(context, "released", node_name=node.name, output=output)
    elif node.target == "vision.verify_object_in_bin":
      _update_bin_state(context, output, node_name=node.name, success=True)
    elif node.target == "recovery.classify_failure":
      _world_record(
        context,
        "failure_classified",
        node=node.name,
        failure_type=output.get("failure_type"),
        strategy=output.get("recommended_strategy"),
      )
    elif node.target == "recovery.plan":
      _world_record(
        context,
        "recovery_planned",
        node=node.name,
        strategy=output.get("strategy"),
        node_overrides=output.get("node_overrides") or {},
      )
  elif node.kind != DecisionNodeKind.TERMINAL:
    if node.target == "vision.verify_object_in_bin":
      _update_bin_state(context, output, node_name=node.name, success=False)
    _world_record(
      context,
      "node_failed",
      node=node.name,
      target=node.target,
      error=result.error,
      output=output,
    )


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

  def _render_invokable_input(
    self,
    node: DecisionNode,
    context: dict[str, Any],
  ) -> dict:
    rendered_input = _render_value(node.input, context)
    if not isinstance(rendered_input, dict):
      raise WorkflowExecutionError(f"Node input must render to object: {node.name}")
    overrides = context.get("node_input_overrides")
    if isinstance(overrides, dict):
      for key in (node.target, node.name):
        override = overrides.get(key or "")
        if isinstance(override, dict):
          rendered_input = _deep_merge(rendered_input, override)
    # Optional inputs use None defaults so templates resolve without sending
    # null into tool contracts that require a concrete typed value.
    return {key: value for key, value in rendered_input.items() if value is not None}

  def _run_invokable_node(
    self,
    node: DecisionNode,
    rendered_input: dict,
    trace: TraceContext,
  ) -> DecisionNodeResult:
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
        # Mirror the counter into the context so result.output records how many
        # recoveries actually ran; the exceeded limit is reported in the error.
        # Set after the budget check so a short-circuit leaves the count at the
        # recoveries that ran rather than the one that was refused.
        context["recovery_attempts"] = recovery_attempts

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
          rendered_input = self._render_invokable_input(node, context)
          result = self._run_invokable_node(node, rendered_input, trace)
        except Exception as exc:
          result = DecisionNodeResult(node=node.name, success=False, error=str(exc))

      results.append(result)
      if node.save_as and result.success:
        context[node.save_as] = result.output
      # Accumulate per-attempt recovery evidence for offline metrics.
      # classify_failure opens a new attempt record; plan_recovery backfills
      # the chosen strategy on the most recent attempt. recovery_attempts and
      # last_failure are left untouched so existing observers keep working.
      if result.success and node.target == "recovery.classify_failure":
        classification = context.get("classification") or {}
        context.setdefault("recovery_history", []).append(
          {
            "attempt": recovery_attempts,
            "failure_type": classification.get("failure_type"),
            "phase": classification.get("phase"),
            "retryable": classification.get("retryable"),
            "confidence": classification.get("confidence"),
            "reason": classification.get("reason"),
            "strategy": None,
            "next_step": None,
            "node": node.name,
          }
        )
      elif result.success and node.target == "recovery.plan":
        recovery_plan = context.get("recovery") or {}
        history = context.get("recovery_history")
        if history:
          history[-1]["strategy"] = recovery_plan.get("strategy")
          history[-1]["next_step"] = recovery_plan.get("next_step")
          history[-1]["node_overrides"] = recovery_plan.get("node_overrides") or {}
        node_overrides = recovery_plan.get("node_overrides")
        if isinstance(node_overrides, dict) and node_overrides:
          current_overrides = context.get("node_input_overrides")
          if not isinstance(current_overrides, dict):
            current_overrides = {}
          context["node_input_overrides"] = _deep_merge(current_overrides, node_overrides)
          context.setdefault("recovery_applied_overrides", []).append(
            {
              "attempt": recovery_attempts,
              "strategy": recovery_plan.get("strategy"),
              "node_overrides": node_overrides,
            }
          )
      _update_world_state(node, result, context)
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
