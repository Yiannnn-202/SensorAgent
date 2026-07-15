import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    package_share = get_package_share_directory("sensoragent_robot_bridge")
    config_path = os.path.join(package_share, "config", "robot_bridge.yaml")

    return LaunchDescription(
        [
            DeclareLaunchArgument("bind_host", default_value="127.0.0.1"),
            DeclareLaunchArgument("bind_port", default_value="8765"),
            Node(
                package="sensoragent_robot_bridge",
                executable="robot_bridge",
                name="sensoragent_robot_bridge",
                output="screen",
                parameters=[
                    config_path,
                    {
                        "bind_host": LaunchConfiguration("bind_host"),
                        "bind_port": ParameterValue(
                            LaunchConfiguration("bind_port"),
                            value_type=int,
                        ),
                        "use_sim_time": True,
                    },
                ],
            ),
        ]
    )
