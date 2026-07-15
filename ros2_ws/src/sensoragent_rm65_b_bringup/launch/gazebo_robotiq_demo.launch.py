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
    description_share = get_package_share_directory("rm_description")
    robotiq_share = get_package_share_directory("robotiq_description")
    ros_gz_sim_share = get_package_share_directory("ros_gz_sim")
    world_path = PathJoinSubstitution(
        [
            package_share,
            "worlds",
            LaunchConfiguration("world_file"),
        ]
    )
    resource_paths = [
        os.path.join(package_share, "models"),
        os.path.dirname(package_share),
        os.path.dirname(description_share),
        os.path.dirname(robotiq_share),
    ]

    xacro_path = PathJoinSubstitution(
        [
            package_share,
            "urdf",
            "rm65_b_robotiq_2f85.urdf.xacro",
        ]
    )
    state_description_xml = Command(
        [
            FindExecutable(name="xacro"),
            " ",
            xacro_path,
        ]
    )
    gazebo_description_xml = Command(
        [
            FindExecutable(name="xacro"),
            " ",
            xacro_path,
        ]
    )
    robot_description = {
        "robot_description": ParameterValue(
            state_description_xml,
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
                " ",
                world_path,
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

    camera_bridge = Node(
        package="ros_gz_bridge",
        executable="parameter_bridge",
        arguments=[
            "/industrial_camera/image@sensor_msgs/msg/Image[gz.msgs.Image",
            (
                "/industrial_camera/camera_info"
                "@sensor_msgs/msg/CameraInfo[gz.msgs.CameraInfo"
            ),
            (
                "/industrial_camera/depth_image"
                "@sensor_msgs/msg/Image[gz.msgs.Image"
            ),
            (
                "/industrial_camera/depth_camera_info"
                "@sensor_msgs/msg/CameraInfo[gz.msgs.CameraInfo"
            ),
        ],
        output="screen",
        condition=IfCondition(LaunchConfiguration("bridge_camera")),
    )

    spawn_robot = Node(
        package="ros_gz_sim",
        executable="create",
        arguments=[
            "-world",
            world_name,
            "-string",
            gazebo_description_xml,
            "-name",
            "rm65_b_robotiq_2f85",
        ],
        output="screen",
    )

    focus_robot = ExecuteProcess(
        cmd=[
            "ign",
            "service",
            "-s",
            "/gui/move_to",
            "--reqtype",
            "ignition.msgs.StringMsg",
            "--reptype",
            "ignition.msgs.Boolean",
            "--timeout",
            "30000",
            "--req",
            'data: "rm65_b_robotiq_2f85"',
        ],
        output="screen",
        condition=IfCondition(LaunchConfiguration("auto_focus_robot")),
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
            "robotiq_gripper_effort_controller",
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

    gripper_action_bridge = Node(
        package=package_name,
        executable="gripper_action_bridge.py",
        output="screen",
        parameters=[{"use_sim_time": True}],
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
    gripper_bridge_after_controllers = RegisterEventHandler(
        OnProcessExit(
            target_action=spawn_controllers,
            on_exit=[TimerAction(period=1.0, actions=[gripper_action_bridge])],
        )
    )
    focus_after_spawn = RegisterEventHandler(
        OnProcessExit(
            target_action=spawn_robot,
            on_exit=[TimerAction(period=3.0, actions=[focus_robot])],
        )
    )

    return LaunchDescription(
        [
            DeclareLaunchArgument("start_gazebo", default_value="true"),
            DeclareLaunchArgument("auto_focus_robot", default_value="false"),
            DeclareLaunchArgument("render_engine", default_value="ogre"),
            DeclareLaunchArgument(
                "world_file",
                default_value="industrial_pgs.sdf",
                description="World file installed in the bringup package worlds directory.",
            ),
            DeclareLaunchArgument("bridge_camera", default_value="true"),
            SetEnvironmentVariable(
                name="GZ_SIM_RESOURCE_PATH",
                value=[
                    os.pathsep.join(resource_paths),
                    os.pathsep,
                    EnvironmentVariable("GZ_SIM_RESOURCE_PATH", default_value=""),
                ],
            ),
            gazebo,
            robot_state_publisher,
            clock_bridge,
            camera_bridge,
            spawn_robot,
            unpause_after_spawn,
            controllers_after_unpause,
            gripper_bridge_after_controllers,
            focus_after_spawn,
        ]
    )
