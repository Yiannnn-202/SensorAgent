import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    IncludeLaunchDescription,
    TimerAction,
)
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration


def generate_launch_description():
    launch_directory = os.path.join(
        get_package_share_directory("sensoragent_rm65_b_bringup"),
        "launch",
    )

    gazebo = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(launch_directory, "gazebo_robotiq_demo.launch.py")
        ),
        launch_arguments={
            "render_engine": LaunchConfiguration("render_engine"),
            "auto_focus_robot": LaunchConfiguration("auto_focus_robot"),
            "world_file": LaunchConfiguration("world_file"),
            "bridge_camera": LaunchConfiguration("bridge_camera"),
        }.items(),
    )

    moveit = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(launch_directory, "moveit_robotiq_demo.launch.py")
        ),
        condition=IfCondition(LaunchConfiguration("start_moveit")),
    )

    robot_bridge = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(
                get_package_share_directory("sensoragent_robot_bridge"),
                "launch",
                "robot_bridge.launch.py",
            )
        ),
        launch_arguments={
            "bind_host": LaunchConfiguration("robot_bridge_host"),
            "bind_port": LaunchConfiguration("robot_bridge_port"),
            "motion_timeout": LaunchConfiguration("robot_bridge_motion_timeout"),
        }.items(),
        condition=IfCondition(LaunchConfiguration("start_robot_bridge")),
    )

    return LaunchDescription(
        [
            DeclareLaunchArgument("render_engine", default_value="ogre"),
            DeclareLaunchArgument("auto_focus_robot", default_value="false"),
            DeclareLaunchArgument("start_moveit", default_value="true"),
            DeclareLaunchArgument("start_robot_bridge", default_value="true"),
            DeclareLaunchArgument(
                "robot_bridge_host",
                default_value="127.0.0.1",
            ),
            DeclareLaunchArgument("robot_bridge_port", default_value="8765"),
            DeclareLaunchArgument(
                "robot_bridge_motion_timeout", default_value="90.0"
            ),
            DeclareLaunchArgument(
                "world_file",
                default_value="industrial_pgs.sdf",
            ),
            DeclareLaunchArgument("bridge_camera", default_value="true"),
            gazebo,
            TimerAction(period=8.0, actions=[moveit]),
            TimerAction(period=10.0, actions=[robot_bridge]),
        ]
    )
