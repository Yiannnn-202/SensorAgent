"""Tests for the industrial failure-recovery DecisionTree."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from unittest import TestCase

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
  sys.path.insert(0, str(SRC))

from sensoragent.schemas import TraceContext
from sensoragent.tools.recovery import RecoveryClassifyFailureTool, RecoveryPlanTool
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


def _make_runtime(
  *,
  verify_grasp_sequence: list[_StubResult] | None = None,
  plan_place_sequence: list[_StubResult] | None = None,
  verify_bin_sequence: list[_StubResult] | None = None,
):
  verify_grasp_results = _sequence(
    verify_grasp_sequence or [_StubResult(True, {"held": True, "opening": 0.03})]
  )
  plan_place_results = _sequence(plan_place_sequence or [_StubResult(True, _place_plan())])
  verify_bin_results = _sequence(verify_bin_sequence or [_StubResult(True, _bin_check(True))])

  classify_tool = RecoveryClassifyFailureTool()
  plan_tool = RecoveryPlanTool()

  def classify(input_data):
    result = classify_tool.run(_tool_call("recovery.classify_failure", input_data))
    return _from_tool_result(result)

  def plan_recovery(input_data):
    result = plan_tool.run(_tool_call("recovery.plan", input_data))
    return _from_tool_result(result)

  tool_runtime = _StubRuntime({
    "vision.config_detect": lambda _i: {
      "found": True,
      "label": "roller",
      "confidence": 1.0,
      "object_id": "roller",
      "pose_3d": [0.24, 0.23, 0.142, 0.0, 0.0, 0.0],
    },
    "robot.plan_top_down_pick": lambda _i: {
      "plan": {"approach": {}, "pregrasp": {}, "grasp": {}, "lift": {}}
    },
    "robot.resolve_place_target": lambda input_data: {
      "target": input_data["target"],
      "place_pose": {
        "position": [0.36, -0.06, 0.30],
        "orientation": [0.9962, -0.0872, 0.0, 0.0],
        "frame_id": "base_link",
      },
    },
    "robot.plan_place": lambda _i: next(plan_place_results),
    "robot.move_joints": lambda _i: {"completed": True, "state": {}},
    "robot.move_pose": lambda _i: {"completed": True, "state": {}},
    "robot.move_linear": lambda _i: {"completed": True, "state": {}},
    "gripper.open": lambda _i: {"completed": True, "state": {"opening": 0.0848}},
    "vision.verify_object_in_bin": lambda _i: next(verify_bin_results),
    "recovery.classify_failure": classify,
    "recovery.plan": plan_recovery,
    "robot.stop": lambda _i: {"completed": True, "state": {}},
  })
  skill_runtime = _StubRuntime({
    "robot.pick": lambda _i: {"picked": True},
    "robot.verify_grasp": lambda _i: next(verify_grasp_results),
    "robot.verify_place": lambda _i: {"released": True, "opening": 0.0848},
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


def _bin_check(success: bool) -> dict:
  return {
    "target": "bin_cell_3",
    "in_target": success,
    "object_position": [0.36, -0.06, 0.30],
    "target_position": [0.36, -0.06, 0.30],
    "distance_xy": 0.0,
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
