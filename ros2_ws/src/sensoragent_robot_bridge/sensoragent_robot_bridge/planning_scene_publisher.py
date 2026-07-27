"""Publish static Gazebo scene obstacles into MoveIt's planning scene."""

from __future__ import annotations

import rclpy
from moveit_msgs.msg import PlanningScene
from rclpy.duration import Duration
from rclpy.node import Node
from rclpy.qos import QoSDurabilityPolicy, QoSProfile

from sensoragent_robot_bridge.scene_obstacles import camera_rig_collision_objects


class StaticScenePublisher(Node):
    """Periodically publish static collision objects for RViz and MoveIt."""

    def __init__(self) -> None:
        super().__init__("sensoragent_static_scene_publisher")
        self.declare_parameter("base_frame", "base_link")
        self.declare_parameter("publish_period", 2.0)
        self._base_frame = str(self.get_parameter("base_frame").value)
        period = float(self.get_parameter("publish_period").value)
        qos = QoSProfile(depth=1, durability=QoSDurabilityPolicy.TRANSIENT_LOCAL)
        self._publisher = self.create_publisher(PlanningScene, "/planning_scene", qos)
        self._timer = self.create_timer(max(0.5, period), self.publish_scene)

    def publish_scene(self) -> None:
        scene = PlanningScene()
        scene.is_diff = True
        scene.world.collision_objects = camera_rig_collision_objects(
            frame_id=self._base_frame,
        )
        self._publisher.publish(scene)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = StaticScenePublisher()
    try:
        deadline = node.get_clock().now() + Duration(seconds=5.0)
        while rclpy.ok() and node.get_clock().now() < deadline:
            node.publish_scene()
            rclpy.spin_once(node, timeout_sec=0.1)
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
