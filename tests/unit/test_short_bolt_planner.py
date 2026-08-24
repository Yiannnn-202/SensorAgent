"""Focused tests for the physical short-bolt planner."""

from __future__ import annotations

import numpy as np
import pytest

from sensoragent.schemas import ToolCall, TraceContext
from sensoragent.skills.robot.planning import build_yaw_aligned_pick_plan_from_points
from sensoragent.tools.robot.planning import RobotPlanShortBoltPickTool


def _cloud(path, z: float = 0.20) -> None:
  shaft = np.asarray([
    [-0.42 + index * 0.004, 0.00, z, 100.0 + index, 100.0]
    for index in range(35)
  ], dtype=np.float32)
  head = np.asarray([
    [-0.28 + index * 0.004, (index % 5 - 2) * 0.004, z, 135.0 + index, 100.0]
    for index in range(25)
  ], dtype=np.float32)
  np.save(path, np.concatenate([shaft, head], axis=0))


def test_short_bolt_planner_uses_mask_pca_and_tcp_offset(tmp_path) -> None:
  cloud_path = tmp_path / "cloud.npy"
  _cloud(cloud_path)
  result = RobotPlanShortBoltPickTool().run(ToolCall(
    tool="robot.plan_short_bolt_pick",
    input={
      "cloud_path": str(cloud_path),
      "mask_polygons": [[[-1.0, 90.0], [200.0, 90.0], [200.0, 110.0], [-1.0, 110.0]]],
      "pose_3d": [-0.35, 0.0, 0.20],
      "tcp_offset": [0.0, 0.0, 0.161],
      "headward_offset": 0.015,
      "minimum_safe_z": 0.0,
      "workspace_min": [-1.0, -1.0, -1.0],
      "workspace_max": [1.0, 1.0, 1.0],
    },
    trace=TraceContext(),
  ))

  assert result.success, result.error
  assert result.output["mode"] == "mask_pca"
  assert result.output["plan"]["grasp"]["position"][2] >= 0.14


def test_short_bolt_planner_can_lock_verified_orientation(tmp_path) -> None:
  cloud_path = tmp_path / "cloud.npy"
  _cloud(cloud_path)
  result = RobotPlanShortBoltPickTool().run(ToolCall(
    tool="robot.plan_short_bolt_pick",
    input={
      "cloud_path": str(cloud_path),
      "mask_polygons": [[[-1.0, 90.0], [200.0, 90.0], [200.0, 110.0], [-1.0, 110.0]]],
      "pose_3d": [-0.35, 0.0, 0.20],
      "orientation": [0.0, 1.0, 0.0, 0.0],
      "lock_orientation": True,
      "tcp_offset": [0.0, 0.0, 0.131],
      "headward_offset": 0.015,
      "minimum_safe_z": 0.0,
      "workspace_min": [-1.0, -1.0, -1.0],
      "workspace_max": [1.0, 1.0, 1.0],
    },
    trace=TraceContext(),
  ))

  assert result.success, result.error
  assert result.output["mode"] == "mask_point_fixed_orientation"
  assert result.output["plan"]["approach"]["orientation"] == [0.0, 1.0, 0.0, 0.0]


def test_centroid_mode_uses_a_fixed_top_down_grasp(tmp_path) -> None:
  cloud_path = tmp_path / "cloud.npy"
  _cloud(cloud_path)
  result = RobotPlanShortBoltPickTool().run(ToolCall(
    tool="robot.plan_short_bolt_pick",
    input={
      "cloud_path": str(cloud_path),
      "mask_polygons": [[[-1.0, 90.0], [200.0, 90.0], [200.0, 110.0], [-1.0, 110.0]]],
      "pose_3d": [-0.35, 0.0, 0.20],
      "grasp_point_mode": "centroid",
      "orientation": [0.0, 1.0, 0.0, 0.0],
      "lock_orientation": True,
      "tcp_offset": [0.0, 0.0, 0.131],
      "minimum_safe_z": 0.0,
      "workspace_min": [-1.0, -1.0, -1.0],
      "workspace_max": [1.0, 1.0, 1.0],
    },
    trace=TraceContext(),
  ))

  assert result.success, result.error
  assert result.output["mode"] == "mask_point_fixed_orientation"
  assert result.output["plan"]["grasp"]["orientation"] == [0.0, 1.0, 0.0, 0.0]


def test_short_bolt_planner_rejects_impossible_safe_workspace(tmp_path) -> None:
  cloud_path = tmp_path / "cloud.npy"
  _cloud(cloud_path, z=0.10)
  with pytest.raises(ValueError, match="SHORT_BOLT_WORKSPACE"):
    RobotPlanShortBoltPickTool().run(ToolCall(
      tool="robot.plan_short_bolt_pick",
      input={
        "cloud_path": str(cloud_path),
        "mask_polygons": [[[-1.0, 90.0], [200.0, 90.0], [200.0, 110.0], [-1.0, 110.0]]],
        "pose_3d": [-0.35, 0.0, 0.10],
        "minimum_safe_z": 0.14,
        "workspace_min": [-0.55, -0.18, 0.0],
        "workspace_max": [-0.20, 0.18, 0.13],
      },
      trace=TraceContext(),
    ))


def test_unlocked_short_bolt_rejects_missing_masked_cloud() -> None:
  with pytest.raises(ValueError, match="SHORT_BOLT_PCA_UNAVAILABLE"):
    RobotPlanShortBoltPickTool().run(ToolCall(
      tool="robot.plan_short_bolt_pick",
      input={
        "pose_3d": [-0.35, 0.0, 0.20],
        "lock_orientation": False,
      },
      trace=TraceContext(),
    ))


def test_locked_short_bolt_without_mask_applies_tcp_offset() -> None:
  result = RobotPlanShortBoltPickTool().run(ToolCall(
    tool="robot.plan_short_bolt_pick",
    input={
      "pose_3d": [-0.35, 0.0, 0.20],
      "orientation": [0.0, 1.0, 0.0, 0.0],
      "lock_orientation": True,
      "tcp_offset": [0.0, 0.0, 0.131],
      "minimum_safe_z": 0.0,
      "workspace_min": [-1.0, -1.0, -1.0],
      "workspace_max": [1.0, 1.0, 1.0],
    },
    trace=TraceContext(),
  ))

  assert result.success, result.error
  assert result.output["mode"] == "fixed_orientation_no_mask"
  assert result.output["plan"]["grasp"]["position"] == [-0.35, 0.0, 0.331]


def test_yaw_only_plan_preserves_calibrated_tool_tilt() -> None:
  points = np.asarray([
    [0.002 * (index % 3 - 1), -0.10 + index * 0.01, 0.20]
    for index in range(20)
  ])
  plan = build_yaw_aligned_pick_plan_from_points(
    points,
    orientation=(0.0, 1.0, 0.0, 0.0),
    grasp_point=(0.0, 0.0, 0.20),
  )
  x, y, z, w = plan.grasp.orientation
  rotation = np.array([
    [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
    [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
    [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
  ])

  assert np.allclose(rotation[:, 2], [0.0, 0.0, -1.0], atol=1e-6)
  assert abs(rotation[:, 0] @ np.array([0.0, 1.0, 0.0])) > 0.99
