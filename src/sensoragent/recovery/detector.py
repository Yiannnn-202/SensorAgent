"""Failure classification heuristics for robot workflow recovery."""

from __future__ import annotations

from math import isfinite
from typing import Any

from sensoragent.recovery.failures import (
  FailureClassification,
  FailureEvidence,
  FailureType,
  RecoveryStrategy,
)


_PICK_STEPS = {"plan_pick", "pick", "verify_grasp", "robot.pick"}
_PLACE_STEPS = {
  "plan_place",
  "place",
  "place_move_place",
  "place_open_gripper",
  "verify_place",
  "robot.place",
}


class FailureDetector:
  """Classify known SensorAgent workflow failures into reportable types."""

  def __init__(
    self,
    *,
    min_confidence: float = 0.35,
    min_grasp_opening: float = 0.002,
    max_grasp_opening: float = 0.08,
  ) -> None:
    self._min_confidence = float(min_confidence)
    self._min_grasp_opening = float(min_grasp_opening)
    self._max_grasp_opening = float(max_grasp_opening)

  def classify(self, evidence: FailureEvidence | dict[str, Any]) -> FailureClassification:
    """Classify failure evidence into a known failure type."""

    normalized = (
      evidence if isinstance(evidence, FailureEvidence) else FailureEvidence.from_dict(evidence)
    )
    error = normalized.error or ""
    error_upper = error.upper()
    output = normalized.output or {}
    step = normalized.failed_step or ""
    target = normalized.target or ""
    phase = normalized.phase or _infer_phase(step)

    if "VISION_MODEL_NOT_READY" in error_upper:
      return _classification(
        FailureType.VISION_MODEL_NOT_READY,
        "perception",
        False,
        0.98,
        "Open-vocabulary vision model weights are not available.",
        normalized,
        RecoveryStrategy.FAIL_FAST,
      )
    if "VISION_BACKEND_UNAVAILABLE" in error_upper:
      return _classification(
        FailureType.VISION_BACKEND_UNAVAILABLE,
        "perception",
        False,
        0.98,
        "Optional vision backend dependencies are not installed.",
        normalized,
        RecoveryStrategy.FAIL_FAST,
      )
    if "OBJECT_NOT_FOUND" in error_upper or output.get("found") is False:
      return _classification(
        FailureType.OBJECT_NOT_FOUND,
        "perception",
        True,
        0.95,
        "Perception completed but no matching object was found.",
        normalized,
        RecoveryStrategy.RETRY_DETECT,
      )
    confidence = output.get("confidence")
    if isinstance(confidence, (int, float)) and not isinstance(confidence, bool):
      if float(confidence) < self._min_confidence:
        return _classification(
          FailureType.LOW_CONFIDENCE,
          "perception",
          True,
          0.85,
          f"Detection confidence {confidence:.3f} is below threshold {self._min_confidence:.3f}.",
          normalized,
          RecoveryStrategy.RETRY_WITH_EXPANDED_VISION,
        )
    if _pose_invalid(output) or any(token in error_upper for token in ("POSE_INVALID", "VISION_DEPTH_ERROR", "VISION_INPUT_ERROR")):
      return _classification(
        FailureType.POSE_INVALID,
        "perception",
        True,
        0.9,
        "Object pose or depth-derived position is invalid.",
        normalized,
        RecoveryStrategy.RETRY_WITH_EXPANDED_VISION,
      )
    if "UNKNOWN PLACE TARGET" in error_upper or "TARGET_NOT_FOUND" in error_upper:
      return _classification(
        FailureType.TARGET_NOT_FOUND,
        "planning",
        False,
        0.95,
        "The requested place target is not registered.",
        normalized,
        RecoveryStrategy.FAIL_FAST,
      )
    if any(token in error_upper for token in ("ROBOT_NOT_READY", "NOT READY", "/READY")):
      return _classification(
        FailureType.ROBOT_NOT_READY,
        "robot",
        True,
        0.9,
        "Robot bridge or required action servers are not ready.",
        normalized,
        RecoveryStrategy.CHECK_BRIDGE_AND_RESET,
      )
    if any(token in error_upper for token in ("ROBOT_BRIDGE_TIMEOUT", "BRIDGE", "HTTP", "CONNECTION")):
      return _classification(
        FailureType.BRIDGE_ERROR,
        "robot",
        True,
        0.9,
        "Robot HTTP bridge returned an integration failure.",
        normalized,
        RecoveryStrategy.CHECK_BRIDGE_AND_RESET,
      )
    if step == "plan_pick" or "PLAN_TOP_DOWN_PICK" in error_upper or "PICK_PLAN" in error_upper:
      return _classification(
        FailureType.PICK_PLAN_FAILED,
        "pick",
        True,
        0.9,
        "Pick planning failed before robot execution.",
        normalized,
        RecoveryStrategy.RETRY_PICK_ORIENTED,
      )
    if step == "plan_place" or "PLAN_PLACE" in error_upper or "PLACE_PLAN" in error_upper:
      return _classification(
        FailureType.PLACE_PLAN_FAILED,
        "place",
        True,
        0.9,
        "Place planning failed before robot execution.",
        normalized,
        RecoveryStrategy.RETRY_PLACE_CANDIDATES,
      )
    if step == "verify_grasp" or "GRASP NOT DETECTED" in error_upper:
      return self._classify_grasp_failure(normalized)
    if step in {"verify_object_lifted", "verify_transport"} or "DROPPED_OBJECT" in error_upper:
      return _classification(
        FailureType.DROPPED_OBJECT,
        "transport",
        True,
        0.9,
        "Object is not confirmed to be held during transport.",
        normalized,
        RecoveryStrategy.REPICK_FROM_OBSERVED_POSE,
      )
    if step == "verify_place" or "PLACE NOT CONFIRMED" in error_upper:
      return _classification(
        FailureType.RELEASE_FAILED,
        "place",
        True,
        0.88,
        "The gripper did not reach the expected released state.",
        normalized,
        RecoveryStrategy.RETRY_OPEN_GRIPPER,
      )
    if step == "verify_object_in_bin" or "WRONG_BIN" in error_upper:
      return _classification(
        FailureType.WRONG_BIN,
        "place",
        True,
        0.95,
        "Vision verification says the object is not in the requested bin cell.",
        normalized,
        RecoveryStrategy.REPICK_FROM_OBSERVED_POSE,
      )
    if "GRIPPER" in step.upper() or "GRIPPER" in error_upper:
      strategy = RecoveryStrategy.RETRY_OPEN_GRIPPER if "OPEN" in step.upper() else RecoveryStrategy.CHECK_BRIDGE_AND_RESET
      return _classification(
        FailureType.GRIPPER_FAILED,
        "robot",
        True,
        0.82,
        "Gripper command failed.",
        normalized,
        strategy,
      )
    if step.startswith("robot.move") or target.startswith("robot.move") or step in {"place_move_place", "place_retreat"}:
      if phase == "pick" or step in _PICK_STEPS:
        failure_type = FailureType.PICK_EXEC_FAILED
        strategy = RecoveryStrategy.RECOVER_TO_STAGING_AND_REPLAN_PICK
      elif phase == "place" or step in _PLACE_STEPS:
        failure_type = FailureType.PLACE_EXEC_FAILED
        strategy = RecoveryStrategy.RECOVER_TO_STAGING_AND_REPLAN_PLACE
      else:
        failure_type = FailureType.MOTION_FAILED
        strategy = RecoveryStrategy.CHECK_BRIDGE_AND_RESET
      return _classification(
        failure_type,
        phase,
        True,
        0.8,
        "Robot motion command failed.",
        normalized,
        strategy,
      )
    if step in _PICK_STEPS:
      return _classification(
        FailureType.PICK_EXEC_FAILED,
        "pick",
        True,
        0.75,
        "Pick phase failed and should be locally replanned.",
        normalized,
        RecoveryStrategy.RECOVER_TO_STAGING_AND_REPLAN_PICK,
      )
    if step in _PLACE_STEPS:
      return _classification(
        FailureType.PLACE_EXEC_FAILED,
        "place",
        True,
        0.75,
        "Place phase failed and should be locally replanned.",
        normalized,
        RecoveryStrategy.RECOVER_TO_STAGING_AND_REPLAN_PLACE,
      )
    return _classification(
      FailureType.UNKNOWN,
      phase,
      False,
      0.3,
      "No known failure rule matched the evidence.",
      normalized,
      RecoveryStrategy.FAIL_FAST,
    )

  def _classify_grasp_failure(self, evidence: FailureEvidence) -> FailureClassification:
    opening = _opening_from_evidence(evidence)
    reason = "Grasp verifier did not confirm a held object."
    if opening is not None:
      reason = f"Gripper opening {opening:.4f} is outside held-object range."
    return _classification(
      FailureType.GRASP_EMPTY,
      "pick",
      True,
      0.92,
      reason,
      evidence,
      RecoveryStrategy.RETRY_PICK_ADJUSTED_GRASP,
    )


def classify_failure(evidence: FailureEvidence | dict[str, Any]) -> FailureClassification:
  """Convenience wrapper using default thresholds."""

  return FailureDetector().classify(evidence)


def _classification(
  failure_type: FailureType,
  phase: str,
  retryable: bool,
  confidence: float,
  reason: str,
  evidence: FailureEvidence,
  strategy: RecoveryStrategy,
) -> FailureClassification:
  return FailureClassification(
    failure_type=failure_type,
    phase=phase,
    retryable=retryable,
    confidence=confidence,
    reason=reason,
    evidence=evidence,
    recommended_strategy=strategy,
  )


def _infer_phase(step: str) -> str:
  if "detect" in step or "vision" in step:
    return "perception"
  if "pick" in step or "grasp" in step:
    return "pick"
  if "place" in step or "bin" in step or "release" in step:
    return "place"
  if "move" in step or "gripper" in step or "robot" in step:
    return "robot"
  return "unknown"


def _pose_invalid(output: dict[str, Any]) -> bool:
  if not output:
    return False
  pose = output.get("pose_3d") or output.get("position_base") or output.get("position")
  if pose is None:
    return False
  if not isinstance(pose, list) or len(pose) < 3:
    return True
  return not all(isinstance(value, (int, float)) and not isinstance(value, bool) and isfinite(float(value)) for value in pose[:3])


def _opening_from_evidence(evidence: FailureEvidence) -> float | None:
  candidates = [evidence.output or {}, evidence.observed or {}]
  for candidate in candidates:
    opening = candidate.get("opening")
    if isinstance(opening, (int, float)) and not isinstance(opening, bool):
      return float(opening)
    state = candidate.get("state")
    if isinstance(state, dict):
      opening = state.get("opening")
      if isinstance(opening, (int, float)) and not isinstance(opening, bool):
        return float(opening)
  return None
