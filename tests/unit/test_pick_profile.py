"""Tests for configured hardware pick-profile selection."""

from __future__ import annotations

from sensoragent.schemas import ToolCall, TraceContext
from sensoragent.tools.robot.pick_profile import RobotSelectPickProfileTool


def test_short_bolt_profile_uses_verified_gripper_parameters() -> None:
  tool = RobotSelectPickProfileTool({
    "default": {"planner": "robot.plan_top_down_pick"},
    "short_bolt": {
      "planner": "robot.plan_short_bolt_pick", "gripper_force": 0.6,
      "gripper_speed": 0.4,
      "motion_speed": 0.35, "descent_speed": 0.25,
    },
  })

  result = tool.run(ToolCall(
    tool="robot.select_pick_profile", input={"label": "short_bolt"}, trace=TraceContext(),
  ))

  assert result.success
  assert result.output == {
    "name": "short_bolt", "planner": "robot.plan_short_bolt_pick",
    "orientation": [0.0, 1.0, 0.0, 0.0], "position_offset": [0.0, 0.0, 0.02],
    "approach_distance": 0.1, "pregrasp_distance": 0.04, "lift_height": 0.12,
    "lift_speed": 0.35, "open_opening": 0.12,
    "close_opening": 0.032, "gripper_force": 0.6, "gripper_speed": 0.4,
    "motion_speed": 0.35, "descent_speed": 0.25,
    "tcp_offset": [0.0, 0.0, 0.161], "headward_offset": 0.015,
    "camera_left_offset_px": 0.0, "camera_left_offset_m": 0.0,
    "minimum_safe_z": 0.14, "workspace_min": [-0.55, -0.18, 0.0],
    "workspace_max": [-0.20, 0.18, 0.35],
  }


def test_grounding_dino_label_normalizes_to_profile_name() -> None:
  tool = RobotSelectPickProfileTool({
    "default": {"planner": "robot.plan_top_down_pick", "gripper_force": 0.25},
    "short_bolt": {"planner": "robot.plan_short_bolt_pick", "gripper_force": 1.0},
  })

  result = tool.run(ToolCall(
    tool="robot.select_pick_profile", input={"label": "short bolt. [SEP]"}, trace=TraceContext(),
  ))

  assert result.success
  assert result.output["name"] == "short_bolt"
  assert result.output["planner"] == "robot.plan_short_bolt_pick"
  assert result.output["gripper_force"] == 1.0
