"""Static tests for the self-contained physical hardware workspace."""

from __future__ import annotations

import ast
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest import TestCase


ROOT = Path(__file__).resolve().parents[2]
ROS_SRC = ROOT / "ros2_ws" / "src"
ISLAND_ARM_ROOT = ROS_SRC / "island_arm"
HARDWARE_BRIDGE_ROOT = ROS_SRC / "sensoragent_hardware_bridge"


class HardwareStackIntegrationTest(TestCase):
  def test_required_driver_sources_are_integrated(self) -> None:
    expected_packages = {
      "arm_control",
      "arm_control_interfaces",
      "op_control",
      "op_control_interfaces",
      "rm_driver",
      "rm_ros_interfaces",
      "vision_dep",
      "vision_interfaces",
    }
    discovered_packages = {
      ET.parse(path).getroot().findtext("name")
      for path in ISLAND_ARM_ROOT.glob("*/package.xml")
    }

    self.assertEqual(discovered_packages, expected_packages)
    self.assertTrue((ROS_SRC / "rm_description" / "package.xml").is_file())

  def test_hardware_bridge_declares_integrated_runtime_dependencies(self) -> None:
    root = ET.parse(HARDWARE_BRIDGE_ROOT / "package.xml").getroot()
    dependencies = {element.text for element in root.findall("exec_depend")}

    self.assertTrue(
      {"rm_driver", "arm_control", "op_control", "vision_dep"}.issubset(
        dependencies
      )
    )

  def test_startup_uses_only_the_sensoragent_workspace(self) -> None:
    start_script = (ROOT / "scripts" / "linux" / "start_hardware_stack.sh").read_text(
      encoding="utf-8"
    )
    prepare_script = (
      ROOT / "scripts" / "linux" / "prepare_hardware_stack.sh"
    ).read_text(encoding="utf-8")

    self.assertNotIn("SENSORAGENT_ISLAND_ARM_SETUP", start_script)
    self.assertNotIn("Island-Arm/install", start_script)
    self.assertIn('"${ROOT}/ros2_ws/src/island_arm"', prepare_script)
    self.assertIn("--packages-up-to", prepare_script)

  def test_hardware_launch_forwards_motion_gate(self) -> None:
    launch_path = HARDWARE_BRIDGE_ROOT / "launch" / "hardware_stack.launch.py"
    launch_source = launch_path.read_text(encoding="utf-8")

    ast.parse(launch_source, filename=str(launch_path))
    self.assertIn(
      'DeclareLaunchArgument("allow_motion", default_value="false")',
      launch_source,
    )
    self.assertIn('ParameterValue(allow_motion, value_type=bool)', launch_source)
