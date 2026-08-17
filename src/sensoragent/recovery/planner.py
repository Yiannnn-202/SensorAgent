"""Deterministic local recovery planning."""

from __future__ import annotations

from typing import Any

from sensoragent.recovery.detector import classify_failure
from sensoragent.recovery.failures import (
  FailureClassification,
  FailureType,
  RecoveryPlan,
  RecoveryStrategy,
)


_DEFAULT_PICK_POSITION_OFFSET = [0.0, 0.0, 0.02]
_DEFAULT_PICK_CLOSE_OPENING = 0.032
_DEFAULT_PLACE_CLEARANCE = 0.08


class RecoveryPlanner:
  """Map classified failures to bounded, explainable replanning strategies."""

  def __init__(self, *, default_max_attempts: int = 2) -> None:
    self._default_max_attempts = max(1, int(default_max_attempts))

  def plan(
    self,
    classification: FailureClassification | dict[str, Any],
    context: dict[str, Any] | None = None,
  ) -> RecoveryPlan:
    """Create a recovery plan from a failure classification."""

    normalized = (
      classification
      if isinstance(classification, FailureClassification)
      else FailureClassification.from_dict(classification)
    )
    context = context or {}
    max_attempts = _max_attempts(context, self._default_max_attempts)
    failure_type = normalized.failure_type

    if failure_type in {
      FailureType.VISION_MODEL_NOT_READY,
      FailureType.VISION_BACKEND_UNAVAILABLE,
      FailureType.TARGET_NOT_FOUND,
      FailureType.UNKNOWN,
    }:
      return _plan(
        RecoveryStrategy.FAIL_FAST,
        failure_type,
        False,
        None,
        0,
        notes=[normalized.reason],
      )
    if failure_type == FailureType.OBJECT_NOT_FOUND:
      return _plan(
        RecoveryStrategy.RETRY_DETECT,
        failure_type,
        True,
        "detect_object",
        max_attempts,
        updated_input={"allow_query_expansion": True, "recapture_frame": True},
        notes=["Re-observe the scene before deciding the object is absent."],
      )
    if failure_type in {FailureType.LOW_CONFIDENCE, FailureType.POSE_INVALID}:
      return _plan(
        RecoveryStrategy.RETRY_WITH_EXPANDED_VISION,
        failure_type,
        True,
        "detect_object",
        max_attempts,
        updated_input={
          "recapture_frame": True,
          "depth_window_delta": 4,
          "min_confidence_delta": -0.05,
        },
        node_overrides={
          "recover_redetect": {
            "depth_window": _positive_number(context.get("depth_window"), 7) + 4,
          },
        },
        notes=["Refresh RGB-D evidence and relax only perception-side sampling parameters."],
      )
    if failure_type == FailureType.PICK_PLAN_FAILED:
      return _plan(
        RecoveryStrategy.RETRY_PICK_ORIENTED,
        failure_type,
        True,
        "plan_pick",
        max_attempts,
        updated_input={
          "pick_planner": "robot.plan_oriented_pick",
          "approach_distance_delta": 0.03,
          "position_offset_delta": [0.0, 0.0, 0.01],
        },
        node_overrides={
          "recover_pick": {
            "oriented_pick_requested": True,
            "oriented_pick_applied": False,
            "oriented_pick_reason": "missing_base_frame_object_points",
            "position_offset": _add_xyz(
              context.get("pick_position_offset"),
              [0.0, 0.0, 0.01],
              _DEFAULT_PICK_POSITION_OFFSET,
            ),
          },
        },
        notes=["Switch from top-down grasp to oriented grasp and add clearance."],
      )
    if failure_type == FailureType.GRASP_EMPTY:
      return _plan(
        RecoveryStrategy.RETRY_PICK_ADJUSTED_GRASP,
        failure_type,
        True,
        "plan_pick",
        max_attempts,
        updated_input={
          "close_opening_delta": -0.005,
          "position_offset_candidates": [[0.0, 0.0, 0.02], [0.0, 0.0, 0.035]],
          "recapture_frame": True,
        },
        node_overrides={
          "recover_pick": {
            "position_offset": [0.0, 0.0, 0.035],
            "close_opening": max(
              0.0,
              _number(context.get("pick_close_opening"), _DEFAULT_PICK_CLOSE_OPENING)
              - 0.005,
            ),
          },
        },
        notes=["Re-detect the object and retry with adjusted TCP/gripper closure."],
      )
    if failure_type in {FailureType.PICK_EXEC_FAILED, FailureType.MOTION_FAILED}:
      return _plan(
        RecoveryStrategy.RECOVER_TO_STAGING_AND_REPLAN_PICK,
        failure_type,
        True,
        "plan_pick",
        max_attempts,
        updated_input={"reset_to_staging": True, "recapture_frame": True},
        node_overrides={
          "recover_pick": {"position_offset": _DEFAULT_PICK_POSITION_OFFSET},
        },
        notes=["Stop overlapping motion, return to staging, and regenerate pick waypoints."],
      )
    if failure_type == FailureType.DROPPED_OBJECT:
      return _plan(
        RecoveryStrategy.REPICK_FROM_OBSERVED_POSE,
        failure_type,
        True,
        "detect_object",
        max_attempts,
        updated_input={"use_observed_pose_as_new_pick_target": True},
        node_overrides={
          # pose_3d is filled by the DecisionTree runtime from the observed
          # failure pose; when no observation exists the runtime reroutes to
          # recover_pick (re-detection) instead.
          "recover_pick_at_pose": {
            "use_observed_pose_as_new_pick_target": True,
          },
        },
        notes=["Treat the dropped object pose as the new pick target."],
      )
    if failure_type == FailureType.PLACE_PLAN_FAILED:
      return _plan(
        RecoveryStrategy.RETRY_PLACE_CANDIDATES,
        failure_type,
        True,
        "plan_place",
        max_attempts,
        updated_input={
          "place_candidate_offsets": [
            [0.0, 0.0, 0.03],
            [-0.04, 0.0, 0.04],
            [0.04, 0.0, 0.04],
            [0.0, 0.04, 0.04],
            [0.0, -0.04, 0.04],
          ],
          "clearance_delta": 0.05,
        },
        node_overrides={
          "recover_place": {
            "place_offset": [0.0, 0.0, 0.03],
            "clearance": _number(
              context.get("place_clearance"),
              _DEFAULT_PLACE_CLEARANCE,
            )
            + 0.05,
          },
        },
        notes=["Try nearby release poses and slightly higher clearance before giving up."],
      )
    if failure_type == FailureType.PLACE_EXEC_FAILED:
      return _plan(
        RecoveryStrategy.RECOVER_TO_STAGING_AND_REPLAN_PLACE,
        failure_type,
        True,
        "plan_place",
        max_attempts,
        updated_input={"reset_to_staging": True, "clearance_delta": 0.05},
        node_overrides={
          "recover_place": {
            "clearance": _number(context.get("place_clearance"), _DEFAULT_PLACE_CLEARANCE)
            + 0.05,
          },
        },
        notes=["Return to place staging joints and regenerate the target approach."],
      )
    if failure_type in {FailureType.RELEASE_FAILED, FailureType.GRIPPER_FAILED}:
      return _plan(
        RecoveryStrategy.RETRY_OPEN_GRIPPER,
        failure_type,
        True,
        "place_open_gripper",
        max_attempts,
        updated_input={"opening": 0.0848, "speed": 0.3, "stop_after_retry": True},
        node_overrides={
          "recover_release": {"opening": 0.0848, "speed": 0.3},
        },
        notes=["Retry open command at conservative speed, then retreat and re-verify."],
      )
    if failure_type == FailureType.WRONG_BIN:
      return _plan(
        RecoveryStrategy.REPICK_FROM_OBSERVED_POSE,
        failure_type,
        True,
        "detect_object",
        max_attempts,
        updated_input={"use_observed_pose_as_new_pick_target": True, "preserve_target": True},
        node_overrides={
          # pose_3d is filled by the runtime from the observed wrong-bin pose;
          # without an observation the runtime reroutes to recover_pick. The
          # requested target stays untouched (preserve_target semantics).
          "recover_pick_at_pose": {
            "use_observed_pose_as_new_pick_target": True,
            "preserve_target": True,
          },
        },
        notes=["Re-pick the object from its observed wrong-bin pose and place it into the requested cell."],
      )
    if failure_type in {FailureType.BRIDGE_ERROR, FailureType.ROBOT_NOT_READY}:
      return _plan(
        RecoveryStrategy.CHECK_BRIDGE_AND_RESET,
        failure_type,
        True,
        "robot_health_check",
        max_attempts,
        updated_input={"call_stop": True, "check_ready": True, "reset_home": True},
        node_overrides={
          "recover_bridge": {"reason": failure_type.value},
        },
        notes=["Stop motion, wait for bridge readiness, and reset home before replanning."],
      )
    return _plan(
      RecoveryStrategy.FAIL_FAST,
      failure_type,
      False,
      None,
      0,
      notes=[f"No recovery policy for {failure_type.value}."],
    )


def plan_recovery(
  classification: FailureClassification | dict[str, Any],
  context: dict[str, Any] | None = None,
) -> RecoveryPlan:
  """Convenience wrapper using default RecoveryPlanner settings."""

  return RecoveryPlanner().plan(classification, context)


def plan_recovery_from_evidence(
  evidence: dict[str, Any],
  context: dict[str, Any] | None = None,
) -> RecoveryPlan:
  """Classify raw evidence and return a recovery plan."""

  return plan_recovery(classify_failure(evidence), context)


def _plan(
  strategy: RecoveryStrategy,
  failure_type: FailureType,
  retryable: bool,
  next_step: str | None,
  max_attempts: int,
  *,
  updated_input: dict[str, Any] | None = None,
  node_overrides: dict[str, dict[str, Any]] | None = None,
  notes: list[str] | None = None,
) -> RecoveryPlan:
  return RecoveryPlan(
    strategy=strategy,
    failure_type=failure_type,
    retryable=retryable,
    next_step=next_step,
    max_attempts=max_attempts,
    updated_input=updated_input or {},
    node_overrides=node_overrides or {},
    notes=notes or [],
  )


def _max_attempts(context: dict[str, Any], default: int) -> int:
  value = context.get("max_recovery_attempts")
  if isinstance(value, int) and not isinstance(value, bool) and value > 0:
    return value
  return default


def _number(value: Any, default: float) -> float:
  if isinstance(value, (int, float)) and not isinstance(value, bool):
    return float(value)
  return default


def _positive_number(value: Any, default: int) -> int:
  if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0:
    return int(value)
  return default


def _add_xyz(value: Any, delta: list[float], default: list[float]) -> list[float]:
  base = (
    [float(item) for item in value]
    if isinstance(value, list)
    and len(value) >= 3
    and all(isinstance(item, (int, float)) and not isinstance(item, bool) for item in value[:3])
    else list(default)
  )
  return [base[index] + float(delta[index]) for index in range(3)]
