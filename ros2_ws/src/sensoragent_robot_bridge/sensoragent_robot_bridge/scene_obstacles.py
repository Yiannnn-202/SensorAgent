"""MoveIt planning-scene obstacles for the SensorAgent Gazebo scene."""

from __future__ import annotations

from geometry_msgs.msg import Pose
from moveit_msgs.msg import CollisionObject
from shape_msgs.msg import SolidPrimitive


def box_collision_object(
    object_id: str,
    *,
    center: tuple[float, float, float],
    size: tuple[float, float, float],
    frame_id: str = "base_link",
) -> CollisionObject:
    collision = CollisionObject()
    collision.header.frame_id = frame_id
    collision.id = object_id
    primitive = SolidPrimitive()
    primitive.type = SolidPrimitive.BOX
    primitive.dimensions = [float(value) for value in size]
    pose = Pose()
    pose.position.x = float(center[0])
    pose.position.y = float(center[1])
    pose.position.z = float(center[2])
    pose.orientation.w = 1.0
    collision.primitives.append(primitive)
    collision.primitive_poses.append(pose)
    collision.operation = CollisionObject.ADD
    return collision


def camera_rig_collision_objects(*, frame_id: str = "base_link") -> list[CollisionObject]:
    """Inflated camera-rig obstacles in base_link coordinates.

    The matching SDF model is static in world coordinates. The robot base_link is
    mounted at world z=0.18 with a 180-degree yaw, so base-frame x/y centers are
    the negated world x/y centers and base-frame z centers are the SDF z centers
    minus 0.18 m. Dimensions intentionally over-approximate the visual geometry
    and nearby gripper clearance so MoveIt keeps the wrist and fingers away from
    the rig instead of merely avoiding the thin rendered posts.
    """

    return [
        box_collision_object(
            "sensoragent_camera_left_post",
            center=(-0.34, -0.42, 0.39),
            size=(0.24, 0.24, 1.32),
            frame_id=frame_id,
        ),
        box_collision_object(
            "sensoragent_camera_right_post",
            center=(-0.34, 0.42, 0.39),
            size=(0.24, 0.24, 1.32),
            frame_id=frame_id,
        ),
        box_collision_object(
            "sensoragent_camera_crossbar",
            center=(-0.34, 0.0, 0.94),
            size=(0.22, 1.08, 0.22),
            frame_id=frame_id,
        ),
        box_collision_object(
            "sensoragent_camera_body",
            center=(-0.34, 0.0, 0.90),
            size=(0.26, 0.22, 0.20),
            frame_id=frame_id,
        ),
    ]


def sorting_workbench_collision_objects(
    *,
    frame_id: str = "base_link",
) -> list[CollisionObject]:
    """Collision objects for the metal sorting scene workbench.

    Gazebo has its own SDF collision geometry, but MoveIt only avoids objects
    explicitly added to its planning scene. The metal sorting world mounts the
    robot at world z=0.18 with 180-degree yaw, so world coordinates are converted
    to base_link by negating x/y and subtracting 0.18 from z.
    """

    return [
        box_collision_object(
            "sensoragent_sorting_workbench_top",
            center=(-0.42, 0.0, 0.085),
            size=(0.65, 0.90, 0.03),
            frame_id=frame_id,
        ),
        box_collision_object(
            "sensoragent_sorting_workbench_leg_1",
            center=(-0.145, 0.375, -0.05),
            size=(0.06, 0.06, 0.26),
            frame_id=frame_id,
        ),
        box_collision_object(
            "sensoragent_sorting_workbench_leg_2",
            center=(-0.145, -0.375, -0.05),
            size=(0.06, 0.06, 0.26),
            frame_id=frame_id,
        ),
        box_collision_object(
            "sensoragent_sorting_workbench_leg_3",
            center=(-0.695, 0.375, -0.05),
            size=(0.06, 0.06, 0.26),
            frame_id=frame_id,
        ),
        box_collision_object(
            "sensoragent_sorting_workbench_leg_4",
            center=(-0.695, -0.375, -0.05),
            size=(0.06, 0.06, 0.26),
            frame_id=frame_id,
        ),
    ]


def sorting_bin_collision_objects(
    *,
    frame_id: str = "base_link",
) -> list[CollisionObject]:
    """Collision objects for the 3x3 placement tray in the sorting scene."""

    return [
        box_collision_object(
            "sensoragent_sorting_bin_bottom",
            center=(-0.28, -0.16, 0.125),
            size=(0.351, 0.351, 0.01),
            frame_id=frame_id,
        ),
        box_collision_object(
            "sensoragent_sorting_bin_wall_x_pos",
            center=(-0.4505, -0.16, 0.1525),
            size=(0.01, 0.351, 0.055),
            frame_id=frame_id,
        ),
        box_collision_object(
            "sensoragent_sorting_bin_wall_x_neg",
            center=(-0.1095, -0.16, 0.1525),
            size=(0.01, 0.351, 0.055),
            frame_id=frame_id,
        ),
        box_collision_object(
            "sensoragent_sorting_bin_wall_y_pos",
            center=(-0.28, -0.3305, 0.1525),
            size=(0.331, 0.01, 0.055),
            frame_id=frame_id,
        ),
        box_collision_object(
            "sensoragent_sorting_bin_wall_y_neg",
            center=(-0.28, 0.0105, 0.1525),
            size=(0.331, 0.01, 0.055),
            frame_id=frame_id,
        ),
        box_collision_object(
            "sensoragent_sorting_bin_divider_x_left",
            center=(-0.2235, -0.16, 0.1525),
            size=(0.008, 0.331, 0.050),
            frame_id=frame_id,
        ),
        box_collision_object(
            "sensoragent_sorting_bin_divider_x_right",
            center=(-0.3365, -0.16, 0.1525),
            size=(0.008, 0.331, 0.050),
            frame_id=frame_id,
        ),
        box_collision_object(
            "sensoragent_sorting_bin_divider_y_front",
            center=(-0.28, -0.1035, 0.1525),
            size=(0.331, 0.008, 0.050),
            frame_id=frame_id,
        ),
        box_collision_object(
            "sensoragent_sorting_bin_divider_y_back",
            center=(-0.28, -0.2165, 0.1525),
            size=(0.331, 0.008, 0.050),
            frame_id=frame_id,
        ),
    ]


def static_scene_collision_objects(
    *,
    frame_id: str = "base_link",
) -> list[CollisionObject]:
    """Return all static scene obstacles that MoveIt should avoid."""

    return [
        *camera_rig_collision_objects(frame_id=frame_id),
        *sorting_workbench_collision_objects(frame_id=frame_id),
        *sorting_bin_collision_objects(frame_id=frame_id),
    ]
