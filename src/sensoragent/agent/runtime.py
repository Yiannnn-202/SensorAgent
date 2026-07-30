"""Agent runtime for dispatching skills and workflows."""

from __future__ import annotations

from sensoragent.logger import TaskLogger
from sensoragent.schemas import (
  ActionList,
  AgentRequest,
  AgentResponse,
  PlanTargetKind,
  TraceContext,
)
from sensoragent.agent.planner import Planner, StaticPlanner
from sensoragent.agent.selector import IdentityWorkflowSelector, WorkflowSelector
from sensoragent.skills import SkillRuntime
from sensoragent.state import InMemoryEventStream, InMemoryTaskStore, TaskState, TaskStatus
from sensoragent.schemas import AgentPlan
from sensoragent.workflows import ActionListRuntime
from sensoragent.workflows.decision_trees import DecisionTreeRuntime


def _validate_required_workflow_inputs(plan: AgentPlan, merged_input: dict) -> str | None:
  """Return a validation error when a selected workflow is missing critical input."""

  requirements = {
    "industrial.pick_place_actionlist": ("object_query", "target"),
    "industrial.vision_pick_place_actionlist": ("object_query", "target"),
    "industrial.recovery_pick_place_tree": ("object_query", "target"),
    "industrial.pick_only_actionlist": ("object_query",),
    "industrial.place_only_actionlist": ("target",),
    "mock.pick_place_actionlist": ("object_query", "target"),
  }
  missing = [
    key
    for key in requirements.get(plan.target, ())
    if not str(merged_input.get(key, "")).strip()
  ]
  if not missing:
    return None
  return (
    f"Planner selected {plan.target} but missing required input(s): "
    f"{', '.join(missing)}"
  )


class AgentRuntime:
  """Dispatches Agent requests to skills or ActionList workflows."""

  def __init__(
    self,
    skill_runtime: SkillRuntime,
    logger: TaskLogger,
    actionlist_runtime: ActionListRuntime | None = None,
    actionlists: dict[str, ActionList] | None = None,
    decision_tree_runtime: DecisionTreeRuntime | None = None,
    decision_trees: dict[str, object] | None = None,
    planner: Planner | None = None,
    selector: WorkflowSelector | None = None,
    task_store: InMemoryTaskStore | None = None,
    event_stream: InMemoryEventStream | None = None,
  ) -> None:
    self._skill_runtime = skill_runtime
    self._logger = logger
    self._actionlist_runtime = actionlist_runtime
    self._actionlists = actionlists or {}
    self._decision_tree_runtime = decision_tree_runtime
    self._decision_trees = decision_trees or {}
    self._planner = planner or StaticPlanner()
    self._selector = selector or IdentityWorkflowSelector()
    self._task_store = task_store or InMemoryTaskStore()
    self._event_stream = event_stream or InMemoryEventStream()

  def _handle_skill(self, request: AgentRequest) -> AgentResponse:
    if request.skill is None:
      return AgentResponse(
        success=False,
        result=None,
        error="AgentRequest.skill is required for skill dispatch",
        trace=request.trace,
      )
    result = self._skill_runtime.invoke(request.skill, request.input, request.trace)
    return AgentResponse(
      success=result.success,
      result=result.output,
      error=result.error,
      trace=request.trace,
    )

  def _handle_actionlist(self, request: AgentRequest) -> AgentResponse:
    if request.actionlist is None:
      return AgentResponse(
        success=False,
        result=None,
        error="AgentRequest.actionlist is required for ActionList dispatch",
        trace=request.trace,
      )
    if self._actionlist_runtime is None:
      return AgentResponse(
        success=False,
        result=None,
        error="ActionList runtime is not configured",
        trace=request.trace,
      )
    actionlist = self._actionlists.get(request.actionlist)
    if actionlist is None:
      return AgentResponse(
        success=False,
        result=None,
        error=f"Unknown actionlist: {request.actionlist}",
        trace=request.trace,
      )
    result = self._actionlist_runtime.run(actionlist, request.input, request.trace)
    return AgentResponse(
      success=result.success,
      result=result.output,
      error=result.error,
      trace=request.trace,
    )

  def _handle_decision_tree(self, request: AgentRequest) -> AgentResponse:
    if request.decision_tree is None:
      return AgentResponse(
        success=False,
        result=None,
        error="AgentRequest.decision_tree is required for DecisionTree dispatch",
        trace=request.trace,
      )
    if self._decision_tree_runtime is None:
      return AgentResponse(
        success=False,
        result=None,
        error="DecisionTree runtime is not configured",
        trace=request.trace,
      )
    decision_tree = self._decision_trees.get(request.decision_tree)
    if decision_tree is None:
      return AgentResponse(
        success=False,
        result=None,
        error=f"Unknown decision tree: {request.decision_tree}",
        trace=request.trace,
      )
    result = self._decision_tree_runtime.run(decision_tree, request.input, request.trace)
    return AgentResponse(
      success=result.success,
      result=result.output,
      error=result.error,
      trace=request.trace,
    )

  def handle(self, request: AgentRequest) -> AgentResponse:
    self._logger.log(
      "agent_request_started",
      request.trace,
      {
        "skill": request.skill,
        "actionlist": request.actionlist,
        "decision_tree": request.decision_tree,
        "input": request.input,
      },
    )

    target_count = sum(
      target is not None
      for target in (request.skill, request.actionlist, request.decision_tree)
    )
    if target_count > 1:
      response = AgentResponse(
        success=False,
        result=None,
        error="AgentRequest cannot specify more than one execution target",
        trace=request.trace,
      )
    elif request.decision_tree:
      response = self._handle_decision_tree(request)
    elif request.actionlist:
      response = self._handle_actionlist(request)
    else:
      response = self._handle_skill(request)

    self._logger.log(
      "agent_request_finished",
      request.trace,
      {
        "skill": request.skill,
        "actionlist": request.actionlist,
        "decision_tree": request.decision_tree,
        "success": response.success,
        "result": response.result,
        "error": response.error,
      },
    )
    return response

  @property
  def task_store(self) -> InMemoryTaskStore:
    return self._task_store

  @property
  def event_stream(self) -> InMemoryEventStream:
    return self._event_stream

  def create_task(self, user_input: str, input_data: dict | None = None) -> TaskState:
    trace = TraceContext()
    task = TaskState(
      task_id=trace.task_id,
      user_input=user_input,
      trace=trace,
      input=input_data or {},
    )
    self._task_store.save(task)
    self._event_stream.publish("task_created", trace, {"user_input": user_input})
    return task

  def cancel_task(self, task_id: str) -> TaskState | None:
    task = self._task_store.get(task_id)
    if task is None:
      return None
    if task.status in (TaskStatus.PENDING, TaskStatus.RUNNING):
      task.mark(TaskStatus.CANCELLED)
      self._event_stream.publish("task_cancelled", task.trace, {})
    return task

  def run_task(self, user_input: str, input_data: dict | None = None) -> TaskState:
    task = self.create_task(user_input, input_data)
    task.mark(TaskStatus.RUNNING)
    self._event_stream.publish("task_started", task.trace, {})

    plan = self._selector.select(self._planner.plan(user_input, task.input))
    task.plan = plan
    self._event_stream.publish("task_planned", task.trace, {"plan": plan.to_dict()})

    # Merge caller-provided task inputs with the planner's extracted inputs.
    # Planner output wins on conflict so incomplete ASR/LLM extraction fails
    # explicitly instead of silently executing with fallback object/target data.
    merged_input = {**task.input, **plan.input}
    validation_error = _validate_required_workflow_inputs(plan, merged_input)
    if validation_error is not None:
      task.mark(TaskStatus.FAILED, error=validation_error)
      self._event_stream.publish("task_failed", task.trace, {"error": task.error})
      self._task_store.save(task)
      return task
    if plan.target_kind == PlanTargetKind.SKILL:
      request = AgentRequest(skill=plan.target, input=merged_input, trace=task.trace)
    elif plan.target_kind == PlanTargetKind.ACTIONLIST:
      request = AgentRequest(actionlist=plan.target, input=merged_input, trace=task.trace)
    else:
      request = AgentRequest(decision_tree=plan.target, input=merged_input, trace=task.trace)

    response = self.handle(request)
    task.result = response.result
    if response.success:
      task.mark(TaskStatus.SUCCEEDED)
      self._event_stream.publish("task_succeeded", task.trace, {"result": task.result})
    else:
      task.mark(TaskStatus.FAILED, error=response.error)
      self._event_stream.publish("task_failed", task.trace, {"error": task.error})
    self._task_store.save(task)
    return task
