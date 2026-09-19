"""SensorAgent-owned one-process-tree startup for the physical pick cell."""

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import Command, FindExecutable, LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from pathlib import Path


def _launch(package: str, name: str) -> IncludeLaunchDescription:
  return IncludeLaunchDescription(
    PythonLaunchDescriptionSource(str(Path(get_package_share_directory(package)) / "launch" / name))
  )


def generate_launch_description() -> LaunchDescription:
  bridge_share = Path(get_package_share_directory("sensoragent_hardware_bridge"))
  arm_control_share = Path(get_package_share_directory("arm_control"))
  description_share = Path(get_package_share_directory("rm_description"))
  op_port = LaunchConfiguration("op_port")
  allow_motion = LaunchConfiguration("allow_motion")
  robot_description = Command([
    FindExecutable(name="xacro"), " ", description_share / "urdf" / "rm_65.urdf",
  ])
  return LaunchDescription([
    DeclareLaunchArgument("op_port", default_value="/dev/ttyUSB0"),
    DeclareLaunchArgument("allow_motion", default_value="false"),
    _launch("rm_driver", "rm_65_driver.launch.py"),
    Node(
      package="robot_state_publisher",
      executable="robot_state_publisher",
      name="robot_state_publisher",
      parameters=[{"robot_description": robot_description}],
      remappings=[("joint_states", "/rm_driver/current_joint_states")],
      output="screen",
    ),
    # Do not include arm_control.launch.py: the Island-Arm version starts a
    # separate MoveIt bringup that conflicts with this lightweight hardware stack.
    Node(
      package="arm_control",
      executable="arm_control_server",
      name="arm_control_server",
      parameters=[str(arm_control_share / "config" / "arm_control.yaml")],
      output="screen",
    ),
    Node(
      package="op_control",
      executable="op_control_node",
      name="op_control_node",
      parameters=[{"port": op_port, "baudrate": 115200, "timeout_sec": 8.0}],
      output="screen",
    ),
    Node(package="vision_dep", executable="dep_cam", name="dep_cam", output="screen",
         parameters=[{"publish_hz": 5.0}]),
    Node(package="tf2_ros", executable="static_transform_publisher", output="screen",
         arguments=["--x", "-0.0868481306", "--y", "0.0345126227", "--z", "-0.0274944828",
                    "--qx", "0.0090451138", "--qy", "-0.0051656285", "--qz", "-0.6941265206",
                    "--qw", "0.7197776571", "--frame-id", "Link6", "--child-frame-id", "camera_link"]),
    Node(package="sensoragent_hardware_bridge", executable="hardware_bridge", output="screen",
         parameters=[str(bridge_share / "config" / "hardware_bridge.yaml"),
                     {"allow_motion": ParameterValue(allow_motion, value_type=bool)}]),
  ])
