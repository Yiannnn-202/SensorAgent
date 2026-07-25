"""Recovery and failure-classification tools."""

from __future__ import annotations

from sensoragent.recovery import FailureDetector, FailureEvidence, RecoveryPlanner
from sensoragent.schemas import ToolCall, ToolResult, ToolSpec


class RecoveryClassifyFailureTool:
  """Classify failed workflow evidence into a typed failure category."""

  spec = ToolSpec(
    name="recovery.classify_failure",
    description="Classify failed SensorAgent workflow evidence into a failure type.",
    tags=("recovery", "failure-detection"),
  )

  def run(self, call: ToolCall) -> ToolResult:
    evidence = call.input.get("evidence", call.input)
    if not isinstance(evidence, dict):
      return ToolResult(
        tool=self.spec.name,
        success=False,
        error="evidence must be an object",
      )
    detector = FailureDetector(
      min_confidence=float(call.input.get("min_confidence", 0.35)),
      min_grasp_opening=float(call.input.get("min_grasp_opening", 0.002)),
      max_grasp_opening=float(call.input.get("max_grasp_opening", 0.08)),
    )
    classification = detector.classify(FailureEvidence.from_dict(evidence))
    return ToolResult(
      tool=self.spec.name,
      success=True,
      output=classification.to_dict(),
    )


class RecoveryPlanTool:
  """Return a deterministic local recovery plan for a classified failure."""

  spec = ToolSpec(
    name="recovery.plan",
    description="Plan a bounded local recovery strategy for a classified failure.",
    tags=("recovery", "replanning"),
  )

  def run(self, call: ToolCall) -> ToolResult:
    classification = call.input.get("classification")
    evidence = call.input.get("evidence")
    context = call.input.get("context", {})
    if not isinstance(context, dict):
      return ToolResult(
        tool=self.spec.name,
        success=False,
        error="context must be an object when provided",
      )
    if isinstance(classification, dict):
      plan = RecoveryPlanner().plan(classification, context)
    elif isinstance(evidence, dict):
      detector = FailureDetector()
      plan = RecoveryPlanner().plan(detector.classify(FailureEvidence.from_dict(evidence)), context)
    else:
      return ToolResult(
        tool=self.spec.name,
        success=False,
        error="classification or evidence must be provided",
      )
    return ToolResult(tool=self.spec.name, success=True, output=plan.to_dict())
