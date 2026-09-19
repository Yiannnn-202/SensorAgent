import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription, TimerAction
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch_ros.actions import Node


def generate_launch_description():
    # RealMan arm driver, robot description (TF), control, and MoveIt.
    rm_bringup = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(os.path.join(
            get_package_share_directory('rm_bringup'),
            'launch',
            'rm_65_bringup.launch.py',
        ))
    )

    # Task-level arm services, delayed until the rm_driver is ready.
    arm_control_server = TimerAction(period=3.0, actions=[
        Node(
            package='arm_control',
            executable='arm_control_server',
            name='arm_control_server',
            output='screen',
            parameters=[os.path.join(
                get_package_share_directory('arm_control'),
                'config',
                'arm_control.yaml',
            )],
        ),
    ])

    return LaunchDescription([
        rm_bringup,
        arm_control_server,
    ])
