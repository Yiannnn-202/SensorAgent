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
