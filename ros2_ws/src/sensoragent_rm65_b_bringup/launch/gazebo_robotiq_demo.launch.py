import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    ExecuteProcess,
    IncludeLaunchDescription,
    RegisterEventHandler,
    SetEnvironmentVariable,
    TimerAction,
)
from launch.conditions import IfCondition
from launch.event_handlers import OnProcessExit
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import (
    Command,
    EnvironmentVariable,
    FindExecutable,
    LaunchConfiguration,
    PathJoinSubstitution,
)
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    package_name = "sensoragent_rm65_b_bringup"
    world_name = "empty"
    package_share = get_package_share_directory(package_name)
    ros_gz_sim_share = get_package_share_directory("ros_gz_sim")
    share_parent = os.path.dirname(package_share)

    robot_description = {
        "robot_description": ParameterValue(
            Command(
                [
                    FindExecutable(name="xacro"),
                    " ",
                    PathJoinSubstitution(
                        [
                            package_share,
                            "urdf",
                            "rm65_b_robotiq_2f85.urdf.xacro",
                        ]
                    ),
                ]
            ),
            value_type=str,
        )
    }

    gazebo = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(ros_gz_sim_share, "launch", "gz_sim.launch.py")
        ),
        launch_arguments={
            "gz_args": [
                "-v 4 -r --render-engine ",
                LaunchConfiguration("render_engine"),
                f" {world_name}.sdf",
            ]
        }.items(),
        condition=IfCondition(LaunchConfiguration("start_gazebo")),
    )

    robot_state_publisher = Node(
        package="robot_state_publisher",
        executable="robot_state_publisher",
        parameters=[
            robot_description,
            {"use_sim_time": True, "publish_frequency": 30.0},
        ],
        output="screen",
    )

    clock_bridge = Node(
        package="ros_gz_bridge",
        executable="parameter_bridge",
        arguments=["/clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock"],
        output="screen",
    )

    spawn_robot = Node(
        package="ros_gz_sim",
        executable="create",
        arguments=[
            "-world",
            world_name,
            "-topic",
            "robot_description",
            "-name",
            "rm65_b_robotiq_2f85",
        ],
        output="screen",
    )

    unpause_world = ExecuteProcess(
        cmd=[
            "ign",
            "service",
            "-s",
            f"/world/{world_name}/control",
            "--reqtype",
            "ignition.msgs.WorldControl",
            "--reptype",
            "ignition.msgs.Boolean",
            "--timeout",
            "3000",
            "--req",
            "pause: false",
        ],
        output="screen",
    )

    spawn_controllers = Node(
        package="controller_manager",
        executable="spawner",
        arguments=[
            "joint_state_broadcaster",
            "rm_group_controller",
            "robotiq_gripper_controller",
            "--controller-manager",
            "/controller_manager",
            "--controller-manager-timeout",
            "120",
            "--switch-timeout",
            "120",
            "--service-call-timeout",
            "30",
            "--activate-as-group",
        ],
        output="screen",
    )

    unpause_after_spawn = RegisterEventHandler(
        OnProcessExit(
            target_action=spawn_robot,
            on_exit=[TimerAction(period=2.0, actions=[unpause_world])],
        )
    )
    controllers_after_unpause = RegisterEventHandler(
        OnProcessExit(
            target_action=unpause_world,
            on_exit=[TimerAction(period=2.0, actions=[spawn_controllers])],
        )
    )

    return LaunchDescription(
        [
            DeclareLaunchArgument("start_gazebo", default_value="true"),
            DeclareLaunchArgument("render_engine", default_value="ogre2"),
            SetEnvironmentVariable(
                name="GZ_SIM_RESOURCE_PATH",
                value=[
                    share_parent,
                    os.pathsep,
                    EnvironmentVariable("GZ_SIM_RESOURCE_PATH", default_value=""),
                ],
            ),
            gazebo,
            robot_state_publisher,
            clock_bridge,
            spawn_robot,
            unpause_after_spawn,
            controllers_after_unpause,
        ]
    )
