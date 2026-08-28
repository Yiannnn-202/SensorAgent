"""Static tests for the ROS 2 simulation bridge package."""

from __future__ import annotations

import ast
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase


ROOT = Path(__file__).resolve().parents[2]
BRIDGE_ROOT = ROOT / "ros2_ws" / "src" / "sensoragent_robot_bridge"
if str(BRIDGE_ROOT) not in sys.path:
  sys.path.insert(0, str(BRIDGE_ROOT))

from sensoragent_robot_bridge.gripper_mapping import (
  closure_to_opening,
  opening_to_closure,
)
from sensoragent_robot_bridge.trajectory_scaling import (
  MAX_SPEED,
  scale_joint_trajectory_speed,
)


class RobotBridgePackageTest(TestCase):
  def test_python_sources_parse(self) -> None:
    paths = [
      BRIDGE_ROOT / "sensoragent_robot_bridge" / "bridge_node.py",
      BRIDGE_ROOT / "sensoragent_robot_bridge" / "gripper_mapping.py",
      BRIDGE_ROOT / "sensoragent_robot_bridge" / "planning_scene_publisher.py",
      BRIDGE_ROOT / "sensoragent_robot_bridge" / "scene_obstacles.py",
      BRIDGE_ROOT / "sensoragent_robot_bridge" / "trajectory_scaling.py",
      BRIDGE_ROOT / "launch" / "robot_bridge.launch.py",
      ROOT
      / "ros2_ws"
      / "src"
      / "sensoragent_rm65_b_bringup"
      / "launch"
      / "full_demo.launch.py",
      ROOT / "scripts" / "linux" / "agent_bridge_support.py",
      ROOT / "scripts" / "linux" / "run_competition_sorting_session.py",
      ROOT / "scripts" / "linux" / "capture_gazebo_rgbd_frame.py",
      ROOT / "scripts" / "linux" / "record_rm65_joint_pose.py",
    ]

    for path in paths:
      ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

  def test_package_manifest_declares_moveit_and_gripper_dependencies(self) -> None:
    root = ET.parse(BRIDGE_ROOT / "package.xml").getroot()
    dependencies = {element.text for element in root.findall("exec_depend")}

    self.assertIn("moveit_msgs", dependencies)
    self.assertIn("control_msgs", dependencies)
    self.assertIn("tf2_ros", dependencies)

  def test_moveit_targets_gripper_tcp_not_flange(self) -> None:
    bringup_root = ROOT / "ros2_ws" / "src" / "sensoragent_rm65_b_bringup"
    urdf = (bringup_root / "urdf" / "rm65_b_robotiq_2f85.urdf.xacro").read_text(
      encoding="utf-8"
    )
    srdf = (bringup_root / "config" / "rm65_b_robotiq_2f85.srdf").read_text(
      encoding="utf-8"
    )
    bridge_config = (BRIDGE_ROOT / "config" / "robot_bridge.yaml").read_text(
      encoding="utf-8"
    )

    self.assertIn('<link name="robotiq_85_tcp"/>', urdf)
    self.assertIn(
      '<xacro:arg name="robot_mount_rpy" default="0 0 3.141592653589793"/>',
      urdf,
    )
    self.assertIn('tip_link="robotiq_85_tcp"', srdf)
    self.assertIn('end_effector_link: "robotiq_85_tcp"', bridge_config)
    self.assertIn("orientation_tolerance: 0.50", bridge_config)
    self.assertIn("position_tolerance: 0.005", bridge_config)

  def test_bridge_adds_static_obstacles_to_planning_scene(self) -> None:
    bridge_source = (
      BRIDGE_ROOT / "sensoragent_robot_bridge" / "bridge_node.py"
    ).read_text(encoding="utf-8")

    self.assertIn("PlanningScene", bridge_source)
    self.assertIn("planning_scene_diff.world.collision_objects", bridge_source)
    self.assertIn("static_scene_collision_objects", bridge_source)

    obstacle_source = (
      BRIDGE_ROOT / "sensoragent_robot_bridge" / "scene_obstacles.py"
    ).read_text(encoding="utf-8")
    setup_source = (BRIDGE_ROOT / "setup.py").read_text(encoding="utf-8")
    moveit_launch = (
      ROOT
      / "ros2_ws"
      / "src"
      / "sensoragent_rm65_b_bringup"
      / "launch"
      / "moveit_robotiq_demo.launch.py"
    ).read_text(encoding="utf-8")

    self.assertIn("sensoragent_camera_left_post", obstacle_source)
    self.assertIn("sensoragent_camera_right_post", obstacle_source)
    self.assertIn("sensoragent_camera_crossbar", obstacle_source)
    self.assertIn("sensoragent_camera_body", obstacle_source)
    self.assertIn("sensoragent_sorting_workbench_top", obstacle_source)
    self.assertIn("sensoragent_sorting_bin_bottom", obstacle_source)
    self.assertIn("sensoragent_sorting_bin_wall_x_pos", obstacle_source)
    self.assertIn("sensoragent_sorting_bin_divider_y_back", obstacle_source)
    self.assertIn("center=(-0.34, -0.50, 0.39)", obstacle_source)
    self.assertIn("center=(-0.34, 0.50, 0.39)", obstacle_source)
    self.assertIn("center=(-0.34, 0.0, 0.94)", obstacle_source)
    self.assertIn("center=(-0.34, 0.0, 0.90)", obstacle_source)
    self.assertIn("center=(-0.42, 0.0, 0.085)", obstacle_source)
    self.assertIn("center=(-0.28, -0.21, 0.125)", obstacle_source)
    self.assertIn("size=(0.24, 0.24, 1.32)", obstacle_source)
    self.assertIn("size=(0.22, 1.24, 0.22)", obstacle_source)
    self.assertIn("size=(0.26, 0.22, 0.20)", obstacle_source)
    self.assertIn("size=(0.65, 0.90, 0.03)", obstacle_source)
    self.assertIn("size=(0.351, 0.351, 0.01)", obstacle_source)
    self.assertIn("TRANSIENT_LOCAL", bridge_source)
    self.assertIn("/scene/obstacles", bridge_source)
    self.assertIn("static_scene_publisher", setup_source)
    self.assertIn("static_scene_publisher", moveit_launch)

  def test_robotiq_fingers_use_high_friction(self) -> None:
    robotiq_path = (
      ROOT
      / "ros2_ws"
      / "src"
      / "robotiq_description"
      / "urdf"
      / "robotiq_2f_85_macro.urdf.xacro"
    )
    root = ET.parse(robotiq_path).getroot()
    mu_values = [float(node.text) for node in root.iter("mu") if node.text]
    mu2_values = [float(node.text) for node in root.iter("mu2") if node.text]

    self.assertGreaterEqual(len(mu_values), 4)
    self.assertGreaterEqual(len(mu2_values), 4)
    self.assertTrue(all(value >= 5.0 for value in mu_values))
    self.assertTrue(all(value >= 5.0 for value in mu2_values))

  def test_industrial_world_uses_stable_block_by_default(self) -> None:
    bringup_root = ROOT / "ros2_ws" / "src" / "sensoragent_rm65_b_bringup"
    world = (bringup_root / "worlds" / "industrial_pgs.sdf").read_text(
      encoding="utf-8"
    )
    block_model = (
      bringup_root / "models" / "sensoragent_part_block" / "model.sdf"
    ).read_text(encoding="utf-8")

    self.assertIn("model://sensoragent_part_block", world)
    self.assertIn("<name>block_01</name>", world)
    self.assertNotIn("model://sensoragent_part_roller", world)
    self.assertIn("<box><size>0.040 0.040 0.040</size></box>", block_model)
    self.assertIn("<mu>20.0</mu>", block_model)

  def test_sorting_world_has_three_reachable_instances_per_retained_class(self) -> None:
    bringup_root = ROOT / "ros2_ws" / "src" / "sensoragent_rm65_b_bringup"
    world_root = ET.parse(
      bringup_root / "worlds" / "industrial_sorting_metal_pgs.sdf"
    ).getroot()
    world = world_root.find("world")
    self.assertIsNotNone(world)

    model_names = {
      model.get("name")
      for model in world.findall("model")
      if model.get("name", "").startswith("metal_")
    }
    include_names = {
      include.findtext("name")
      for include in world.findall("include")
      if (include.findtext("name") or "").startswith("metal_")
    }
    part_names = model_names | include_names
    self.assertEqual(
      part_names,
      {
        f"metal_{category}_{index:02d}"
        for category in ("roller", "hex_nut", "short_bolt")
        for index in range(1, 4)
      },
    )

    part_poses = {
      node.get("name") or node.findtext("name"): node.findtext("pose")
      for node in [*world.findall("model"), *world.findall("include")]
      if (node.get("name") or node.findtext("name") or "").startswith("metal_")
    }
    self.assertEqual(
      [part_poses[f"metal_roller_{index:02d}"] for index in range(1, 4)],
      [
        "0.1725 -0.225 0.320 0 1.570796 0",
        "0.3475 -0.112 0.320 0 1.570796 0",
        "0.2525 -0.030 0.320 0 1.570796 0",
      ],
    )
    self.assertEqual(
      [part_poses[f"metal_hex_nut_{index:02d}"] for index in range(1, 4)],
      [
        "0.2675 -0.215 0.3125 0 0 -0.350000",
        "0.1875 -0.128 0.3125 0 0 0.150000",
        "0.3575 -0.035 0.3125 0 0 0.420000",
      ],
    )
    bolt_poses = [
      part_poses[f"metal_short_bolt_{index:02d}"]
      for index in range(1, 4)
    ]
    self.assertEqual(
      bolt_poses,
      [
        "0.3575 -0.232 0.3325 3.141593 0 -0.250000",
        "0.2775 -0.142 0.3325 3.141593 0 0.200000",
        "0.1625 -0.045 0.3325 3.141593 0 -0.400000",
      ],
    )

    for model_name in (
      "sensoragent_part_roller",
      "sensoragent_part_hex_nut",
      "sensoragent_part_short_bolt",
    ):
      model_source = (
        bringup_root / "models" / model_name / "model.sdf"
      ).read_text(encoding="utf-8")
      self.assertIn("<diffuse>0.58 0.59 0.60 1</diffuse>", model_source)

  def test_gripper_mapping_matches_simulated_action_semantics(self) -> None:
    maximum = 0.0848

    self.assertAlmostEqual(opening_to_closure(maximum, maximum), 0.0)
    self.assertAlmostEqual(opening_to_closure(0.0, maximum), maximum)
    self.assertAlmostEqual(closure_to_opening(0.0, maximum), maximum)
    self.assertAlmostEqual(closure_to_opening(maximum, maximum), 0.0)

  def test_cartesian_trajectory_speed_scaling(self) -> None:
    point = SimpleNamespace(
      time_from_start=SimpleNamespace(sec=1, nanosec=0),
      velocities=[2.0, -2.0],
      accelerations=[4.0, -4.0],
    )
    trajectory = SimpleNamespace(points=[point])

    scale_joint_trajectory_speed(trajectory, 0.5)

    self.assertEqual(point.time_from_start.sec, 2)
    self.assertEqual(point.time_from_start.nanosec, 0)
    self.assertEqual(point.velocities, [1.0, -1.0])
    self.assertEqual(point.accelerations, [1.0, -1.0])

  def test_cartesian_trajectory_accepts_maximum_speed_two(self) -> None:
    point = SimpleNamespace(
      time_from_start=SimpleNamespace(sec=2, nanosec=0),
      velocities=[1.0],
      accelerations=[1.0],
    )
    trajectory = SimpleNamespace(points=[point])

    scale_joint_trajectory_speed(trajectory, MAX_SPEED)

    self.assertEqual(point.time_from_start.sec, 1)
    self.assertEqual(point.time_from_start.nanosec, 0)
    self.assertEqual(point.velocities, [2.0])
    self.assertEqual(point.accelerations, [4.0])
