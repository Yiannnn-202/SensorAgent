"""Tests for the industrial failure-recovery DecisionTree."""

from __future__ import annotations

import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from unittest import TestCase

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
  sys.path.insert(0, str(SRC))

from sensoragent.schemas import TraceContext
from sensoragent.tools.recovery import RecoveryClassifyFailureTool, RecoveryPlanTool
from sensoragent.tools.vision import VisionVerifyObjectInBinTool, VisionVerifyObjectLiftedTool
from sensoragent.workflows.actionlists import (
  ActionListRuntime,
  build_industrial_pick_only_actionlist,
  build_industrial_place_only_actionlist,
)
from sensoragent.workflows.decision_trees.industrial import (
  build_industrial_recovery_pick_place_tree,
)
from sensoragent.workflows.decision_trees.runtime import DecisionTreeRuntime


@dataclass
class _StubResult:
  success: bool
  output: dict | None = None
  error: str | None = None


class _StubRuntime:
  def __init__(self, handlers: dict) -> None:
    self._handlers = handlers
    self.calls: list[tuple[str, dict]] = []

  def invoke(self, name: str, input_data: dict, trace: TraceContext) -> _StubResult:
    self.calls.append((name, input_data))
    handler = self._handlers.get(name)
    if handler is None:
      return _StubResult(False, error=f"no stub for {name}")
    result = handler(input_data)
    if isinstance(result, _StubResult):
      return result
    return _StubResult(True, output=result)


class _NullLogger:
  def log(self, *args, **kwargs) -> None:
    return None


class IndustrialRecoveryTreeTest(TestCase):
  def test_nominal_recovery_tree_succeeds_without_recovery(self) -> None:
    runtime, tool_runtime, _ = _make_runtime()

    result = runtime.run(
      build_industrial_recovery_pick_place_tree(),
      {"object_query": "roller", "target": "bin_cell_3"},
      TraceContext(),
    )

    self.assertTrue(result.success, msg=result.error)
    self.assertEqual(result.nodes[-1].node, "success")
    self.assertNotIn("recovery.classify_failure", [call[0] for call in tool_runtime.calls])

  def test_configured_intermediate_joints_are_in_nominal_tree(self) -> None:
    runtime, tool_runtime, _ = _make_runtime()
    joint_poses = {
      "observe_joints": [0.0, 0.1, -0.2, 0.3, -0.4, 0.5],
      "pick_staging_joints": [0.1, 0.2, -0.3, 0.4, -0.5, 0.6],
      "carry_joints": [0.2, 0.3, -0.4, 0.5, -0.6, 0.7],
      "place_staging_joints": [0.3, 0.4, -0.5, 0.6, -0.7, 0.8],
    }

    result = runtime.run(
      build_industrial_recovery_pick_place_tree(joint_poses),
      {"object_query": "roller", "target": "bin_cell_3"},
      TraceContext(),
    )

    self.assertTrue(result.success, msg=result.error)
    self.assertEqual(
      [node.node for node in result.nodes],
      [
        "observe_before_detect",
        "detect_object",
        "plan_pick",
        "pick_staging_joints",
        "pick",
        "verify_grasp",
        "carry_joints",
        "resolve_place_target",
        "plan_place",
        "place_pre_approach_joints",
        "place_move_place",
        "place_open_gripper",
        "place_lift_clearance",
        "place_retreat",
        "observe_after_place",
        "verify_place",
        "verify_object_in_bin",
        "success",
      ],
    )
    move_joints_inputs = [
      input_data["joints"]
      for name, input_data in tool_runtime.calls
      if name == "robot.move_joints"
    ]
    self.assertEqual(
      move_joints_inputs,
      [
        joint_poses["observe_joints"],
        joint_poses["pick_staging_joints"],
        joint_poses["carry_joints"],
        joint_poses["place_staging_joints"],
        joint_poses["place_staging_joints"],
        joint_poses["observe_joints"],
      ],
    )

  def test_staging_move_failure_recovers_via_bridge_reset(self) -> None:
    # A staging move_joints failure (here observe_before_detect) classifies as
    # MOTION_FAILED and routes through recover_bridge (robot.stop -> redetect ->
    # plan_pick) instead of fail-fast at the chain tail.
    joint_poses = {
      "observe_joints": [0.0, 0.1, -0.2, 0.3, -0.4, 0.5],
      "pick_staging_joints": [0.1, 0.2, -0.3, 0.4, -0.5, 0.6],
      "carry_joints": [0.2, 0.3, -0.4, 0.5, -0.6, 0.7],
      "place_staging_joints": [0.3, 0.4, -0.5, 0.6, -0.7, 0.8],
    }
    runtime, _tool_runtime, _ = _make_runtime(
      move_joints_sequence=[
        _StubResult(False, error="motion aborted during observe"),
        _StubResult(True, {"completed": True, "state": {}}),
      ],
    )

    result = runtime.run(
      build_industrial_recovery_pick_place_tree(joint_poses),
      {"object_query": "roller", "target": "bin_cell_3"},
      TraceContext(),
    )

    self.assertTrue(result.success, msg=result.error)
    node_names = [node.node for node in result.nodes]
    self.assertIn("recover_bridge", node_names)
    self.assertEqual(result.output["classification"]["failure_type"], "MOTION_FAILED")

  def test_recovery_attempts_are_bounded_by_max_recovery_attempts(self) -> None:
    # With max_recovery_attempts=1, the second entry into recovery.classify_failure
    # must short-circuit to failure instead of attempting another recovery.
    runtime, tool_runtime, _ = _make_runtime(
      plan_pick_sequence=[
        _StubResult(False, error="PLAN_TOP_DOWN_PICK failed: IK unreachable"),
        _StubResult(True, _pick_plan()),
      ],
      plan_place_sequence=[_StubResult(False, error="PLACE_PLAN failed for bin_cell_3")],
    )

    result = runtime.run(
      build_industrial_recovery_pick_place_tree(),
      {"object_query": "roller", "target": "bin_cell_3", "max_recovery_attempts": 1},
      TraceContext(),
    )

    self.assertFalse(result.success)
    self.assertIn("max_recovery_attempts", result.error or "")
    # classify_failure runs once (first recovery); the second entry short-circuits.
    self.assertEqual(
      [call[0] for call in tool_runtime.calls].count("recovery.classify_failure"), 1
    )

  def test_recovery_attempts_are_observable_in_output(self) -> None:
    # The recovery counter must land in the tree context so result.output shows
    # how many recoveries actually ran; without it, debugging a short-circuit
    # only yields the configured limit from the error message.
    runtime, tool_runtime, _ = _make_runtime(
      plan_pick_sequence=[
        _StubResult(False, error="PLAN_TOP_DOWN_PICK failed: IK unreachable"),
        _StubResult(True, _pick_plan()),
      ]
    )

    result = runtime.run(
      build_industrial_recovery_pick_place_tree(),
      {"object_query": "roller", "target": "bin_cell_3"},
      TraceContext(),
    )

    self.assertTrue(result.success, msg=result.error)
    classify_calls = [call[0] for call in tool_runtime.calls].count("recovery.classify_failure")
    self.assertEqual(result.output["recovery_attempts"], classify_calls)
    self.assertEqual(result.output["recovery_attempts"], 1)
    # Per-attempt recovery evidence is accumulated for offline metrics: the
    # history length agrees with the counter, the recorded failure type matches
    # the final classification, and plan_recovery backfills the chosen strategy.
    history = result.output.get("recovery_history", [])
    self.assertEqual(len(history), result.output["recovery_attempts"])
    self.assertEqual(
      history[0]["failure_type"],
      result.output["classification"]["failure_type"],
    )
    self.assertEqual(history[0]["strategy"], result.output["recovery"]["strategy"])

  def test_recovery_attempts_are_observable_after_short_circuit(self) -> None:
    # On short-circuit the counter reflects the recoveries that ran (1), while
    # the error carries the limit that was exceeded.
    runtime, tool_runtime, _ = _make_runtime(
      plan_pick_sequence=[
        _StubResult(False, error="PLAN_TOP_DOWN_PICK failed: IK unreachable"),
        _StubResult(True, _pick_plan()),
      ],
      plan_place_sequence=[_StubResult(False, error="PLACE_PLAN failed for bin_cell_3")],
    )

    result = runtime.run(
      build_industrial_recovery_pick_place_tree(),
      {"object_query": "roller", "target": "bin_cell_3", "max_recovery_attempts": 1},
      TraceContext(),
    )

    self.assertFalse(result.success)
    self.assertEqual(
      result.output["recovery_attempts"],
      [call[0] for call in tool_runtime.calls].count("recovery.classify_failure"),
    )
    self.assertEqual(result.output["recovery_attempts"], 1)
    # A refused (short-circuited) attempt must not append to recovery_history;
    # only the recovery that actually ran is recorded.
    self.assertEqual(len(result.output.get("recovery_history", [])), 1)

  def test_pick_node_uses_block_close_opening(self) -> None:
    tree = build_industrial_recovery_pick_place_tree()
    pick_node = next(node for node in tree.nodes if node.name == "pick")

    self.assertEqual(pick_node.input["close_opening"], 0.032)
    self.assertEqual(pick_node.input["gripper_force"], 1.0)

  def test_grasp_failure_recovers_by_re_pick(self) -> None:
    runtime, tool_runtime, skill_runtime = _make_runtime(
      verify_grasp_sequence=[
        _StubResult(False, {"held": False, "opening": 0.0848}, "grasp not detected (opening=0.0848)"),
        _StubResult(True, {"held": True, "opening": 0.03}),
      ]
    )

    result = runtime.run(
      build_industrial_recovery_pick_place_tree(),
      {"object_query": "roller", "target": "bin_cell_3"},
      TraceContext(),
    )

    self.assertTrue(result.success, msg=result.error)
    self.assertIn("recover_pick", [node.node for node in result.nodes])
    self.assertIn("recovery.classify_failure", [call[0] for call in tool_runtime.calls])
    self.assertGreaterEqual([call[0] for call in skill_runtime.calls].count("robot.verify_grasp"), 2)
    self.assertEqual(result.output["classification"]["failure_type"], "GRASP_EMPTY")

  def test_place_plan_failure_recovers_with_place_only_actionlist(self) -> None:
    runtime, tool_runtime, _ = _make_runtime(
      plan_place_sequence=[
        _StubResult(False, error="PLACE_PLAN failed for bin_cell_3"),
        _StubResult(True, _place_plan()),
      ]
    )

    result = runtime.run(
      build_industrial_recovery_pick_place_tree(),
      {"object_query": "roller", "target": "bin_cell_3"},
      TraceContext(),
    )

    self.assertTrue(result.success, msg=result.error)
    self.assertIn("recover_place", [node.node for node in result.nodes])
    self.assertEqual(result.output["classification"]["failure_type"], "PLACE_PLAN_FAILED")
    self.assertGreaterEqual([call[0] for call in tool_runtime.calls].count("robot.plan_place"), 2)

  def test_wrong_bin_recovers_by_re_pick_and_re_place(self) -> None:
    runtime, tool_runtime, _ = _make_runtime(
      verify_bin_sequence=[
        _StubResult(
          False,
          {
            "target": "bin_cell_3",
            "in_target": False,
            "object_position": [0.55, -0.30, 0.31],
            "target_position": [0.36, -0.06, 0.30],
            "distance_xy": 0.30,
          },
          "WRONG_BIN: object is outside the requested target cell",
        ),
        _StubResult(
          True,
          {
            "target": "bin_cell_3",
            "in_target": True,
            "object_position": [0.36, -0.06, 0.30],
            "target_position": [0.36, -0.06, 0.30],
            "distance_xy": 0.0,
          },
        ),
      ]
    )

    result = runtime.run(
      build_industrial_recovery_pick_place_tree(),
      {"object_query": "roller", "target": "bin_cell_3"},
      TraceContext(),
    )

    self.assertTrue(result.success, msg=result.error)
    self.assertIn("recover_pick", [node.node for node in result.nodes])
    self.assertEqual(result.output["classification"]["failure_type"], "WRONG_BIN")
    self.assertGreaterEqual([call[0] for call in tool_runtime.calls].count("vision.verify_object_in_bin"), 2)

  def test_object_not_found_recovers_by_redetect(self) -> None:
    # The detect node has one internal retry (max_retries=1), so it must fail
    # twice before the tree classifies the failure. Recovery re-observes and
    # re-detects, then the nominal pick-place flow completes.
    runtime, tool_runtime, _ = _make_runtime(
      config_detect_sequence=[
        _StubResult(False, {"found": False, "confidence": 0.0}, "OBJECT_NOT_FOUND: no match for roller"),
        _StubResult(False, {"found": False, "confidence": 0.0}, "OBJECT_NOT_FOUND: no match for roller"),
        _StubResult(True, _config_detection()),
      ]
    )

    result = runtime.run(
      build_industrial_recovery_pick_place_tree(),
      {"object_query": "roller", "target": "bin_cell_3"},
      TraceContext(),
    )

    self.assertTrue(result.success, msg=result.error)
    node_names = [node.node for node in result.nodes]
    self.assertIn("recover_redetect", node_names)
    self.assertEqual(result.output["classification"]["failure_type"], "OBJECT_NOT_FOUND")
    # detect_object is retried internally (2 calls) then recover_redetect runs
    # once more, for 3 detect calls in total.
    self.assertEqual(
      [call[0] for call in tool_runtime.calls].count("vision.config_detect"), 3
    )

  def test_low_confidence_recovers_by_redetect(self) -> None:
    # The detector surfaces a low-confidence detection as a failed detect node;
    # recovery re-observes and re-detects with relaxed vision sampling.
    runtime, tool_runtime, _ = _make_runtime(
      config_detect_sequence=[
        _StubResult(False, {"found": True, "confidence": 0.10}, "LOW_CONFIDENCE: 0.010 below 0.350"),
        _StubResult(False, {"found": True, "confidence": 0.10}, "LOW_CONFIDENCE: 0.010 below 0.350"),
        _StubResult(True, _config_detection()),
      ]
    )

    result = runtime.run(
      build_industrial_recovery_pick_place_tree(),
      {"object_query": "roller", "target": "bin_cell_3"},
      TraceContext(),
    )

    self.assertTrue(result.success, msg=result.error)
    self.assertIn("recover_redetect", [node.node for node in result.nodes])
    self.assertEqual(result.output["classification"]["failure_type"], "LOW_CONFIDENCE")

  def test_pose_invalid_recovers_by_redetect(self) -> None:
    # A non-finite depth-derived position makes the pose unusable; the detect
    # node fails through its internal retry, then recovery re-detects to
    # refresh RGB-D evidence.
    runtime, tool_runtime, _ = _make_runtime(
      config_detect_sequence=[
        _StubResult(False, {"found": True, "confidence": 0.9}, "VISION_DEPTH_ERROR: non-finite pose_3d"),
        _StubResult(False, {"found": True, "confidence": 0.9}, "VISION_DEPTH_ERROR: non-finite pose_3d"),
        _StubResult(True, _config_detection()),
      ]
    )

    result = runtime.run(
      build_industrial_recovery_pick_place_tree(),
      {"object_query": "roller", "target": "bin_cell_3"},
      TraceContext(),
    )

    self.assertTrue(result.success, msg=result.error)
    self.assertIn("recover_redetect", [node.node for node in result.nodes])
    self.assertEqual(result.output["classification"]["failure_type"], "POSE_INVALID")

  def test_pick_plan_failure_recovers_by_re_pick(self) -> None:
    runtime, tool_runtime, _ = _make_runtime(
      plan_pick_sequence=[
        _StubResult(False, error="PLAN_TOP_DOWN_PICK failed: IK unreachable"),
        _StubResult(True, _pick_plan()),
      ]
    )

    result = runtime.run(
      build_industrial_recovery_pick_place_tree(),
      {"object_query": "roller", "target": "bin_cell_3"},
      TraceContext(),
    )

    self.assertTrue(result.success, msg=result.error)
    self.assertIn("recover_pick", [node.node for node in result.nodes])
    self.assertEqual(result.output["classification"]["failure_type"], "PICK_PLAN_FAILED")
    self.assertGreaterEqual(
      [call[0] for call in tool_runtime.calls].count("robot.plan_top_down_pick"), 2
    )

  def test_max_recovery_attempts_is_forwarded_to_planner(self) -> None:
    # The tree declares max_recovery_attempts as an input, so when a caller sets
    # it the recovery planner must honour it instead of always falling back to
    # the default of 2. Pins the plan_recovery node forwarding the attempt limit
    # through to RecoveryPlanTool via the context input.
    runtime, _tool_runtime, _ = _make_runtime(
      plan_pick_sequence=[
        _StubResult(False, error="PLAN_TOP_DOWN_PICK failed: IK unreachable"),
        _StubResult(True, _pick_plan()),
      ]
    )

    result = runtime.run(
      build_industrial_recovery_pick_place_tree(),
      {"object_query": "roller", "target": "bin_cell_3", "max_recovery_attempts": 5},
      TraceContext(),
    )

    self.assertTrue(result.success, msg=result.error)
    self.assertEqual(result.output["recovery"]["max_attempts"], 5)

  def test_release_failure_recovers_by_reopening_gripper(self) -> None:
    # The gripper does not confirm release on the first place; recovery re-opens
    # it and then rejoins the lift-clearance step rather than re-placing.
    runtime, tool_runtime, _ = _make_runtime(
      verify_place_sequence=[
        _StubResult(False, {"released": False, "opening": 0.03}, "PLACE NOT CONFIRMED: gripper still closed"),
        _StubResult(True, {"released": True, "opening": 0.0848}),
      ]
    )

    result = runtime.run(
      build_industrial_recovery_pick_place_tree(),
      {"object_query": "roller", "target": "bin_cell_3"},
      TraceContext(),
    )

    self.assertTrue(result.success, msg=result.error)
    node_names = [node.node for node in result.nodes]
    self.assertIn("recover_release", node_names)
    # After re-opening the gripper the tree rejoins the lift-clearance node,
    # not the start of place, so the place motion is not repeated.
    self.assertIn("place_lift_clearance", node_names)
    self.assertEqual(result.output["classification"]["failure_type"], "RELEASE_FAILED")


class LiveDetectRecoveryTreeTest(TestCase):
  """The perception-driven variant must observe placement, not assume it."""

  def test_live_tree_captures_a_frame_before_each_detection(self) -> None:
    runtime, tool_runtime, _ = _make_runtime(
      real_verify_in_bin=True,
      open_vocab_sequence=[
        _StubResult(True, _detection([0.24, 0.23, 0.142])),
        _StubResult(True, _detection([0.24, 0.23, 0.30])),
        _StubResult(True, _detection([0.36, -0.06, 0.30])),
      ],
    )

    result = runtime.run(_live_tree(), _live_request(), TraceContext())

    self.assertTrue(result.success, msg=result.error)
    names = [call[0] for call in tool_runtime.calls]
    self.assertNotIn("vision.config_detect", names)
    self.assertEqual(names[0], "vision.capture_frame")
    self.assertEqual(names[1], "vision.open_vocab_detect")
    # One capture for the initial detection, one after grasping, one after placing.
    self.assertEqual(names.count("vision.capture_frame"), 3)

  def test_live_detection_receives_captured_frame_and_spatial_constraint(self) -> None:
    runtime, tool_runtime, _ = _make_runtime(
      real_verify_in_bin=True,
      open_vocab_sequence=[
        _StubResult(True, _detection([0.24, 0.23, 0.142])),
        _StubResult(True, _detection([0.24, 0.23, 0.30])),
        _StubResult(True, _detection([0.36, -0.06, 0.30])),
      ],
    )

    runtime.run(_live_tree(), _live_request(), TraceContext())

    detect_input = next(
      input_data for name, input_data in tool_runtime.calls if name == "vision.open_vocab_detect"
    )
    self.assertTrue(str(detect_input["image_path"]).endswith("rgb.npy"))
    self.assertTrue(str(detect_input["depth_path"]).endswith("depth.npy"))
    self.assertEqual(detect_input["T_base_camera"], _T_BASE_CAMERA)
    self.assertEqual(detect_input["spatial_constraint"], {"relation": "left", "ordinal": 1})

  def test_live_detection_omits_missing_spatial_constraint(self) -> None:
    runtime, tool_runtime, _ = _make_runtime(
      real_verify_in_bin=True,
      open_vocab_sequence=[
        _StubResult(True, _detection([0.24, 0.23, 0.142])),
        _StubResult(True, _detection([0.36, -0.06, 0.30])),
      ],
    )

    request = {"object_query": "roller", "target": "bin_cell_3"}
    result = runtime.run(_live_tree(), request, TraceContext())

    self.assertTrue(result.success, msg=result.error)
    detect_input = next(
      input_data for name, input_data in tool_runtime.calls if name == "vision.open_vocab_detect"
    )
    self.assertNotIn("spatial_constraint", detect_input)

  def test_live_detection_omits_null_spatial_constraint(self) -> None:
    runtime, tool_runtime, _ = _make_runtime(
      real_verify_in_bin=True,
      open_vocab_sequence=[
        _StubResult(True, _detection([0.24, 0.23, 0.142])),
        _StubResult(True, _detection([0.36, -0.06, 0.30])),
      ],
    )

    request = {
      "object_query": "roller",
      "target": "bin_cell_3",
      "spatial_constraint": None,
    }
    result = runtime.run(_live_tree(), request, TraceContext())

    self.assertTrue(result.success, msg=result.error)
    detect_input = next(
      input_data for name, input_data in tool_runtime.calls if name == "vision.open_vocab_detect"
    )
    self.assertNotIn("spatial_constraint", detect_input)

  def test_terminal_failure_result_serializes_without_recursion(self) -> None:
    runtime, _tool_runtime, _ = _make_runtime(
      real_verify_in_bin=True,
      open_vocab_sequence=[
        _StubResult(False, error="DETECT_FAILED"),
        _StubResult(False, error="DETECT_FAILED"),
      ],
    )

    result = runtime.run(_live_tree(), _live_request(), TraceContext())

    self.assertFalse(result.success)
    serialized = asdict(result)
    self.assertEqual(serialized["nodes"][-1]["node"], "failure")
    self.assertNotEqual(
      serialized["output"].get("last_failure", {}).get("node"),
      "failure",
    )

  def test_wrong_bin_is_observed_from_re_detection_not_commanded_pose(self) -> None:
    # The object is detected away from bin_cell_3 after the first place, so the
    # real verify tool must report WRONG_BIN. A commanded-pose check could not.
    runtime, tool_runtime, _ = _make_runtime(
      real_verify_in_bin=True,
      open_vocab_sequence=[
        _StubResult(True, _detection([0.24, 0.23, 0.142])),
        _StubResult(True, _detection([0.24, 0.23, 0.30])),
        _StubResult(True, _detection([0.55, -0.30, 0.31])),
        _StubResult(True, _detection([0.36, -0.06, 0.30])),
      ],
    )

    result = runtime.run(_live_tree(), _live_request(), TraceContext())

    node_names = [node.node for node in result.nodes]
    self.assertIn("redetect_post_place", node_names)
    self.assertIn("recover_pick", node_names)
    self.assertEqual(result.output["classification"]["failure_type"], "WRONG_BIN")
    verify_inputs = [
      input_data for name, input_data in tool_runtime.calls if name == "vision.verify_object_in_bin"
    ]
    self.assertIn("object_pose", verify_inputs[0])
    self.assertNotIn("pose_3d", verify_inputs[0])
    # The verified position is the re-detected one, not the commanded release
    # pose (which would be the in-target [0.36, -0.06, 0.30]).
    self.assertEqual(verify_inputs[0]["object_pose"]["pose_3d"][:3], [0.55, -0.30, 0.31])
    self.assertIn(
      "WRONG_BIN",
      str(result.output["classification"]["evidence"]["error"]),
    )

  def test_default_tree_still_uses_commanded_pose(self) -> None:
    runtime, tool_runtime, _ = _make_runtime(real_verify_in_bin=True)

    result = runtime.run(
      build_industrial_recovery_pick_place_tree(),
      {"object_query": "roller", "target": "bin_cell_3"},
      TraceContext(),
    )

    self.assertTrue(result.success, msg=result.error)
    names = [call[0] for call in tool_runtime.calls]
    self.assertNotIn("vision.capture_frame", names)
    self.assertNotIn("vision.open_vocab_detect", names)
    verify_input = next(
      input_data for name, input_data in tool_runtime.calls if name == "vision.verify_object_in_bin"
    )
    self.assertIn("pose_3d", verify_input)


  def test_lift_verification_detects_a_dropped_object(self) -> None:
    # The object is re-detected still on the table after grasping, so the lift
    # check must fail and route through DROPPED_OBJECT recovery.
    runtime, tool_runtime, _ = _make_runtime(
      real_verify_in_bin=True,
      real_verify_lifted=True,
      open_vocab_sequence=[
        _StubResult(True, _detection([0.24, 0.23, 0.142])),
        # Still resting on the table after the grasp -> dropped.
        _StubResult(True, _detection([0.24, 0.23, 0.145])),
        # Recovery re-picks, then the post-place check sees the target cell.
        _StubResult(True, _detection([0.36, -0.06, 0.30])),
      ],
    )

    result = runtime.run(_live_tree(), _live_request(), TraceContext())

    node_names = [node.node for node in result.nodes]
    self.assertIn("verify_object_lifted", node_names)
    self.assertIn("recover_pick", node_names)
    self.assertEqual(
      result.output["classification"]["failure_type"],
      "DROPPED_OBJECT",
      msg=f"nodes={node_names}",
    )
    # The step name is what the detector keys DROPPED_OBJECT off, so pin it.
    self.assertEqual(
      result.output["classification"]["evidence"]["failed_step"],
      "verify_object_lifted",
    )
    self.assertEqual(result.output["classification"]["phase"], "transport")

  def test_lift_verification_passes_when_object_rises(self) -> None:
    runtime, tool_runtime, _ = _make_runtime(
      real_verify_in_bin=True,
      real_verify_lifted=True,
      open_vocab_sequence=[
        _StubResult(True, _detection([0.24, 0.23, 0.142])),
        _StubResult(True, _detection([0.24, 0.23, 0.30])),
        _StubResult(True, _detection([0.36, -0.06, 0.30])),
      ],
    )

    result = runtime.run(_live_tree(), _live_request(), TraceContext())

    self.assertTrue(result.success, msg=result.error)
    self.assertNotIn("recover_pick", [node.node for node in result.nodes])
    self.assertTrue(result.output["lift_check"]["lifted"])

  def test_occluded_object_after_grasp_does_not_block_transport(self) -> None:
    # A lifted object is often hidden by the gripper; absence is not a drop.
    runtime, tool_runtime, _ = _make_runtime(
      real_verify_in_bin=True,
      real_verify_lifted=True,
      open_vocab_sequence=[
        _StubResult(True, _detection([0.24, 0.23, 0.142])),
        _StubResult(False, None, "OBJECT_NOT_FOUND: no match for roller"),
        _StubResult(True, _detection([0.36, -0.06, 0.30])),
      ],
    )

    result = runtime.run(_live_tree(), _live_request(), TraceContext())

    self.assertTrue(result.success, msg=result.error)
    node_names = [node.node for node in result.nodes]
    self.assertIn("redetect_post_grasp", node_names)
    self.assertNotIn("verify_object_lifted", node_names)
    self.assertNotIn("recover_pick", node_names)

  def test_default_tree_has_no_lift_verification(self) -> None:
    runtime, tool_runtime, _ = _make_runtime(real_verify_in_bin=True)

    result = runtime.run(
      build_industrial_recovery_pick_place_tree(),
      {"object_query": "roller", "target": "bin_cell_3"},
      TraceContext(),
    )

    self.assertTrue(result.success, msg=result.error)
    self.assertNotIn("vision.verify_object_lifted", [call[0] for call in tool_runtime.calls])


  def test_live_tree_runs_without_a_spatial_constraint(self) -> None:
    # The sim config enables the constraint input unconditionally, but callers
    # usually omit it; an absent value must not break variable resolution.
    runtime, tool_runtime, _ = _make_runtime(
      real_verify_in_bin=True,
      open_vocab_sequence=[
        _StubResult(True, _detection([0.24, 0.23, 0.142])),
        _StubResult(True, _detection([0.24, 0.23, 0.30])),
        _StubResult(True, _detection([0.36, -0.06, 0.30])),
      ],
    )

    result = runtime.run(
      _live_tree(),
      {"object_query": "roller", "target": "bin_cell_3"},
      TraceContext(),
    )

    self.assertTrue(result.success, msg=result.error)
    detect_input = next(
      input_data for name, input_data in tool_runtime.calls if name == "vision.open_vocab_detect"
    )
    # Absent rather than null: tool contracts type the field as an object.
    self.assertNotIn("spatial_constraint", detect_input)


def _live_tree():
  return build_industrial_recovery_pick_place_tree(
    detect_tool="vision.open_vocab_detect",
    capture_tool="vision.capture_frame",
    live_verify=True,
    spatial_constraint_input=True,
  )


def _live_request() -> dict:
  return {
    "object_query": "roller",
    "target": "bin_cell_3",
    "spatial_constraint": {"relation": "left", "ordinal": 1},
  }


def _make_runtime(
  *,
  verify_grasp_sequence: list[_StubResult] | None = None,
  plan_place_sequence: list[_StubResult] | None = None,
  verify_bin_sequence: list[_StubResult] | None = None,
  open_vocab_sequence: list[_StubResult] | None = None,
  config_detect_sequence: list[_StubResult] | None = None,
  plan_pick_sequence: list[_StubResult] | None = None,
  verify_place_sequence: list[_StubResult] | None = None,
  move_joints_sequence: list[_StubResult] | None = None,
  real_verify_in_bin: bool = False,
  real_verify_lifted: bool = False,
):
  verify_grasp_results = _sequence(
    verify_grasp_sequence or [_StubResult(True, {"held": True, "opening": 0.03})]
  )
  plan_place_results = _sequence(plan_place_sequence or [_StubResult(True, _place_plan())])
  verify_bin_results = _sequence(verify_bin_sequence or [_StubResult(True, _bin_check(True))])
  open_vocab_results = _sequence(open_vocab_sequence or [_StubResult(True, _detection())])
  config_detect_results = _sequence(
    config_detect_sequence or [_StubResult(True, _config_detection())]
  )
  plan_pick_results = _sequence(
    plan_pick_sequence or [_StubResult(True, _pick_plan())]
  )
  verify_place_results = _sequence(
    verify_place_sequence or [_StubResult(True, {"released": True, "opening": 0.0848})]
  )
  move_joints_results = _sequence(
    move_joints_sequence or [_StubResult(True, {"completed": True, "state": {}})]
  )

  classify_tool = RecoveryClassifyFailureTool()
  plan_tool = RecoveryPlanTool()

  def classify(input_data):
    result = classify_tool.run(_tool_call("recovery.classify_failure", input_data))
    return _from_tool_result(result)

  def plan_recovery(input_data):
    result = plan_tool.run(_tool_call("recovery.plan", input_data))
    return _from_tool_result(result)

  verify_in_bin_tool = VisionVerifyObjectInBinTool(_PLACE_TARGETS)
  verify_lifted_tool = VisionVerifyObjectLiftedTool()

  def verify_in_bin(input_data):
    """Run the real geometric check so live tests exercise the observation path."""

    result = verify_in_bin_tool.run(_tool_call("vision.verify_object_in_bin", input_data))
    return _from_tool_result(result)

  def verify_lifted(input_data):
    result = verify_lifted_tool.run(_tool_call("vision.verify_object_lifted", input_data))
    return _from_tool_result(result)

  tool_runtime = _StubRuntime({
    "vision.config_detect": lambda _i: next(config_detect_results),
    "vision.capture_frame": lambda input_data: {
      "image_path": f"{input_data.get('out_dir', 'logs/frame')}/rgb.npy",
      "depth_path": f"{input_data.get('out_dir', 'logs/frame')}/depth.npy",
      "camera_info_path": f"{input_data.get('out_dir', 'logs/frame')}/camera_info.json",
      "T_base_camera": _T_BASE_CAMERA,
      "T_world_camera": None,
    },
    "vision.open_vocab_detect": lambda _i: next(open_vocab_results),
    "robot.plan_top_down_pick": lambda _i: next(plan_pick_results),
    "robot.resolve_place_target": lambda input_data: {
      "target": input_data["target"],
      "place_pose": {
        "position": [0.36, -0.06, 0.30],
        "orientation": [0.9962, -0.0872, 0.0, 0.0],
        "frame_id": "base_link",
      },
    },
    "robot.plan_place": lambda _i: next(plan_place_results),
    "robot.move_joints": lambda _i: next(move_joints_results),
    "robot.move_pose": lambda _i: {"completed": True, "state": {}},
    "robot.move_linear": lambda _i: {"completed": True, "state": {}},
    "gripper.open": lambda _i: {"completed": True, "state": {"opening": 0.0848}},
    "vision.verify_object_in_bin": (
      verify_in_bin if real_verify_in_bin else lambda _i: next(verify_bin_results)
    ),
    "vision.verify_object_lifted": (
      verify_lifted if real_verify_lifted else lambda _i: {"lifted": True}
    ),
    "recovery.classify_failure": classify,
    "recovery.plan": plan_recovery,
    "robot.stop": lambda _i: {"completed": True, "state": {}},
  })
  skill_runtime = _StubRuntime({
    "robot.pick": lambda _i: {"picked": True},
    "robot.verify_grasp": lambda _i: next(verify_grasp_results),
    "robot.verify_place": lambda _i: next(verify_place_results),
  })
  actionlists = {
    "industrial.pick_only_actionlist": build_industrial_pick_only_actionlist(),
    "industrial.place_only_actionlist": build_industrial_place_only_actionlist(),
  }
  actionlist_runtime = ActionListRuntime(tool_runtime, skill_runtime, _NullLogger())
  runtime = DecisionTreeRuntime(
    tool_runtime,
    skill_runtime,
    actionlist_runtime,
    actionlists,
    _NullLogger(),
  )
  return runtime, tool_runtime, skill_runtime


def _place_plan() -> dict:
  return {
    "plan": {
      "approach": {
        "position": [0.36, -0.06, 0.45],
        "orientation": [0.9962, -0.0872, 0.0, 0.0],
        "frame_id": "base_link",
      },
      "place": {
        "position": [0.36, -0.06, 0.30],
        "orientation": [0.9962, -0.0872, 0.0, 0.0],
        "frame_id": "base_link",
      },
      "retreat": {
        "position": [0.36, -0.06, 0.45],
        "orientation": [0.9962, -0.0872, 0.0, 0.0],
        "frame_id": "base_link",
      },
    }
  }


def _pick_plan() -> dict:
  return {"plan": {"approach": {}, "pregrasp": {}, "grasp": {}, "lift": {}}}


def _config_detection(position: list[float] | None = None) -> dict:
  pose = list(position or [0.24, 0.23, 0.142])
  return {
    "found": True,
    "label": "roller",
    "confidence": 1.0,
    "object_id": "roller",
    "pose_3d": [*pose[:3], 0.0, 0.0, 0.0],
  }


def _bin_check(success: bool) -> dict:
  return {
    "target": "bin_cell_3",
    "in_target": success,
    "object_position": [0.36, -0.06, 0.30],
    "target_position": [0.36, -0.06, 0.30],
    "distance_xy": 0.0,
  }


_T_BASE_CAMERA = [
  [0.0, -1.0, 0.0, 0.34],
  [-1.0, 0.0, 0.0, 0.0],
  [0.0, 0.0, -1.0, 0.88],
  [0.0, 0.0, 0.0, 1.0],
]

# Same cell the stub robot.resolve_place_target hands back, so the real
# verify_object_in_bin tool can compare a detection against it.
_PLACE_TARGETS = {
  "bin_cell_3": {
    "position": [0.36, -0.06, 0.30],
    "orientation": [0.9962, -0.0872, 0.0, 0.0],
    "frame_id": "base_link",
  }
}


def _detection(position: list[float] | None = None) -> dict:
  pose = list(position or [0.24, 0.23, 0.142])
  return {
    "found": True,
    "label": "roller",
    "confidence": 0.91,
    "object_id": "roller",
    "pose_3d": [*pose[:3], 0.0, 0.0, 0.0],
  }


def _tool_call(tool: str, input_data: dict):
  from sensoragent.schemas import ToolCall

  return ToolCall(tool=tool, input=input_data, trace=TraceContext())


def _from_tool_result(result) -> _StubResult:
  return _StubResult(result.success, result.output, result.error)


def _sequence(values: list[_StubResult]):
  index = 0
  while True:
    if index < len(values):
      value = values[index]
      index += 1
    else:
      value = values[-1]
    yield value
