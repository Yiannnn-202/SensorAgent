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
      BRIDGE_ROOT / "sensoragent_robot_bridge" / "trajectory_scaling.py",
      BRIDGE_ROOT / "launch" / "robot_bridge.launch.py",
      ROOT
      / "ros2_ws"
      / "src"
      / "sensoragent_rm65_b_bringup"
      / "launch"
      / "full_demo.launch.py",
      ROOT / "scripts" / "linux" / "test_gazebo_pick_pipeline.py",
      ROOT / "scripts" / "linux" / "test_gazebo_place_pipeline.py",
      ROOT / "scripts" / "linux" / "test_gazebo_pick_place_pipeline.py",
      ROOT / "scripts" / "linux" / "capture_gazebo_rgbd_frame.py",
      ROOT / "scripts" / "linux" / "run_gazebo_vision_actionlist_sim.py",
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
    self.assertIn('tip_link="robotiq_85_tcp"', srdf)
    self.assertIn('end_effector_link: "robotiq_85_tcp"', bridge_config)
    self.assertIn("orientation_tolerance: 0.20", bridge_config)
    self.assertIn("position_tolerance: 0.005", bridge_config)

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
