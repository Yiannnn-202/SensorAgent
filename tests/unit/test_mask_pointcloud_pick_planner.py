"""Tests for the experimental generic mask-and-point-cloud pick planner."""

from __future__ import annotations

import numpy as np

from sensoragent.schemas import ToolCall, TraceContext
from sensoragent.tools.robot.planning import RobotPlanMaskPointCloudPickTool


def _cloud(path) -> None:
  points = np.asarray(
    [
      [-0.42 + index * 0.004, (index % 5 - 2) * 0.002, 0.20, 100.0 + index, 100.0]
      for index in range(40)
    ],
    dtype=np.float32,
  )
  np.save(path, points)


def _mask() -> list[list[list[float]]]:
  return [[[-1.0, 90.0], [200.0, 90.0], [200.0, 110.0], [-1.0, 110.0]]]


def test_generic_planner_uses_mask_pca_center_plan(tmp_path) -> None:
  cloud_path = tmp_path / "cloud.npy"
  _cloud(cloud_path)

  result = RobotPlanMaskPointCloudPickTool().run(
    ToolCall(
      tool="robot.plan_mask_pointcloud_pick",
      input={
        "cloud_path": str(cloud_path),
        "mask_polygons": _mask(),
        "T_base_camera": np.eye(4).tolist(),
        "pose_3d": [-0.35, 0.0, 0.20],
        "tcp_offset": [0.0, 0.0, 0.131],
        "minimum_safe_z": 0.14,
        "workspace_min": [-0.55, -0.18, 0.0],
        "workspace_max": [-0.20, 0.18, 0.35],
      },
      trace=TraceContext(),
    )
  )

  assert result.success, result.error
  assert result.output["mode"] == "mask_pca_center"
  assert result.output["point_count"] == 40
  assert result.output["plan"]["grasp"]["position"][2] >= 0.14


def test_generic_planner_uses_top_down_when_base_transform_is_missing(tmp_path) -> None:
  cloud_path = tmp_path / "cloud.npy"
  _cloud(cloud_path)

  result = RobotPlanMaskPointCloudPickTool().run(
    ToolCall(
      tool="robot.plan_mask_pointcloud_pick",
      input={
        "cloud_path": str(cloud_path),
        "mask_polygons": _mask(),
        "pose_3d": [-0.35, 0.0, 0.20],
        "minimum_safe_z": 0.14,
        "workspace_min": [-0.55, -0.18, 0.0],
        "workspace_max": [-0.20, 0.18, 0.35],
      },
      trace=TraceContext(),
    )
  )

  assert result.success, result.error
  assert result.output["mode"] == "pose_fallback"
  assert result.output["fallback_reason"] == "MISSING_BASE_TRANSFORM"
