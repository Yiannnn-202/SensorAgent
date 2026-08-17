"""Robot planning tools that produce backend-neutral pick/place plans."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from sensoragent.schemas import RobotPose, ToolCall, ToolResult, ToolSpec
from sensoragent.skills.robot import (
  build_oriented_pick_plan_from_points,
  build_place_plan,
  build_top_down_pick_plan,
  estimate_object_geometry,
  estimate_shaft_grasp_point,
)


DEFAULT_TOP_DOWN_ORIENTATION = (0.0, 1.0, 0.0, 0.0)


def _number_list(value, field: str, minimum_size: int) -> list[float]:
  if not isinstance(value, (list, tuple)) or len(value) < minimum_size:
    raise ValueError(f"{field} must contain at least {minimum_size} numeric values")
  result = []
  for item in value:
    if not isinstance(item, (int, float)) or isinstance(item, bool):
      raise ValueError(f"{field} must contain numeric values")
    result.append(float(item))
  return result


def _grasp_pose_from_input(input_data: dict) -> RobotPose:
  """Build a grasp pose from full pose or simple vision-returned 3D position."""

  if input_data.get("grasp_pose") is not None:
    return RobotPose.from_dict(input_data.get("grasp_pose"))

  position_value = (
    input_data.get("position")
    or input_data.get("point_3d")
    or input_data.get("pose_3d")
  )
  position = _number_list(position_value, "position/point_3d/pose_3d", 3)[:3]
  offset = input_data.get("position_offset", [0.0, 0.0, 0.0])
  offset_xyz = _number_list(offset, "position_offset", 3)[:3]
  orientation = input_data.get("orientation", DEFAULT_TOP_DOWN_ORIENTATION)
  orientation_xyzw = _number_list(orientation, "orientation", 4)[:4]
  return RobotPose(
    position=tuple(position[index] + offset_xyz[index] for index in range(3)),
    orientation=tuple(orientation_xyzw),
    frame_id=str(input_data.get("frame_id", "base_link")),
  )


def _point_in_polygon(points: np.ndarray, polygon: list[list[float]]) -> np.ndarray:
  """Return an inside mask for Nx2 pixel coordinates."""

  vertices = np.asarray(polygon, dtype=np.float64)
  if vertices.ndim != 2 or vertices.shape[0] < 3 or vertices.shape[1] < 2:
    return np.zeros(len(points), dtype=bool)
  inside = np.zeros(len(points), dtype=bool)
  previous = vertices[-1, :2]
  for current in vertices[:, :2]:
    x1, y1 = previous
    x2, y2 = current
    crosses = ((y1 > points[:, 1]) != (y2 > points[:, 1]))
    denominator = y2 - y1
    safe_denominator = denominator if abs(denominator) > 1e-12 else 1e-12
    x_intersection = (x2 - x1) * (points[:, 1] - y1) / safe_denominator + x1
    inside ^= crosses & (points[:, 0] < x_intersection)
    previous = current
  return inside


def _masked_cloud_points(
  cloud_path: object,
  mask_polygons: object,
) -> np.ndarray:
  if not cloud_path or not isinstance(mask_polygons, list):
    return np.empty((0, 3), dtype=np.float64)
  cloud = np.load(Path(str(cloud_path)))
  if cloud.ndim != 2 or cloud.shape[1] < 5:
    raise ValueError("cloud_path must contain Nx5 xyzuv points")
  valid = np.isfinite(cloud[:, :5]).all(axis=1)
  cloud = cloud[valid]
  if len(cloud) == 0:
    return np.empty((0, 3), dtype=np.float64)
  pixel_points = cloud[:, 3:5]
  selected = np.zeros(len(cloud), dtype=bool)
  for polygon in mask_polygons:
    if isinstance(polygon, list):
      selected |= _point_in_polygon(pixel_points, polygon)
  points = cloud[selected, :3]
  if len(points) > 8000:
    stride = max(1, len(points) // 8000)
    points = points[::stride][:8000]
  return points


def _transform_camera_point(point: np.ndarray, transform: object) -> np.ndarray | None:
  if isinstance(transform, list):
    matrix = np.asarray(transform, dtype=np.float64)
    if matrix.shape == (4, 4):
      return matrix[:3, :3] @ point + matrix[:3, 3]
  if isinstance(transform, dict):
    translation = transform.get("translation")
    rotation = transform.get("rotation_xyzw")
    if isinstance(translation, list) and len(translation) == 3 and isinstance(rotation, list) and len(rotation) == 4:
      x, y, z, w = (float(value) for value in rotation)
      matrix = np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
      ])
      return matrix @ point + np.asarray(translation, dtype=np.float64)
  return None


def _transform_camera_points(points: np.ndarray, transform: object) -> np.ndarray:
  if len(points) == 0:
    return points
  if isinstance(transform, list):
    matrix = np.asarray(transform, dtype=np.float64)
    if matrix.shape == (4, 4):
      return points @ matrix[:3, :3].T + matrix[:3, 3]
  if isinstance(transform, dict):
    translation = transform.get("translation")
    rotation = transform.get("rotation_xyzw")
    if isinstance(translation, list) and len(translation) == 3 and isinstance(rotation, list) and len(rotation) == 4:
      x, y, z, w = (float(value) for value in rotation)
      matrix = np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
      ])
      return points @ matrix.T + np.asarray(translation, dtype=np.float64)
  return points


def _transform_camera_vector(vector: np.ndarray, transform: object) -> np.ndarray | None:
  if isinstance(transform, list):
    matrix = np.asarray(transform, dtype=np.float64)
    if matrix.shape == (4, 4):
      return matrix[:3, :3] @ vector
  if isinstance(transform, dict):
    rotation = transform.get("rotation_xyzw")
    if isinstance(rotation, list) and len(rotation) == 4:
      x, y, z, w = (float(value) for value in rotation)
      matrix = np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
      ])
      return matrix @ vector
  return None


def _nearest_cloud_point(cloud_path: object, pixel: tuple[float, float]) -> np.ndarray | None:
  if not cloud_path:
    return None
  cloud = np.load(Path(str(cloud_path)))
  if cloud.ndim != 2 or cloud.shape[1] < 5:
    raise ValueError("cloud_path must contain Nx5 xyzuv points")
  valid = np.isfinite(cloud[:, :5]).all(axis=1)
  cloud = cloud[valid]
  if len(cloud) == 0:
    return None
  distances = (cloud[:, 3] - pixel[0]) ** 2 + (cloud[:, 4] - pixel[1]) ** 2
  return cloud[int(np.argmin(distances)), :3].astype(np.float64)


def _validate_safe_waypoints(
  plan,
  input_data: dict,
  *,
  error_prefix: str,
) -> None:
  minimum_z = float(input_data.get("minimum_safe_z", 0.14))
  workspace_min = input_data.get("workspace_min", [-0.55, -0.18, 0.0])
  workspace_max = input_data.get("workspace_max", [-0.20, 0.18, 0.35])
  if not isinstance(workspace_min, list) or not isinstance(workspace_max, list) or len(workspace_min) != 3 or len(workspace_max) != 3:
    raise ValueError("workspace_min and workspace_max must contain three numbers")
  lower = np.asarray(workspace_min, dtype=np.float64)
  upper = np.asarray(workspace_max, dtype=np.float64)
  for name in ("approach", "pregrasp", "grasp", "lift"):
    position = np.asarray(getattr(plan, name).position, dtype=np.float64)
    if position[2] < minimum_z:
      raise ValueError(
        f"{error_prefix}_SAFETY: {name}.z={position[2]:.4f} "
        f"below minimum_safe_z={minimum_z:.4f}"
      )
    if np.any(position < lower) or np.any(position > upper):
      raise ValueError(
        f"{error_prefix}_WORKSPACE: {name} position is outside configured workspace"
      )


def _validate_waypoints(plan, input_data: dict) -> None:
  _validate_safe_waypoints(plan, input_data, error_prefix="SHORT_BOLT")


def _plan_within_workspace(plan, input_data: dict) -> bool:
  minimum_z = float(input_data.get("minimum_safe_z", 0.14))
  workspace_min = input_data.get("workspace_min", [-0.55, -0.18, 0.0])
  workspace_max = input_data.get("workspace_max", [-0.20, 0.18, 0.35])
  if not isinstance(workspace_min, list) or not isinstance(workspace_max, list) or len(workspace_min) != 3 or len(workspace_max) != 3:
    return False
  lower = np.asarray(workspace_min, dtype=np.float64)
  upper = np.asarray(workspace_max, dtype=np.float64)
  for name in ("approach", "pregrasp", "grasp", "lift"):
    position = np.asarray(getattr(plan, name).position, dtype=np.float64)
    if position[2] < minimum_z:
      return False
    if np.any(position < lower) or np.any(position > upper):
      return False
  return True


def _lift_plan(plan, *, minimum_safe_z: float):
  positions = [np.asarray(getattr(plan, name).position, dtype=np.float64) for name in ("approach", "pregrasp", "grasp", "lift")]
  current_min_z = min(float(position[2]) for position in positions)
  if current_min_z >= minimum_safe_z:
    return plan
  delta = minimum_safe_z - current_min_z
  return type(plan)(
    approach=plan.approach.offset_z(delta),
    pregrasp=plan.pregrasp.offset_z(delta),
    grasp=plan.grasp.offset_z(delta),
    lift=plan.lift.offset_z(delta),
  )


def _fit_plan_z_window(plan, input_data: dict):
  minimum_z = float(input_data.get("minimum_safe_z", 0.14))
  workspace_max = input_data.get("workspace_max", [-0.20, 0.18, 0.35])
  if not isinstance(workspace_max, list) or len(workspace_max) != 3:
    return plan
  maximum_z = float(workspace_max[2])
  positions = [np.asarray(getattr(plan, name).position, dtype=np.float64) for name in ("approach", "pregrasp", "grasp", "lift")]
  current_max_z = max(float(position[2]) for position in positions)
  current_min_z = min(float(position[2]) for position in positions)
  if current_max_z <= maximum_z:
    return plan
  delta = current_max_z - maximum_z
  if current_min_z - delta < minimum_z:
    return plan
  return type(plan)(
    approach=plan.approach.offset_z(-delta),
    pregrasp=plan.pregrasp.offset_z(-delta),
    grasp=plan.grasp.offset_z(-delta),
    lift=plan.lift.offset_z(-delta),
  )


def _has_base_transform(value: object) -> bool:
  if isinstance(value, list):
    return np.asarray(value, dtype=np.float64).shape == (4, 4)
  if isinstance(value, dict):
    translation = value.get("translation")
    rotation = value.get("rotation_xyzw")
    return (
      isinstance(translation, list)
      and len(translation) == 3
      and isinstance(rotation, list)
      and len(rotation) == 4
    )
  return False


class RobotPlanMaskPointCloudPickTool:
  """Experimental generic PCA pick planner for mask-selected point clouds.

  This tool is deliberately not referenced by a production ActionList. It is a
  reusable fallback candidate for elongated, rigid objects whose point-cloud
  geometry supports a stable principal axis.
  """

  spec = ToolSpec(
    name="robot.plan_mask_pointcloud_pick",
    description=(
      "Experimental mask-and-point-cloud PCA grasp planner with a safe "
      "top-down fallback."
    ),
    tags=("robot", "planning", "pick", "point-cloud", "experimental"),
  )

  def run(self, call: ToolCall) -> ToolResult:
    minimum_points = call.input.get("minimum_points", 20)
    if not isinstance(minimum_points, int) or isinstance(minimum_points, bool):
      raise ValueError("minimum_points must be an integer")
    if minimum_points < 3:
      raise ValueError("minimum_points must be at least 3")

    transform = call.input.get("T_base_camera")
    point_frame = str(call.input.get("point_frame", "camera"))
    raw_points = _masked_cloud_points(
      call.input.get("cloud_path"),
      call.input.get("mask_polygons"),
    )
    fallback_reason: str | None = None
    if point_frame != "base_link" and not _has_base_transform(transform):
      points = np.empty((0, 3), dtype=np.float64)
      fallback_reason = "MISSING_BASE_TRANSFORM"
    else:
      points = _transform_camera_points(raw_points, transform)

    if len(points) >= minimum_points:
      geometry = estimate_object_geometry(points)
      offset = np.asarray(
        _number_list(call.input.get("position_offset", [0.0, 0.0, 0.0]), "position_offset", 3)[:3],
        dtype=np.float64,
      )
      grasp_point = tuple(np.asarray(geometry.center, dtype=np.float64) + offset)
      tcp_offset = tuple(
        _number_list(call.input.get("tcp_offset", [0.0, 0.0, 0.0]), "tcp_offset", 3)[:3]
      )
      plan = build_oriented_pick_plan_from_points(
        points,
        frame_id=str(call.input.get("frame_id", "base_link")),
        approach_distance=float(call.input.get("approach_distance", 0.10)),
        pregrasp_distance=float(call.input.get("pregrasp_distance", 0.04)),
        lift_height=float(call.input.get("lift_height", 0.12)),
        tcp_offset=tcp_offset,
        grasp_point=grasp_point,
      )
      plan = _lift_plan(
        plan,
        minimum_safe_z=float(call.input.get("minimum_safe_z", 0.14)),
      )
      plan = _fit_plan_z_window(plan, call.input)
      if _plan_within_workspace(plan, call.input):
        _validate_safe_waypoints(
          plan,
          call.input,
          error_prefix="MASK_POINTCLOUD",
        )
        return ToolResult(
          tool=self.spec.name,
          success=True,
          output={
            "plan": plan.to_dict(),
            "mode": "mask_pca_center",
            "point_count": int(len(points)),
          },
        )
      fallback_reason = "PCA_PLAN_OUTSIDE_SAFE_WORKSPACE"
    elif fallback_reason is None:
      fallback_reason = "INSUFFICIENT_MASKED_POINTS"

    grasp = _grasp_pose_from_input(call.input)
    plan = build_top_down_pick_plan(
      grasp,
      approach_distance=float(call.input.get("approach_distance", 0.10)),
      pregrasp_distance=float(call.input.get("pregrasp_distance", 0.04)),
      lift_height=float(call.input.get("lift_height", 0.12)),
    )
    plan = _lift_plan(plan, minimum_safe_z=float(call.input.get("minimum_safe_z", 0.14)))
    plan = _fit_plan_z_window(plan, call.input)
    _validate_safe_waypoints(plan, call.input, error_prefix="MASK_POINTCLOUD")
    return ToolResult(
      tool=self.spec.name,
      success=True,
      output={
        "plan": plan.to_dict(),
        "mode": "pose_fallback",
        "point_count": int(len(points)),
        "fallback_reason": fallback_reason,
      },
    )


class RobotPlanShortBoltPickTool:
  """Plan a short-bolt grasp from a SAM2 mask and RGB-D point cloud."""

  spec = ToolSpec(
    name="robot.plan_short_bolt_pick",
    description="Use SAM2 mask and XYZUV point-cloud PCA to grasp the bolt shaft toward its head.",
    tags=("robot", "planning", "pick", "short-bolt", "point-cloud", "safety"),
  )

  def run(self, call: ToolCall) -> ToolResult:
    transform = call.input.get("T_base_camera")
    points = _masked_cloud_points(call.input.get("cloud_path"), call.input.get("mask_polygons"))
    points = _transform_camera_points(points, transform)
    if len(points) >= 20:
      grasp_point = estimate_shaft_grasp_point(
        points,
        headward_offset=float(call.input.get("headward_offset", 0.015)),
      )
      camera_left_px = float(call.input.get("camera_left_offset_px", 0.0))
      center_px = call.input.get("center_px")
      if camera_left_px and isinstance(center_px, list) and len(center_px) >= 2:
        camera_point = _nearest_cloud_point(
          call.input.get("cloud_path"),
          (float(center_px[0]) - camera_left_px, float(center_px[1])),
        )
        base_point = _transform_camera_point(camera_point, transform) if camera_point is not None else None
        center_camera_point = _nearest_cloud_point(
          call.input.get("cloud_path"), (float(center_px[0]), float(center_px[1]))
        )
        center_point = (
          _transform_camera_point(center_camera_point, transform)
          if transform is not None and center_camera_point is not None
          else None
        )
        if base_point is not None and center_point is not None:
          grasp_point = tuple(np.asarray(grasp_point) + (base_point - center_point))
      camera_left_m = float(call.input.get("camera_left_offset_m", 0.0))
      if camera_left_m:
        base_delta = _transform_camera_vector(np.asarray([-camera_left_m, 0.0, 0.0], dtype=np.float64), transform)
        if base_delta is not None:
          grasp_point = tuple(np.asarray(grasp_point) + base_delta)
      position_offset = np.asarray(call.input.get("position_offset", [0.0, 0.0, 0.0]), dtype=np.float64)
      grasp_point = tuple(np.asarray(grasp_point) + position_offset)
      plan = build_oriented_pick_plan_from_points(
        points,
        frame_id=str(call.input.get("frame_id", "base_link")),
        approach_distance=float(call.input.get("approach_distance", 0.10)),
        pregrasp_distance=float(call.input.get("pregrasp_distance", 0.04)),
        lift_height=float(call.input.get("lift_height", 0.12)),
        tcp_offset=tuple(float(value) for value in call.input.get("tcp_offset", [0.0, 0.0, 0.161])),
        grasp_point=grasp_point,
      )
      plan = _lift_plan(plan, minimum_safe_z=float(call.input.get("minimum_safe_z", 0.14)))
      plan = _fit_plan_z_window(plan, call.input)
      if not _plan_within_workspace(plan, call.input):
        grasp = _grasp_pose_from_input(call.input)
        plan = build_top_down_pick_plan(
          grasp,
          approach_distance=float(call.input.get("approach_distance", 0.10)),
          pregrasp_distance=float(call.input.get("pregrasp_distance", 0.04)),
          lift_height=float(call.input.get("lift_height", 0.12)),
        )
        plan = _lift_plan(plan, minimum_safe_z=float(call.input.get("minimum_safe_z", 0.14)))
        plan = _fit_plan_z_window(plan, call.input)
        if not _plan_within_workspace(plan, call.input):
          raise ValueError("SHORT_BOLT_WORKSPACE: no safe plan inside configured workspace")
        return ToolResult(tool=self.spec.name, success=True, output={"plan": plan.to_dict(), "mode": "pose_fallback"})
      _validate_waypoints(plan, call.input)
      return ToolResult(tool=self.spec.name, success=True, output={"plan": plan.to_dict(), "mode": "mask_pca"})

    grasp = _grasp_pose_from_input(call.input)
    plan = build_top_down_pick_plan(
      grasp,
      approach_distance=float(call.input.get("approach_distance", 0.10)),
      pregrasp_distance=float(call.input.get("pregrasp_distance", 0.04)),
      lift_height=float(call.input.get("lift_height", 0.12)),
    )
    _validate_waypoints(plan, call.input)
    return ToolResult(tool=self.spec.name, success=True, output={"plan": plan.to_dict(), "mode": "pose_fallback"})


class RobotPlanTopDownPickTool:
  """Generate a simple top-down PickPlan from a pose or vision 3D position."""

  spec = ToolSpec(
    name="robot.plan_top_down_pick",
    description="Generate pick waypoints from a grasp pose or a simple vision-returned 3D position.",
    tags=("robot", "planning", "pick"),
  )

  def run(self, call: ToolCall) -> ToolResult:
    grasp = _grasp_pose_from_input(call.input)
    plan = build_top_down_pick_plan(
      grasp,
      approach_distance=float(call.input.get("approach_distance", 0.10)),
      pregrasp_distance=float(call.input.get("pregrasp_distance", 0.03)),
      lift_height=float(call.input.get("lift_height", 0.10)),
    )
    return ToolResult(
      tool=self.spec.name,
      success=True,
      output={
        "grasp_pose": grasp.to_dict(),
        "plan": plan.to_dict(),
      },
    )


class RobotPlanOrientedPickTool:
  """Generate an oriented PickPlan from object point-cloud samples."""

  spec = ToolSpec(
    name="robot.plan_oriented_pick",
    description="Generate an oriented pick plan from base-frame object point samples.",
    tags=("robot", "planning", "pick", "point-cloud"),
  )

  def run(self, call: ToolCall) -> ToolResult:
    tcp_offset = tuple(float(value) for value in call.input.get("tcp_offset", [0.0, 0.0, 0.0]))
    if len(tcp_offset) != 3:
      raise ValueError("tcp_offset must contain three numbers")
    plan = build_oriented_pick_plan_from_points(
      call.input.get("points", []),
      frame_id=str(call.input.get("frame_id", "base_link")),
      approach_distance=float(call.input.get("approach_distance", 0.10)),
      pregrasp_distance=float(call.input.get("pregrasp_distance", 0.03)),
      lift_height=float(call.input.get("lift_height", 0.10)),
      tcp_offset=tcp_offset,
    )
    return ToolResult(
      tool=self.spec.name,
      success=True,
      output={"plan": plan.to_dict()},
    )


class RobotPlanPlaceTool:
  """Generate a simple PlacePlan from a target place pose."""

  spec = ToolSpec(
    name="robot.plan_place",
    description="Generate approach, place, and retreat waypoints from a place pose.",
    tags=("robot", "planning", "place"),
  )

  def run(self, call: ToolCall) -> ToolResult:
    place = RobotPose.from_dict(call.input.get("place_pose"))
    plan = build_place_plan(
      place,
      clearance=float(call.input.get("clearance", 0.08)),
    )
    return ToolResult(
      tool=self.spec.name,
      success=True,
      output={"plan": plan.to_dict()},
    )
