"""Simple deterministic grasp and place planning helpers.

The oriented point-cloud planner is adapted from the dropped
``robocup_geca_arm`` grasp package, but rewritten to use SensorAgent's
backend-neutral schemas instead of ROS message types.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np

from sensoragent.schemas.robot import PickPlan, PlacePlan, RobotPose


DEFAULT_TOP_DOWN_ORIENTATION = (0.0, 1.0, 0.0, 0.0)


@dataclass(frozen=True)
class ObjectGeometry:
  """Estimated object geometry in the robot base frame."""

  center: tuple[float, float, float]
  principal_axis: tuple[float, float, float]
  secondary_axis: tuple[float, float, float]
  dimensions: tuple[float, float, float]
  points: tuple[tuple[float, float, float], ...]


def _as_points(points: Iterable[Iterable[float]]) -> np.ndarray:
  array = np.asarray(list(points), dtype=np.float64)
  if array.ndim != 2 or array.shape[1] != 3:
    raise ValueError("points must be an Nx3 numeric array")
  if len(array) == 0:
    raise ValueError("points must not be empty")
  return array


def _normalize(vector: np.ndarray) -> np.ndarray:
  norm = np.linalg.norm(vector)
  if norm < 1e-9:
    raise ValueError("cannot normalize a near-zero vector")
  return vector / norm


def _matrix_to_quaternion(matrix: np.ndarray) -> tuple[float, float, float, float]:
  """Convert a 3x3 rotation matrix to an xyzw quaternion."""

  trace = float(np.trace(matrix))
  if trace > 0.0:
    scale = np.sqrt(trace + 1.0) * 2.0
    w = 0.25 * scale
    x = (matrix[2, 1] - matrix[1, 2]) / scale
    y = (matrix[0, 2] - matrix[2, 0]) / scale
    z = (matrix[1, 0] - matrix[0, 1]) / scale
  else:
    diagonal = np.diag(matrix)
    index = int(np.argmax(diagonal))
    if index == 0:
      scale = np.sqrt(1.0 + matrix[0, 0] - matrix[1, 1] - matrix[2, 2]) * 2.0
      w = (matrix[2, 1] - matrix[1, 2]) / scale
      x = 0.25 * scale
      y = (matrix[0, 1] + matrix[1, 0]) / scale
      z = (matrix[0, 2] + matrix[2, 0]) / scale
    elif index == 1:
      scale = np.sqrt(1.0 + matrix[1, 1] - matrix[0, 0] - matrix[2, 2]) * 2.0
      w = (matrix[0, 2] - matrix[2, 0]) / scale
      x = (matrix[0, 1] + matrix[1, 0]) / scale
      y = 0.25 * scale
      z = (matrix[1, 2] + matrix[2, 1]) / scale
    else:
      scale = np.sqrt(1.0 + matrix[2, 2] - matrix[0, 0] - matrix[1, 1]) * 2.0
      w = (matrix[1, 0] - matrix[0, 1]) / scale
      x = (matrix[0, 2] + matrix[2, 0]) / scale
      y = (matrix[1, 2] + matrix[2, 1]) / scale
      z = 0.25 * scale
  quat = np.asarray([x, y, z, w], dtype=np.float64)
  quat = quat / np.linalg.norm(quat)
  return tuple(float(value) for value in quat)


def _quaternion_to_matrix(quaternion: tuple[float, float, float, float]) -> np.ndarray:
  x, y, z, w = (float(value) for value in quaternion)
  norm = (x * x + y * y + z * z + w * w) ** 0.5
  if norm < 1e-9:
    raise ValueError("orientation quaternion must not be zero")
  x, y, z, w = x / norm, y / norm, z / norm, w / norm
  return np.array([
    [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
    [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
    [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
  ], dtype=np.float64)


def build_fixed_orientation_pick_plan_from_contact(
  contact_point: Iterable[float],
  *,
  orientation: tuple[float, float, float, float] = DEFAULT_TOP_DOWN_ORIENTATION,
  frame_id: str = "base_link",
  approach_distance: float = 0.10,
  pregrasp_distance: float = 0.03,
  lift_height: float = 0.10,
  tcp_offset: tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> PickPlan:
  contact = np.asarray(tuple(float(value) for value in contact_point), dtype=np.float64)
  rotation = _quaternion_to_matrix(orientation)
  link6_grasp = contact - rotation @ np.asarray(tcp_offset, dtype=np.float64)

  def make_pose(position: np.ndarray) -> RobotPose:
    return RobotPose(
      position=tuple(float(value) for value in position),
      orientation=orientation,
      frame_id=frame_id,
    )

  return PickPlan(
    approach=make_pose(link6_grasp + np.array([0.0, 0.0, approach_distance])),
    pregrasp=make_pose(link6_grasp + np.array([0.0, 0.0, pregrasp_distance])),
    grasp=make_pose(link6_grasp),
    lift=make_pose(link6_grasp + np.array([0.0, 0.0, lift_height])),
  )


def estimate_object_geometry(points: Iterable[Iterable[float]]) -> ObjectGeometry:
  """Estimate object center, axes, and dimensions from base-frame points."""

  point_array = _as_points(points)
  center = np.mean(point_array, axis=0)
  centered = point_array - center
  covariance = np.cov(centered.T)
  eigenvalues, eigenvectors = np.linalg.eigh(covariance)
  order = np.argsort(eigenvalues)[::-1]
  eigenvalues = eigenvalues[order]
  eigenvectors = eigenvectors[:, order]

  return ObjectGeometry(
    center=tuple(float(value) for value in center),
    principal_axis=tuple(float(value) for value in _normalize(eigenvectors[:, 0])),
    secondary_axis=tuple(float(value) for value in _normalize(eigenvectors[:, 1])),
    dimensions=tuple(float(np.sqrt(max(value, 0.0))) for value in eigenvalues),
    points=tuple(tuple(float(item) for item in point) for point in point_array),
  )


def _find_handle_center(points: np.ndarray, axis: np.ndarray) -> np.ndarray:
  """Pick the thicker half along the principal axis as the grasp region."""

  projection = points @ axis
  median = np.median(projection)
  mask_positive = projection >= median
  mask_negative = projection < median
  if mask_positive.sum() < 10 or mask_negative.sum() < 10:
    return np.mean(points, axis=0)

  def mean_radius(region: np.ndarray) -> float:
    center = np.mean(region, axis=0)
    centered = region - center
    perpendicular = centered - (centered @ axis)[:, None] * axis
    return float(np.mean(np.linalg.norm(perpendicular, axis=1)))

  positive = points[mask_positive]
  negative = points[mask_negative]
  handle_points = positive if mean_radius(positive) >= mean_radius(negative) else negative
  return np.mean(handle_points, axis=0)


def estimate_shaft_grasp_point(
  points: Iterable[Iterable[float]],
  *,
  headward_offset: float = 0.015,
) -> tuple[float, float, float]:
  """Estimate a shaft grasp point shifted toward the thicker bolt head."""

  point_array = _as_points(points)
  geometry = estimate_object_geometry(point_array)
  axis = _normalize(np.asarray(geometry.principal_axis, dtype=np.float64))
  projection = point_array @ axis
  median = np.median(projection)
  positive = point_array[projection >= median]
  negative = point_array[projection < median]
  if len(positive) < 10 or len(negative) < 10:
    center = np.mean(point_array, axis=0)
    return tuple(float(value) for value in center)

  def mean_radius(region: np.ndarray) -> float:
    center = np.mean(region, axis=0)
    centered = region - center
    perpendicular = centered - (centered @ axis)[:, None] * axis
    return float(np.mean(np.linalg.norm(perpendicular, axis=1)))

  head_is_positive = mean_radius(positive) >= mean_radius(negative)
  shaft = negative if head_is_positive else positive
  shaft_center = np.mean(shaft, axis=0)
  head_direction = axis if head_is_positive else -axis
  grasp = shaft_center + float(headward_offset) * head_direction
  return tuple(float(value) for value in grasp)


def build_oriented_pick_plan_from_points(
  points: Iterable[Iterable[float]],
  *,
  frame_id: str = "base_link",
  approach_distance: float = 0.10,
  pregrasp_distance: float = 0.03,
  lift_height: float = 0.10,
  tcp_offset: tuple[float, float, float] = (0.0, 0.0, 0.0),
  grasp_point: tuple[float, float, float] | None = None,
) -> PickPlan:
  """Build an oriented pick plan from object point-cloud samples.

  The planner estimates the object long axis with PCA, chooses the thicker half
  as the grasp region, constructs a gripper frame, and offsets approach,
  pregrasp, grasp, and lift waypoints. It is intended for simple elongated
  industrial parts and tools; complex objects still need class-specific grasping.
  """

  point_array = _as_points(points)
  geometry = estimate_object_geometry(point_array)
  axis = _normalize(np.asarray(geometry.principal_axis, dtype=np.float64))
  handle_center = (
    np.asarray(grasp_point, dtype=np.float64)
    if grasp_point is not None
    else _find_handle_center(point_array, axis)
  )

  world_up = np.array([0.0, 0.0, 1.0], dtype=np.float64)
  tool_y = axis
  up_perpendicular = world_up - (world_up @ tool_y) * tool_y
  if np.linalg.norm(up_perpendicular) < 1e-6:
    reference = np.array([1.0, 0.0, 0.0], dtype=np.float64)
    up_perpendicular = reference - (reference @ tool_y) * tool_y
  tool_z = _normalize(-up_perpendicular)
  tool_x = _normalize(np.cross(tool_y, tool_z))
  tool_z = _normalize(np.cross(tool_x, tool_y))
  rotation = np.column_stack([tool_x, tool_y, tool_z])

  # Match the sample repository's convention: rotate around the approach axis
  # so the gripper closing direction is consistent for our RM65-B setup.
  rotate_z_minus_90 = np.array(
    [
      [0.0, 1.0, 0.0],
      [-1.0, 0.0, 0.0],
      [0.0, 0.0, 1.0],
    ],
    dtype=np.float64,
  )
  rotation = rotation @ rotate_z_minus_90
  orientation = _matrix_to_quaternion(rotation)
  link6_offset = rotation @ np.asarray(tcp_offset, dtype=np.float64)

  def make_pose(position: np.ndarray) -> RobotPose:
    link6_position = position - link6_offset
    return RobotPose(
      position=tuple(float(value) for value in link6_position),
      orientation=orientation,
      frame_id=frame_id,
    )

  return PickPlan(
    approach=make_pose(handle_center - approach_distance * tool_z),
    pregrasp=make_pose(handle_center - pregrasp_distance * tool_z),
    grasp=make_pose(handle_center),
    lift=make_pose(handle_center + np.array([0.0, 0.0, lift_height])),
  )


def build_yaw_aligned_pick_plan_from_points(
  points: Iterable[Iterable[float]],
  *,
  orientation: tuple[float, float, float, float],
  frame_id: str = "base_link",
  approach_distance: float = 0.10,
  pregrasp_distance: float = 0.03,
  lift_height: float = 0.10,
  tcp_offset: tuple[float, float, float] = (0.0, 0.0, 0.0),
  grasp_point: tuple[float, float, float] | None = None,
) -> PickPlan:
  """Align only the calibrated tool yaw to the point-cloud long axis."""

  point_array = _as_points(points)
  axis = np.asarray(estimate_object_geometry(point_array).principal_axis, dtype=np.float64)
  axis[2] = 0.0
  axis = _normalize(axis)
  rotation = _quaternion_to_matrix(orientation)
  reference_x = rotation[:, 0].copy()
  reference_x[2] = 0.0
  reference_x = _normalize(reference_x)
  if float(reference_x @ axis) < 0.0:
    axis = -axis
  yaw = float(np.arctan2(
    reference_x[0] * axis[1] - reference_x[1] * axis[0],
    reference_x @ axis,
  ))
  yaw_rotation = np.array([
    [np.cos(yaw), -np.sin(yaw), 0.0],
    [np.sin(yaw), np.cos(yaw), 0.0],
    [0.0, 0.0, 1.0],
  ], dtype=np.float64)
  aligned_orientation = _matrix_to_quaternion(yaw_rotation @ rotation)
  contact = grasp_point if grasp_point is not None else tuple(np.mean(point_array, axis=0))
  return build_fixed_orientation_pick_plan_from_contact(
    contact,
    orientation=aligned_orientation,
    frame_id=frame_id,
    approach_distance=approach_distance,
    pregrasp_distance=pregrasp_distance,
    lift_height=lift_height,
    tcp_offset=tcp_offset,
  )


def build_top_down_pick_plan(
  grasp: RobotPose,
  *,
  approach_distance: float = 0.10,
  pregrasp_distance: float = 0.03,
  lift_height: float = 0.10,
) -> PickPlan:
  """Build vertical approach, pregrasp, grasp, and lift waypoints."""

  return PickPlan(
    approach=grasp.offset_z(approach_distance),
    pregrasp=grasp.offset_z(pregrasp_distance),
    grasp=grasp,
    lift=grasp.offset_z(lift_height),
  )


def build_place_plan(place: RobotPose, *, clearance: float = 0.08) -> PlacePlan:
  """Build vertical approach, place, and retreat waypoints."""

  safe_pose = place.offset_z(clearance)
  return PlacePlan(approach=safe_pose, place=place, retreat=safe_pose)
