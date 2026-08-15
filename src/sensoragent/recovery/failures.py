"""Typed failure and recovery data structures."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class FailureType(StrEnum):
  """Known failure classes used by recovery logic and reports."""

  UNKNOWN = "UNKNOWN"
  OBJECT_NOT_FOUND = "OBJECT_NOT_FOUND"
  LOW_CONFIDENCE = "LOW_CONFIDENCE"
  POSE_INVALID = "POSE_INVALID"
  TARGET_NOT_FOUND = "TARGET_NOT_FOUND"
  ROBOT_NOT_READY = "ROBOT_NOT_READY"
  BRIDGE_ERROR = "BRIDGE_ERROR"
  PICK_PLAN_FAILED = "PICK_PLAN_FAILED"
  PICK_EXEC_FAILED = "PICK_EXEC_FAILED"
  GRASP_EMPTY = "GRASP_EMPTY"
  DROPPED_OBJECT = "DROPPED_OBJECT"
  PLACE_PLAN_FAILED = "PLACE_PLAN_FAILED"
  PLACE_EXEC_FAILED = "PLACE_EXEC_FAILED"
  RELEASE_FAILED = "RELEASE_FAILED"
  WRONG_BIN = "WRONG_BIN"
  GRIPPER_FAILED = "GRIPPER_FAILED"
  MOTION_FAILED = "MOTION_FAILED"
  VISION_MODEL_NOT_READY = "VISION_MODEL_NOT_READY"
  VISION_BACKEND_UNAVAILABLE = "VISION_BACKEND_UNAVAILABLE"


class RecoveryStrategy(StrEnum):
  """Deterministic recovery strategies selected after classification."""

  FAIL_FAST = "fail_fast"
  RETRY_DETECT = "retry_detect"
  RETRY_WITH_EXPANDED_VISION = "retry_with_expanded_vision"
  RETRY_PICK_ORIENTED = "retry_pick_oriented"
  RETRY_PICK_ADJUSTED_GRASP = "retry_pick_adjusted_grasp"
  RECOVER_TO_STAGING_AND_REPLAN_PICK = "recover_to_staging_and_replan_pick"
  REPICK_FROM_OBSERVED_POSE = "repick_from_observed_pose"
  RETRY_PLACE_CANDIDATES = "retry_place_candidates"
  RECOVER_TO_STAGING_AND_REPLAN_PLACE = "recover_to_staging_and_replan_place"
  RETRY_OPEN_GRIPPER = "retry_open_gripper"
  CHECK_BRIDGE_AND_RESET = "check_bridge_and_reset"


@dataclass(frozen=True)
class FailureEvidence:
  """Normalized evidence used to classify a failed workflow node or verifier."""

  failed_step: str | None = None
  target: str | None = None
  phase: str | None = None
  error: str | None = None
  output: dict[str, Any] | None = None
  observed: dict[str, Any] | None = None
  expected: dict[str, Any] | None = None
  attempt: int = 1
  max_attempts: int = 1

  @classmethod
  def from_dict(cls, value: dict[str, Any]) -> "FailureEvidence":
    """Build evidence from loose workflow/tool payloads."""

    output = value.get("output")
    observed = value.get("observed")
    expected = value.get("expected")
    return cls(
      failed_step=_optional_str(
        value.get("failed_step")
        or value.get("step")
        or value.get("node")
        or value.get("tool")
        or value.get("skill")
      ),
      target=_optional_str(value.get("target")),
      phase=_optional_str(value.get("phase")),
      error=_optional_str(value.get("error")),
      output=output if isinstance(output, dict) else None,
      observed=observed if isinstance(observed, dict) else None,
      expected=expected if isinstance(expected, dict) else None,
      attempt=_positive_int(value.get("attempt") or value.get("attempts"), default=1),
      max_attempts=_positive_int(
        value.get("max_attempts") or value.get("retry_limit") or value.get("max_retries"),
        default=1,
      ),
    )

  def to_dict(self) -> dict[str, Any]:
    return asdict(self)


@dataclass(frozen=True)
class FailureClassification:
  """A classified failure with report-ready recovery metadata."""

  failure_type: FailureType
  phase: str
  retryable: bool
  confidence: float
  reason: str
  evidence: FailureEvidence = field(default_factory=FailureEvidence)
  recommended_strategy: RecoveryStrategy = RecoveryStrategy.FAIL_FAST

  @classmethod
  def from_dict(cls, value: dict[str, Any]) -> "FailureClassification":
    evidence_value = value.get("evidence")
    evidence = (
      FailureEvidence.from_dict(evidence_value)
      if isinstance(evidence_value, dict)
      else FailureEvidence()
    )
    return cls(
      failure_type=FailureType(str(value.get("failure_type", FailureType.UNKNOWN))),
      phase=str(value.get("phase", "unknown")),
      retryable=bool(value.get("retryable", False)),
      confidence=float(value.get("confidence", 0.0)),
      reason=str(value.get("reason", "")),
      evidence=evidence,
      recommended_strategy=RecoveryStrategy(
        str(value.get("recommended_strategy", RecoveryStrategy.FAIL_FAST))
      ),
    )

  def to_dict(self) -> dict[str, Any]:
    value = asdict(self)
    value["failure_type"] = self.failure_type.value
    value["recommended_strategy"] = self.recommended_strategy.value
    return value


@dataclass(frozen=True)
class RecoveryPlan:
  """A deterministic local replanning decision."""

  strategy: RecoveryStrategy
  failure_type: FailureType
  retryable: bool
  next_step: str | None
  max_attempts: int
  updated_input: dict[str, Any] = field(default_factory=dict)
  node_overrides: dict[str, dict[str, Any]] = field(default_factory=dict)
  notes: list[str] = field(default_factory=list)

  def to_dict(self) -> dict[str, Any]:
    value = asdict(self)
    value["strategy"] = self.strategy.value
    value["failure_type"] = self.failure_type.value
    return value


def _optional_str(value: Any) -> str | None:
  if value is None:
    return None
  return str(value)


def _positive_int(value: Any, *, default: int) -> int:
  if isinstance(value, int) and not isinstance(value, bool) and value > 0:
    return value
  return default
