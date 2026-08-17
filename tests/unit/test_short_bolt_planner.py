"""Focused tests for the physical short-bolt planner."""

from __future__ import annotations

import numpy as np
import pytest

from sensoragent.schemas import ToolCall, TraceContext
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
