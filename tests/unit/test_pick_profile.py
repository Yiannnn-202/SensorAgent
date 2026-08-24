"""Tests for configured hardware pick-profile selection."""

from __future__ import annotations

from sensoragent.schemas import ToolCall, TraceContext
from sensoragent.tools.robot.pick_profile import RobotSelectPickProfileTool


def test_short_bolt_profile_uses_verified_gripper_parameters() -> None:
  tool = RobotSelectPickProfileTool({
    "default": {"planner": "robot.plan_top_down_pick"},
    "short_bolt": {
      "planner": "robot.plan_short_bolt_pick", "open_min_opening": 0.105,
      "lock_orientation": True,
      "gripper_force": 0.6,
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
    "lift_speed": 0.35,
    "open_opening": 0.12, "open_min_opening": 0.105,
    "close_opening": 0.032, "max_grasp_opening": 0.08,
    "gripper_force": 0.6, "gripper_speed": 0.4,
    "require_grasp_confirmation": False,
    "motion_speed": 0.35, "descent_speed": 0.25,
    "tcp_offset": [0.0, 0.0, 0.161], "grasp_point_mode": "shaft", "headward_offset": 0.015,
    "camera_left_offset_px": 0.0, "camera_left_offset_m": 0.0,
    "minimum_safe_z": 0.14, "lock_orientation": True,
    "orientation_mode": "full_pca",
    "workspace_min": [-0.55, -0.18, 0.0],
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


def test_bolt_label_uses_short_bolt_profile() -> None:
  tool = RobotSelectPickProfileTool({
    "default": {"planner": "robot.plan_top_down_pick"},
    "short_bolt": {"planner": "robot.plan_short_bolt_pick"},
  })

  result = tool.run(ToolCall(
    tool="robot.select_pick_profile", input={"label": "bolt. [SEP]"}, trace=TraceContext(),
  ))

  assert result.success
  assert result.output["name"] == "short_bolt"
  assert result.output["planner"] == "robot.plan_short_bolt_pick"


def test_yolo_seg_labels_select_roller_and_hex_nut_profiles() -> None:
  tool = RobotSelectPickProfileTool({
    "default": {"planner": "robot.plan_top_down_pick"},
    "roller": {"planner": "robot.plan_short_bolt_pick", "grasp_point_mode": "centroid"},
    "hex_nut": {"planner": "robot.plan_short_bolt_pick", "grasp_point_mode": "centroid", "lock_orientation": True},
  })

  roller = tool.run(ToolCall(
    tool="robot.select_pick_profile", input={"label": "roller"}, trace=TraceContext(),
  ))
  nut = tool.run(ToolCall(
    tool="robot.select_pick_profile", input={"label": "hex nut"}, trace=TraceContext(),
  ))

  assert roller.success
  assert roller.output["name"] == "roller"
  assert roller.output["grasp_point_mode"] == "centroid"
  assert not roller.output["lock_orientation"]
  assert nut.success
  assert nut.output["name"] == "hex_nut"
  assert nut.output["grasp_point_mode"] == "centroid"
  assert nut.output["lock_orientation"]


def test_disabled_profile_refuses_an_uncalibrated_object() -> None:
  tool = RobotSelectPickProfileTool({"roller": {"enabled": False}})

  result = tool.run(ToolCall(
    tool="robot.select_pick_profile", input={"label": "roller"}, trace=TraceContext(),
  ))

  assert not result.success
  assert result.error == "PICK_PROFILE_DISABLED: roller requires physical calibration"
