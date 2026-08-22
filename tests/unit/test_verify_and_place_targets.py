"""Tests for verify skills and resolve_place_target tool."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from unittest import TestCase

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
  sys.path.insert(0, str(SRC))

from sensoragent.schemas import SkillCall, ToolCall, ToolResult, TraceContext
from sensoragent.skills.base import SkillContext
from sensoragent.skills.robot.verify import RobotVerifyGraspSkill, RobotVerifyPlaceSkill
from sensoragent.tools.robot.place_targets import (
  RobotResolvePlaceTargetTool,
  default_place_target_registry,
)


@dataclass
class _StubToolResult:
  success: bool
  output: dict | None = None
  error: str | None = None


class _StubToolRuntime:
  def __init__(
    self,
    opening: float | None,
    success: bool = True,
    error: str | None = None,
    grasped: bool | None = None,
  ) -> None:
    self._opening = opening
    self._success = success
    self._error = error
    self._grasped = grasped
    self.calls: list[str] = []

  def invoke(self, tool_name: str, input_data: dict, trace: TraceContext) -> _StubToolResult:
    self.calls.append(tool_name)
    if not self._success:
      return _StubToolResult(success=False, output=None, error=self._error)
    state: dict = {}
    if self._opening is not None:
      state["opening"] = self._opening
    if self._grasped is not None:
      state["grasped"] = self._grasped
    return _StubToolResult(success=True, output={"state": state, "completed": True, "message": ""})


class _NullLogger:
  def log(self, *args, **kwargs) -> None:
    return None


def _skill_context(
  opening: float | None,
  success: bool = True,
  error: str | None = None,
  grasped: bool | None = None,
) -> tuple[SkillContext, _StubToolRuntime]:
  runtime = _StubToolRuntime(opening=opening, success=success, error=error, grasped=grasped)
  return SkillContext(tool_runtime=runtime, logger=_NullLogger()), runtime


def _skill_call(name: str, inp: dict | None = None) -> SkillCall:
  return SkillCall(skill=name, input=inp or {}, trace=TraceContext())


class VerifyGraspSkillTest(TestCase):
  def test_grasp_success_when_opening_in_range(self) -> None:
    context, runtime = _skill_context(opening=0.03)
    result = RobotVerifyGraspSkill().run(_skill_call("robot.verify_grasp"), context)
    self.assertTrue(result.success)
    self.assertEqual(runtime.calls, ["gripper.get_state"])
    self.assertTrue(result.output["held"])

  def test_grasp_failure_when_fully_closed(self) -> None:
    context, _ = _skill_context(opening=0.0)
    result = RobotVerifyGraspSkill().run(_skill_call("robot.verify_grasp"), context)
    self.assertFalse(result.success)
    self.assertIn("grasp not detected", result.error)

  def test_grasp_failure_when_fully_open(self) -> None:
    context, _ = _skill_context(opening=0.085)
    result = RobotVerifyGraspSkill().run(_skill_call("robot.verify_grasp"), context)
    self.assertFalse(result.success)

  def test_grasp_failure_when_gripper_tool_fails(self) -> None:
    context, _ = _skill_context(opening=None, success=False, error="GRIPPER_UNAVAILABLE")
    result = RobotVerifyGraspSkill().run(_skill_call("robot.verify_grasp"), context)
    self.assertFalse(result.success)
    self.assertEqual(result.error, "GRIPPER_UNAVAILABLE")

  def test_grasp_failure_when_bridge_reports_no_contact_despite_in_range_opening(self) -> None:
    # A gripper that closed on nothing still ends at its narrow target opening;
    # the physics-level grasped=False must win over the opening heuristic.
    context, _ = _skill_context(opening=0.0197, grasped=False)
    result = RobotVerifyGraspSkill().run(_skill_call("robot.verify_grasp"), context)
    self.assertFalse(result.success)
    self.assertFalse(result.output["held"])
    self.assertIn("grasped=False", result.error)

  def test_grasp_success_when_bridge_reports_contact(self) -> None:
    context, _ = _skill_context(opening=0.0197, grasped=True)
    result = RobotVerifyGraspSkill().run(_skill_call("robot.verify_grasp"), context)
    self.assertTrue(result.success)
    self.assertTrue(result.output["held"])


class VerifyPlaceSkillTest(TestCase):
  def test_place_success_when_gripper_open(self) -> None:
    context, _ = _skill_context(opening=0.07)
    result = RobotVerifyPlaceSkill().run(_skill_call("robot.verify_place"), context)
    self.assertTrue(result.success)
    self.assertTrue(result.output["released"])

  def test_place_failure_when_still_grasping(self) -> None:
    context, _ = _skill_context(opening=0.01)
    result = RobotVerifyPlaceSkill().run(_skill_call("robot.verify_place"), context)
    self.assertFalse(result.success)
    self.assertIn("place not confirmed", result.error)


class ResolvePlaceTargetToolTest(TestCase):
  def test_known_target_returns_place_pose(self) -> None:
    tool = RobotResolvePlaceTargetTool(default_place_target_registry())
    result = tool.run(ToolCall(tool="robot.resolve_place_target", input={"target": "bin_cell_3"}, trace=TraceContext()))
    self.assertTrue(result.success)
    self.assertEqual(result.output["target"], "bin_cell_3")
    pose = result.output["place_pose"]
    self.assertEqual(len(pose["position"]), 3)
    self.assertEqual(len(pose["orientation"]), 4)

  def test_unknown_target_reports_error(self) -> None:
    tool = RobotResolvePlaceTargetTool(default_place_target_registry())
    result = tool.run(ToolCall(tool="robot.resolve_place_target", input={"target": "missing_cell"}, trace=TraceContext()))
    self.assertFalse(result.success)
    self.assertIn("unknown place target", result.error)

  def test_missing_target_reports_error(self) -> None:
    tool = RobotResolvePlaceTargetTool(default_place_target_registry())
    result = tool.run(ToolCall(tool="robot.resolve_place_target", input={}, trace=TraceContext()))
    self.assertFalse(result.success)
    self.assertIn("non-empty string", result.error)
