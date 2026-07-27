"""Named joint-space poses for RM65-B workflow configuration."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


RM65_B_JOINT_ORDER = ("joint1", "joint2", "joint3", "joint4", "joint5", "joint6")

DEFAULT_HOME_JOINTS = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]

# Existing manually verified pre-place posture. Keep this as the default until
# a tuned value is recorded in configs/* under scene.joint_poses.
DEFAULT_PLACE_STAGING_JOINTS = [-0.17, -0.57, -0.61, 0.0, -1.96, 0.0]


def normalize_joint_pose(name: str, value: Sequence[Any]) -> list[float]:
  """Validate and normalize one six-DOF RM65-B joint pose."""

  if not isinstance(value, (list, tuple)) or len(value) != len(RM65_B_JOINT_ORDER):
    raise ValueError(
      f"{name} must contain {len(RM65_B_JOINT_ORDER)} joint values in "
      f"{list(RM65_B_JOINT_ORDER)} order"
    )
  if not all(isinstance(item, (int, float)) and not isinstance(item, bool) for item in value):
    raise ValueError(f"{name} must contain only numeric joint values")
  return [float(item) for item in value]


def configured_joint_pose(
  joint_poses: Mapping[str, Any] | None,
  name: str,
  fallback: Sequence[Any],
) -> list[float]:
  """Return a configured named joint pose or a validated fallback."""

  value = (joint_poses or {}).get(name)
  if value is None:
    return normalize_joint_pose(name, fallback)
  return normalize_joint_pose(name, value)
