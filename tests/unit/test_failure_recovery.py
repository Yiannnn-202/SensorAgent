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
