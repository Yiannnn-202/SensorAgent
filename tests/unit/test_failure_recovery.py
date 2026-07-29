"""Unit tests for failure classification and recovery planning."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest import TestCase

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
  sys.path.insert(0, str(SRC))

from sensoragent.agent import build_agent_from_config
from sensoragent.recovery import FailureDetector, FailureType, RecoveryPlanner, RecoveryStrategy
from sensoragent.schemas import TraceContext
from sensoragent.tools.recovery import RecoveryClassifyFailureTool, RecoveryPlanTool
from sensoragent.tools.vision.failure import MockNotFoundDetectTool
from sensoragent.tools.vision.verify import (
  VisionVerifyObjectInBinTool,
  VisionVerifyObjectLiftedTool,
)
from sensoragent.workflows import DecisionTreeRuntime
from sensoragent.workflows.decision_trees import build_mock_not_found_branch_tree


class FailureDetectorTest(TestCase):
  def test_classifies_object_not_found(self) -> None:
    result = FailureDetector().classify({
      "failed_step": "detect_object",
      "output": {"found": False, "label": "roller", "confidence": 0.0},
      "error": "OBJECT_NOT_FOUND: no match",
    })

    self.assertEqual(result.failure_type, FailureType.OBJECT_NOT_FOUND)
    self.assertTrue(result.retryable)
    self.assertEqual(result.recommended_strategy, RecoveryStrategy.RETRY_DETECT)

  def test_classifies_grasp_empty(self) -> None:
    result = FailureDetector().classify({
      "failed_step": "verify_grasp",
      "output": {"held": False, "opening": 0.0848},
      "error": "grasp not detected (opening=0.0848)",
    })

    self.assertEqual(result.failure_type, FailureType.GRASP_EMPTY)
    self.assertEqual(result.phase, "pick")
    self.assertEqual(result.recommended_strategy, RecoveryStrategy.RETRY_PICK_ADJUSTED_GRASP)

  def test_classifies_wrong_bin(self) -> None:
    result = FailureDetector().classify({
      "failed_step": "verify_object_in_bin",
      "output": {"in_target": False, "distance_xy": 0.2},
      "error": "WRONG_BIN: object is outside the requested target cell",
    })

    self.assertEqual(result.failure_type, FailureType.WRONG_BIN)
    self.assertEqual(result.recommended_strategy, RecoveryStrategy.REPICK_FROM_OBSERVED_POSE)

  def test_classifies_low_confidence(self) -> None:
    result = FailureDetector().classify({
      "failed_step": "detect_object",
      "output": {"found": True, "label": "roller", "confidence": 0.10},
    })

    self.assertEqual(result.failure_type, FailureType.LOW_CONFIDENCE)
    self.assertEqual(result.phase, "perception")
    self.assertTrue(result.retryable)
    self.assertEqual(
      result.recommended_strategy, RecoveryStrategy.RETRY_WITH_EXPANDED_VISION
    )

  def test_classifies_pose_invalid_from_bad_position(self) -> None:
    # A non-finite depth-derived position must be rejected as a bad pose.
    result = FailureDetector().classify({
      "failed_step": "detect_object",
      "output": {"found": True, "confidence": 0.9, "pose_3d": [0.2, 0.1, float("nan")]},
    })

    self.assertEqual(result.failure_type, FailureType.POSE_INVALID)
    self.assertEqual(result.recommended_strategy, RecoveryStrategy.RETRY_WITH_EXPANDED_VISION)

  def test_classifies_pose_invalid_from_error_token(self) -> None:
    result = FailureDetector().classify({
      "failed_step": "detect_object",
      "output": {"found": True, "confidence": 0.9},
      "error": "VISION_DEPTH_ERROR: depth window returned no samples",
    })

    self.assertEqual(result.failure_type, FailureType.POSE_INVALID)
    self.assertEqual(result.recommended_strategy, RecoveryStrategy.RETRY_WITH_EXPANDED_VISION)

  def test_classifies_target_not_found(self) -> None:
    result = FailureDetector().classify({
      "failed_step": "resolve_place_target",
      "error": "TARGET_NOT_FOUND: bin_cell_9 is not registered",
    })

    self.assertEqual(result.failure_type, FailureType.TARGET_NOT_FOUND)
    self.assertFalse(result.retryable)
    self.assertEqual(result.recommended_strategy, RecoveryStrategy.FAIL_FAST)

  def test_classifies_robot_not_ready(self) -> None:
    result = FailureDetector().classify({
      "failed_step": "robot.move_joints",
      "error": "ROBOT_NOT_READY: action server not ready",
    })

    self.assertEqual(result.failure_type, FailureType.ROBOT_NOT_READY)
    self.assertEqual(result.phase, "robot")
    self.assertEqual(result.recommended_strategy, RecoveryStrategy.CHECK_BRIDGE_AND_RESET)

  def test_classifies_bridge_error(self) -> None:
    result = FailureDetector().classify({
      "failed_step": "robot.move_joints",
      "error": "ROBOT_BRIDGE_TIMEOUT: HTTP 504 from /move_joints",
    })

    self.assertEqual(result.failure_type, FailureType.BRIDGE_ERROR)
    self.assertEqual(result.recommended_strategy, RecoveryStrategy.CHECK_BRIDGE_AND_RESET)

  def test_classifies_pick_plan_failed(self) -> None:
    result = FailureDetector().classify({
      "failed_step": "plan_pick",
      "error": "IK failed for top-down approach",
    })

    self.assertEqual(result.failure_type, FailureType.PICK_PLAN_FAILED)
    self.assertEqual(result.phase, "pick")
    self.assertEqual(result.recommended_strategy, RecoveryStrategy.RETRY_PICK_ORIENTED)

  def test_classifies_place_plan_failed(self) -> None:
    result = FailureDetector().classify({
      "failed_step": "plan_place",
      "error": "PLACE_PLAN failed for bin_cell_3",
    })

    self.assertEqual(result.failure_type, FailureType.PLACE_PLAN_FAILED)
    self.assertEqual(result.phase, "place")
    self.assertEqual(result.recommended_strategy, RecoveryStrategy.RETRY_PLACE_CANDIDATES)

  def test_classifies_dropped_object_from_lift_check(self) -> None:
    # The post-grasp lift verification reports the object never rose, so the
    # transport-phase drop classification must fire. Pins the branch added
    # alongside verify_object_lifted so a later refactor cannot silently
    # reclassify it.
    result = FailureDetector().classify({
      "failed_step": "verify_object_lifted",
      "output": {"lifted": False, "before_pose": [0.24, 0.23, 0.142], "after_pose": [0.24, 0.23, 0.145]},
      "error": "DROPPED_OBJECT: object did not rise after grasp",
    })

    self.assertEqual(result.failure_type, FailureType.DROPPED_OBJECT)
    self.assertEqual(result.phase, "transport")
    self.assertTrue(result.retryable)
    self.assertEqual(result.recommended_strategy, RecoveryStrategy.REPICK_FROM_OBSERVED_POSE)

  def test_classifies_release_failed(self) -> None:
    result = FailureDetector().classify({
      "failed_step": "verify_place",
      "output": {"released": False, "opening": 0.03},
      "error": "PLACE NOT CONFIRMED: gripper still closed",
    })

    self.assertEqual(result.failure_type, FailureType.RELEASE_FAILED)
    self.assertEqual(result.recommended_strategy, RecoveryStrategy.RETRY_OPEN_GRIPPER)

  def test_classifies_gripper_failed(self) -> None:
    result = FailureDetector().classify({
      "failed_step": "gripper.open",
      "error": "gripper command returned timeout",
    })

    self.assertEqual(result.failure_type, FailureType.GRIPPER_FAILED)
    self.assertEqual(result.phase, "robot")
    # An open-gripper step routes to retry-open; other gripper steps reset.
    self.assertEqual(result.recommended_strategy, RecoveryStrategy.RETRY_OPEN_GRIPPER)

  def test_classifies_motion_failed(self) -> None:
    # A move step that is neither pick- nor place-phased falls back to a
    # generic motion failure routed through the bridge reset path.
    result = FailureDetector().classify({
      "failed_step": "robot.move_pose",
      "error": "motion aborted",
    })

    self.assertEqual(result.failure_type, FailureType.MOTION_FAILED)
    self.assertEqual(
      result.recommended_strategy, RecoveryStrategy.CHECK_BRIDGE_AND_RESET
    )

  def test_classifies_pick_exec_failed(self) -> None:
    result = FailureDetector().classify({
      "failed_step": "pick",
      "error": "pick action did not complete",
    })

    self.assertEqual(result.failure_type, FailureType.PICK_EXEC_FAILED)
    self.assertEqual(
      result.recommended_strategy, RecoveryStrategy.RECOVER_TO_STAGING_AND_REPLAN_PICK
    )

  def test_classifies_vision_model_not_ready(self) -> None:
    result = FailureDetector().classify({
      "failed_step": "detect_object",
      "error": "VISION_MODEL_NOT_READY: missing models/vision/yoloe.pt",
    })

    self.assertEqual(result.failure_type, FailureType.VISION_MODEL_NOT_READY)
    self.assertFalse(result.retryable)
    self.assertEqual(result.recommended_strategy, RecoveryStrategy.FAIL_FAST)

  def test_classifies_unknown_fallback(self) -> None:
    # Evidence that matches no rule must land on UNKNOWN and fail fast.
    result = FailureDetector().classify({
      "failed_step": "mystery_step",
      "error": "something unexpected happened",
    })

    self.assertEqual(result.failure_type, FailureType.UNKNOWN)
    self.assertFalse(result.retryable)
    self.assertEqual(result.recommended_strategy, RecoveryStrategy.FAIL_FAST)


class RecoveryPlannerTest(TestCase):
  def test_pick_plan_failure_switches_to_oriented_pick(self) -> None:
    classification = FailureDetector().classify({
      "failed_step": "plan_pick",
      "error": "IK failed",
    })

    plan = RecoveryPlanner().plan(classification, {"max_recovery_attempts": 3})

    self.assertEqual(plan.strategy, RecoveryStrategy.RETRY_PICK_ORIENTED)
    self.assertEqual(plan.next_step, "plan_pick")
    self.assertEqual(plan.max_attempts, 3)
    self.assertEqual(plan.updated_input["pick_planner"], "robot.plan_oriented_pick")

  def test_model_missing_fails_fast(self) -> None:
    classification = FailureDetector().classify({
      "failed_step": "detect_object",
      "error": "VISION_MODEL_NOT_READY: missing models/vision/yoloe.pt",
    })

    plan = RecoveryPlanner().plan(classification)

    self.assertEqual(plan.strategy, RecoveryStrategy.FAIL_FAST)
    self.assertFalse(plan.retryable)

  def test_low_confidence_retries_with_expanded_vision(self) -> None:
    classification = FailureDetector().classify({
      "failed_step": "detect_object",
      "output": {"found": True, "confidence": 0.10},
    })

    plan = RecoveryPlanner().plan(classification, {"max_recovery_attempts": 2})

    self.assertEqual(plan.strategy, RecoveryStrategy.RETRY_WITH_EXPANDED_VISION)
    self.assertEqual(plan.next_step, "detect_object")
    self.assertTrue(plan.updated_input["recapture_frame"])
    # Relax perception-side sampling only, never the task target.
    self.assertNotIn("preserve_target", plan.updated_input)

  def test_dropped_object_repicks_from_observed_pose(self) -> None:
    classification = FailureDetector().classify({
      "failed_step": "verify_object_lifted",
      "error": "DROPPED_OBJECT: object did not rise after grasp",
    })

    plan = RecoveryPlanner().plan(classification)

    self.assertEqual(plan.strategy, RecoveryStrategy.REPICK_FROM_OBSERVED_POSE)
    self.assertEqual(plan.next_step, "detect_object")
    self.assertTrue(plan.updated_input["use_observed_pose_as_new_pick_target"])

  def test_wrong_bin_repick_preserves_the_target(self) -> None:
    classification = FailureDetector().classify({
      "failed_step": "verify_object_in_bin",
      "output": {"in_target": False, "distance_xy": 0.3},
      "error": "WRONG_BIN: object outside requested cell",
    })

    plan = RecoveryPlanner().plan(classification)

    self.assertEqual(plan.strategy, RecoveryStrategy.REPICK_FROM_OBSERVED_POSE)
    self.assertEqual(plan.next_step, "detect_object")
    self.assertTrue(plan.updated_input["use_observed_pose_as_new_pick_target"])
    # Re-pick from the wrong-bin pose, but keep re-placing into the same cell.
    self.assertTrue(plan.updated_input["preserve_target"])

  def test_bridge_error_resets_via_health_check(self) -> None:
    classification = FailureDetector().classify({
      "failed_step": "robot.move_joints",
      "error": "ROBOT_BRIDGE_TIMEOUT: HTTP 504",
    })

    plan = RecoveryPlanner().plan(classification)

    self.assertEqual(plan.strategy, RecoveryStrategy.CHECK_BRIDGE_AND_RESET)
    self.assertEqual(plan.next_step, "robot_health_check")
    self.assertTrue(plan.updated_input["call_stop"])

  def test_release_failed_retries_opening_the_gripper(self) -> None:
    classification = FailureDetector().classify({
      "failed_step": "verify_place",
      "error": "PLACE NOT CONFIRMED: gripper still closed",
    })

    plan = RecoveryPlanner().plan(classification)

    self.assertEqual(plan.strategy, RecoveryStrategy.RETRY_OPEN_GRIPPER)
    self.assertEqual(plan.next_step, "place_open_gripper")
    self.assertEqual(plan.updated_input["opening"], 0.0848)

  def test_unknown_failure_fails_fast_with_zero_attempts(self) -> None:
    classification = FailureDetector().classify({
      "failed_step": "mystery_step",
      "error": "something unexpected",
    })

    plan = RecoveryPlanner().plan(classification, {"max_recovery_attempts": 3})

    self.assertEqual(plan.strategy, RecoveryStrategy.FAIL_FAST)
    self.assertFalse(plan.retryable)
    self.assertEqual(plan.max_attempts, 0)
    self.assertIsNone(plan.next_step)


class RecoveryToolTest(TestCase):
  def test_classify_and_plan_tools_round_trip(self) -> None:
    trace = TraceContext()
    classify = RecoveryClassifyFailureTool().run(
      _call(
        "recovery.classify_failure",
        {
          "evidence": {
            "failed_step": "plan_place",
            "error": "PLACE_PLAN failed for bin_cell_1",
          }
        },
        trace,
      )
    )
    self.assertTrue(classify.success, msg=classify.error)
    self.assertEqual(classify.output["failure_type"], "PLACE_PLAN_FAILED")

    plan = RecoveryPlanTool().run(
      _call("recovery.plan", {"classification": classify.output}, trace)
    )
    self.assertTrue(plan.success, msg=plan.error)
    self.assertEqual(plan.output["strategy"], "retry_place_candidates")
    self.assertIn("place_candidate_offsets", plan.output["updated_input"])


class VisionVerificationToolTest(TestCase):
  def test_verify_object_in_bin_success_and_wrong_bin(self) -> None:
    tool = VisionVerifyObjectInBinTool({
      "bin_cell_3": {
        "position": [0.36, -0.06, 0.30],
        "orientation": [0.9962, -0.0872, 0.0, 0.0],
        "frame_id": "base_link",
      }
    })
    trace = TraceContext()

    ok = tool.run(
      _call(
        "vision.verify_object_in_bin",
        {"target": "bin_cell_3", "pose_3d": [0.37, -0.05, 0.31]},
        trace,
      )
    )
    self.assertTrue(ok.success, msg=ok.error)
    self.assertTrue(ok.output["in_target"])

    wrong = tool.run(
      _call(
        "vision.verify_object_in_bin",
        {"target": "bin_cell_3", "pose_3d": [0.55, -0.30, 0.31]},
        trace,
      )
    )
    self.assertFalse(wrong.success)
    self.assertIn("WRONG_BIN", wrong.error or "")

  def test_verify_object_lifted_detects_drop(self) -> None:
    tool = VisionVerifyObjectLiftedTool()
    trace = TraceContext()

    result = tool.run(
      _call(
        "vision.verify_object_lifted",
        {
          "before_pose": [0.24, 0.23, 0.142],
          "after_pose": [0.24, 0.23, 0.145],
        },
        trace,
      )
    )

    self.assertFalse(result.success)
    self.assertIn("DROPPED_OBJECT", result.error or "")


class DecisionTreeLastFailureTest(TestCase):
  def test_failed_node_is_available_to_recovery_tools(self) -> None:
    bundle = build_agent_from_config(ROOT / "configs" / "robot_mock.yaml")
    bundle.tool_registry.register(MockNotFoundDetectTool())
    runtime = DecisionTreeRuntime(
      bundle.tool_runtime,
      bundle.skill_runtime,
      bundle.actionlist_runtime,
      bundle.actionlists,
      bundle.logger,
    )

    result = runtime.run(
      build_mock_not_found_branch_tree(),
      {"object_query": "missing object"},
      TraceContext(),
    )

    self.assertFalse(result.success)
    self.assertIn("last_failure", result.output)
    self.assertEqual(result.output["last_failure"]["failed_step"], "not_found")


def _call(tool: str, input_data: dict, trace: TraceContext):
  from sensoragent.schemas import ToolCall

  return ToolCall(tool=tool, input=input_data, trace=trace)
