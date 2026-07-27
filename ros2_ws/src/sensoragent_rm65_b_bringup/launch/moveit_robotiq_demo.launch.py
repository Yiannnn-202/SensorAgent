import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch_ros.actions import Node
from moveit_configs_utils import MoveItConfigsBuilder


def generate_launch_description():
    package_name = "sensoragent_rm65_b_bringup"
    moveit_config = (
        MoveItConfigsBuilder(
            "rm65_b_robotiq_2f85",
            package_name=package_name,
        )
        .robot_description(
            file_path="urdf/rm65_b_robotiq_2f85.urdf.xacro"
        )
        .robot_description_semantic(
            file_path="config/rm65_b_robotiq_2f85.srdf"
        )
        .robot_description_kinematics(file_path="config/kinematics.yaml")
        .joint_limits(file_path="config/joint_limits.yaml")
        .trajectory_execution(file_path="config/moveit_controllers.yaml")
        .planning_pipelines(pipelines=["ompl"])
        .to_moveit_configs()
    )

    move_group = Node(
        package="moveit_ros_move_group",
        executable="move_group",
        output="screen",
        parameters=[
            moveit_config.to_dict(),
            {
                "use_sim_time": True,
                "allow_trajectory_execution": True,
                "publish_robot_description_semantic": True,
                "publish_planning_scene": True,
                "publish_geometry_updates": True,
                "publish_state_updates": True,
                "publish_transforms_updates": True,
            },
        ],
    )

    rviz_config = os.path.join(
        get_package_share_directory("rm_65_config"),
        "config",
        "moveit.rviz",
    )
    rviz = Node(
        package="rviz2",
        executable="rviz2",
        output="log",
        arguments=["-d", rviz_config],
        parameters=[
            moveit_config.robot_description,
            moveit_config.robot_description_semantic,
            moveit_config.robot_description_kinematics,
            moveit_config.planning_pipelines,
            {"use_sim_time": True},
        ],
    )

    static_scene_publisher = Node(
        package="sensoragent_robot_bridge",
        executable="static_scene_publisher",
        output="screen",
        parameters=[
            {
                "use_sim_time": True,
                "base_frame": "base_link",
                "publish_period": 2.0,
            },
        ],
    )

    return LaunchDescription([move_group, static_scene_publisher, rviz])
