"""SensorAgent-owned one-process-tree startup for the physical pick cell."""

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import Command, FindExecutable
from launch_ros.actions import Node
from pathlib import Path


def _launch(package: str, name: str) -> IncludeLaunchDescription:
  return IncludeLaunchDescription(
    PythonLaunchDescriptionSource(str(Path(get_package_share_directory(package)) / "launch" / name))
  )


def generate_launch_description() -> LaunchDescription:
  bridge_share = Path(get_package_share_directory("sensoragent_hardware_bridge"))
  description_share = Path(get_package_share_directory("rm_description"))
  robot_description = Command([
    FindExecutable(name="xacro"), " ", description_share / "urdf" / "rm_65.urdf",
  ])
  return LaunchDescription([
    _launch("rm_driver", "rm_65_driver.launch.py"),
    # The vendor display launch remaps an absolute /joint_states name, which
    # leaves the publisher disconnected from the driver's namespaced topic.
    Node(
      package="robot_state_publisher",
      executable="robot_state_publisher",
      name="robot_state_publisher",
      parameters=[{"robot_description": robot_description}],
      remappings=[("joint_states", "/rm_driver/current_joint_states")],
      output="screen",
    ),
    _launch("arm_control", "arm_control.launch.py"),
    _launch("op_control", "op_control.launch.py"),
    Node(package="vision_dep", executable="dep_cam", name="dep_cam", output="screen",
         parameters=[{"publish_hz": 5.0}]),
    Node(package="tf2_ros", executable="static_transform_publisher", output="screen",
         arguments=["--x", "-0.0868481306", "--y", "0.0345126227", "--z", "-0.0274944828",
                    "--qx", "0.0090451138", "--qy", "-0.0051656285", "--qz", "-0.6941265206",
                    "--qw", "0.7197776571", "--frame-id", "Link6", "--child-frame-id", "camera_link"]),
    Node(package="sensoragent_hardware_bridge", executable="hardware_bridge", output="screen",
         parameters=[str(bridge_share / "config" / "hardware_bridge.yaml")]),
  ])
