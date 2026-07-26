"""End-to-end test for the industrial pick-place ActionList."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from unittest import TestCase

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
  sys.path.insert(0, str(SRC))

from sensoragent.agent import LLMPlanner
from sensoragent.schemas import PlanTargetKind, TraceContext
from sensoragent.workflows.actionlists.industrial import build_industrial_pick_place_actionlist
from sensoragent.workflows.actionlists.runtime import ActionListRuntime


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
      return _StubResult(success=False, error=f"no stub for {name}")
    output = handler(input_data)
    if isinstance(output, _StubResult):
      return output
    return _StubResult(success=True, output=output)


class _NullLogger:
  def log(self, *args, **kwargs) -> None:
    return None


def _make_runtimes(*, opening_after_pick: float, opening_after_place: float):
  """Wire tool + skill runtimes with sequenced gripper.get_state responses."""

  gripper_states = iter([{"opening": opening_after_pick}, {"opening": opening_after_place}])

  def detect(_input):
    return {
      "found": True,
      "label": "roller",
      "confidence": 0.9,
      "object_id": "obj_1",
      "pose_3d": [0.30, 0.10, 0.05],
    }

  def plan_pick(_input):
    return {"plan": {"approach": {}, "pregrasp": {}, "grasp": {}, "lift": {}}}

  def resolve_target(input_data):
    return {
      "target": input_data["target"],
      "place_pose": {"position": [0.4, 0.2, 0.05], "orientation": [0, 1, 0, 0], "frame_id": "base_link"},
    }

  def plan_place(_input):
    return {
      "plan": {
        "approach": {"position": [0.36, -0.06, 0.35], "orientation": [0, 1, 0, 0], "frame_id": "base_link"},
        "place": {"position": [0.36, -0.06, 0.20], "orientation": [0, 1, 0, 0], "frame_id": "base_link"},
        "retreat": {"position": [0.36, -0.06, 0.35], "orientation": [0, 1, 0, 0], "frame_id": "base_link"},
      }
    }

  def move_joints(_input):
    return {"completed": True, "message": "", "state": {}}

  def move_pose(_input):
    return {"completed": True, "message": "", "state": {}}

  def move_linear(_input):
    return {"completed": True, "message": "", "state": {}}

  def gripper_open(_input):
    return {"completed": True, "message": "", "state": {"opening": 0.0848}}

  def gripper_state(_input):
    return {"completed": True, "message": "", "state": next(gripper_states)}

  tool_runtime = _StubRuntime({
    "vision.config_detect": detect,
    "robot.plan_top_down_pick": plan_pick,
    "robot.resolve_place_target": resolve_target,
    "robot.plan_place": plan_place,
    "gripper.get_state": gripper_state,
    "robot.move_joints": move_joints,
    "robot.move_pose": move_pose,
    "robot.move_linear": move_linear,
    "gripper.open": gripper_open,
  })

  def pick(_input):
    return {"picked": True, "completed_steps": ["open_gripper", "move_approach"]}

  def place(input_data):
    return {"placed": True, "target": input_data.get("target"), "completed_steps": ["move_approach"]}

  def verify_grasp(_input):
    # verify_grasp skill inspects gripper.get_state via tool_runtime;
    # here we call the real skill via SkillRuntime — but skills need SkillContext.
    # Instead, model verify_grasp as a passthrough skill in the stub.
    state = next(gripper_states)
    opening = state["opening"]
    held = 0.002 <= opening <= 0.08
    return _StubResult(
      success=held,
      output={"held": held, "opening": opening},
      error=None if held else f"grasp not detected (opening={opening:.4f})",
    )

  def verify_place(_input):
    state = next(gripper_states)
    opening = state["opening"]
    released = opening >= 0.05
    return _StubResult(
      success=released,
      output={"released": released, "opening": opening},
      error=None if released else f"place not confirmed (opening={opening:.4f})",
    )

  skill_runtime = _StubRuntime({
    "robot.pick": pick,
    "robot.place": place,
    "robot.verify_grasp": verify_grasp,
    "robot.verify_place": verify_place,
  })

  return tool_runtime, skill_runtime


class IndustrialActionListTest(TestCase):
  def _run(self, opening_after_pick: float, opening_after_place: float):
    tool_runtime, skill_runtime = _make_runtimes(
      opening_after_pick=opening_after_pick,
      opening_after_place=opening_after_place,
    )
    runtime = ActionListRuntime(tool_runtime, skill_runtime, _NullLogger())
    actionlist = build_industrial_pick_place_actionlist()
    return runtime.run(
      actionlist,
      {"object_query": "roller", "target": "bin_cell_3"},
      TraceContext(),
    ), tool_runtime, skill_runtime

  def test_happy_path_succeeds(self) -> None:
    result, tool_runtime, skill_runtime = self._run(0.02, 0.07)
    self.assertTrue(result.success, msg=result.error)
    step_names = [step.step for step in result.steps]
    self.assertEqual(
      step_names,
      [
        "detect_object",
        "plan_pick",
        "pick",
        "verify_grasp",
        "resolve_place_target",
        "plan_place",
        "place_pre_approach_joints",
        "place_move_place",
        "place_open_gripper",
        "place_lift_clearance",
        "place_retreat",
        "verify_place",
      ],
    )
    self.assertIn("robot.resolve_place_target", [call[0] for call in tool_runtime.calls])
    self.assertIn("robot.verify_grasp", [call[0] for call in skill_runtime.calls])
    self.assertIn("robot.verify_place", [call[0] for call in skill_runtime.calls])

  def test_grasp_failure_short_circuits(self) -> None:
    result, tool_runtime, skill_runtime = self._run(0.0, 0.07)
    self.assertFalse(result.success)
    self.assertEqual(result.steps[-1].step, "verify_grasp")
    self.assertNotIn("robot.plan_place", [call[0] for call in tool_runtime.calls])
    self.assertNotIn("robot.move_joints", [call[0] for call in tool_runtime.calls])


class LLMPlannerAllowedTargetsTest(TestCase):
  def test_planner_accepts_industrial_target(self) -> None:
    class _FakeClient:
      def complete_json(self, system_prompt: str, user_prompt: str) -> dict:
        return {
          "target_kind": "actionlist",
          "target": "industrial.pick_place_actionlist",
          "input": {"object_query": "滚柱", "target": "bin_cell_3"},
          "reason": "intent={...}",
        }

    planner = LLMPlanner(
      _FakeClient(),
      allowed_targets=("industrial.pick_place_actionlist", "mock.pick_place_actionlist"),
    )
    plan = planner.plan("把滚柱放到 bin_cell_3", {})
    self.assertEqual(plan.target, "industrial.pick_place_actionlist")
    self.assertEqual(plan.target_kind, PlanTargetKind.ACTIONLIST)
    self.assertEqual(plan.input["target"], "bin_cell_3")

  def test_planner_rejects_unlisted_target(self) -> None:
    class _FakeClient:
      def complete_json(self, system_prompt: str, user_prompt: str) -> dict:
        return {
          "target_kind": "actionlist",
          "target": "dangerous.workflow",
          "input": {},
          "reason": "",
        }

    planner = LLMPlanner(
      _FakeClient(),
      allowed_targets=("industrial.pick_place_actionlist",),
    )
    with self.assertRaises(ValueError):
      planner.plan("do something unsafe", {})


class IndustrialPickOnlyTest(TestCase):
  def test_pick_only_runs_four_steps(self) -> None:
    from sensoragent.workflows.actionlists.industrial import (
      build_industrial_pick_only_actionlist,
    )

    detect = lambda _i: {
      "found": True,
      "label": "roller",
      "confidence": 1.0,
      "object_id": "roller",
      "pose_3d": [0.24, 0.23, 0.142, 0.0, 0.0, 0.0],
    }
    plan_pick = lambda _i: {"plan": {"approach": {}, "pregrasp": {}, "grasp": {}, "lift": {}}}
    tool_runtime = _StubRuntime({
      "vision.config_detect": detect,
      "robot.plan_top_down_pick": plan_pick,
      "gripper.get_state": lambda _i: {
        "completed": True, "message": "", "state": {"opening": 0.03},
      },
    })
    pick = lambda _i: {"picked": True, "completed_steps": ["open_gripper"]}
    verify_grasp = lambda _i: _StubResult(
      success=True, output={"held": True, "opening": 0.03},
    )
    skill_runtime = _StubRuntime({
      "robot.pick": pick,
      "robot.verify_grasp": verify_grasp,
    })
    runtime = ActionListRuntime(tool_runtime, skill_runtime, _NullLogger())
    result = runtime.run(
      build_industrial_pick_only_actionlist(),
      {"object_query": "roller"},
      TraceContext(),
    )
    self.assertTrue(result.success, msg=result.error)
    self.assertEqual(
      [s.step for s in result.steps],
      ["detect_object", "plan_pick", "pick", "verify_grasp"],
    )
    self.assertNotIn("robot.resolve_place_target", [c[0] for c in tool_runtime.calls])
    self.assertNotIn("robot.verify_place", [c[0] for c in skill_runtime.calls])


class IndustrialPlaceOnlyTest(TestCase):
  def test_place_only_runs_clearance_lift_before_retreat(self) -> None:
    from sensoragent.workflows.actionlists.industrial import (
      build_industrial_place_only_actionlist,
    )

    resolve = lambda input_data: {
      "target": input_data["target"],
      "place_pose": {
        "position": [0.36, -0.06, 0.30],
        "orientation": [0.9962, -0.0872, 0.0, 0.0],
        "frame_id": "base_link",
      },
    }
    plan_place = lambda _i: {
      "plan": {
        "approach": {"position": [0.36, -0.06, 0.45], "orientation": [0.9962, -0.0872, 0.0, 0.0], "frame_id": "base_link"},
        "place":    {"position": [0.36, -0.06, 0.30], "orientation": [0.9962, -0.0872, 0.0, 0.0], "frame_id": "base_link"},
        "retreat":  {"position": [0.36, -0.06, 0.45], "orientation": [0.9962, -0.0872, 0.0, 0.0], "frame_id": "base_link"},
      }
    }
    tool_runtime = _StubRuntime({
      "robot.resolve_place_target": resolve,
      "robot.plan_place": plan_place,
      "robot.move_joints": lambda _i: {"completed": True, "message": "", "state": {}},
      "robot.move_pose":   lambda _i: {"completed": True, "message": "", "state": {}},
      "robot.move_linear": lambda _i: {"completed": True, "message": "", "state": {}},
      "gripper.open":      lambda _i: {"completed": True, "message": "", "state": {"opening": 0.08}},
      "gripper.get_state": lambda _i: {
        "completed": True, "message": "", "state": {"opening": 0.08},
      },
    })
    verify_place = lambda _i: _StubResult(
      success=True, output={"released": True, "opening": 0.08},
    )
    skill_runtime = _StubRuntime({"robot.verify_place": verify_place})
    runtime = ActionListRuntime(tool_runtime, skill_runtime, _NullLogger())
    result = runtime.run(
      build_industrial_place_only_actionlist(),
      {"target": "bin_cell_3"},
      TraceContext(),
    )
    self.assertTrue(result.success, msg=result.error)
    self.assertEqual(
      [s.step for s in result.steps],
      [
        "resolve_place_target",
        "plan_place",
        "place_pre_approach_joints",
        "place_move_place",
        "place_open_gripper",
        "place_lift_clearance",
        "place_retreat",
        "verify_place",
      ],
    )
    self.assertIn(
      ("robot.move_linear", {"pose": {"position": [0.36, -0.06, 0.45], "orientation": [0.9962, -0.0872, 0.0, 0.0], "frame_id": "base_link"}, "speed": 2.0, "wait": True}),
      tool_runtime.calls,
    )
    self.assertNotIn("vision.config_detect", [c[0] for c in tool_runtime.calls])
    self.assertNotIn("robot.verify_grasp", [c[0] for c in skill_runtime.calls])
