"""Tests for the physical hardware bridge gripper fallbacks."""

from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType
from unittest import TestCase

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
ROS2_PACKAGE_ROOT = ROOT / "ros2_ws" / "src" / "sensoragent_hardware_bridge"
for path in (SRC, ROS2_PACKAGE_ROOT):
  if str(path) not in sys.path:
    sys.path.insert(0, str(path))


def _install_ros_stubs() -> None:
  import types

  rclpy = ModuleType("rclpy")
  rclpy.init = lambda *args, **kwargs: None
  rclpy.shutdown = lambda *args, **kwargs: None
  rclpy.spin = lambda *args, **kwargs: None

  node = ModuleType("rclpy.node")

  class _Node:
    def __init__(self, *args, **kwargs) -> None:
      del args, kwargs

  node.Node = _Node
  rclpy.node = node

  geometry_msgs = ModuleType("geometry_msgs")
  geometry_msgs_msg = ModuleType("geometry_msgs.msg")

  class _Pose:
    def __init__(self) -> None:
      self.position = types.SimpleNamespace(x=0.0, y=0.0, z=0.0)
      self.orientation = types.SimpleNamespace(x=0.0, y=0.0, z=0.0, w=1.0)

  geometry_msgs_msg.Pose = _Pose
  geometry_msgs.msg = geometry_msgs_msg

  std_msgs = ModuleType("std_msgs")
  std_msgs_msg = ModuleType("std_msgs.msg")
  std_msgs_msg.Empty = type("Empty", (), {})
  std_msgs.msg = std_msgs_msg

  arm_control_interfaces = ModuleType("arm_control_interfaces")
  arm_control_interfaces_srv = ModuleType("arm_control_interfaces.srv")
  for name in ("GetCurrentPose", "MoveJDeg", "MoveL", "MoveToPose"):
    setattr(arm_control_interfaces_srv, name, type(name, (), {"Request": type("Request", (), {})}))
  arm_control_interfaces.srv = arm_control_interfaces_srv

  op_control_interfaces = ModuleType("op_control_interfaces")
  op_control_interfaces_msg = ModuleType("op_control_interfaces.msg")
  op_control_interfaces_msg.OmniPickerState = type("OmniPickerState", (), {})
  op_control_interfaces_srv = ModuleType("op_control_interfaces.srv")
  for name in ("Close", "Open", "SetPosition"):
    setattr(op_control_interfaces_srv, name, type(name, (), {"Request": type("Request", (), {})}))
  op_control_interfaces.msg = op_control_interfaces_msg
  op_control_interfaces.srv = op_control_interfaces_srv

  sys.modules.setdefault("rclpy", rclpy)
  sys.modules.setdefault("rclpy.node", node)
  sys.modules.setdefault("geometry_msgs", geometry_msgs)
  sys.modules.setdefault("geometry_msgs.msg", geometry_msgs_msg)
  sys.modules.setdefault("std_msgs", std_msgs)
  sys.modules.setdefault("std_msgs.msg", std_msgs_msg)
  sys.modules.setdefault("arm_control_interfaces", arm_control_interfaces)
  sys.modules.setdefault("arm_control_interfaces.srv", arm_control_interfaces_srv)
  sys.modules.setdefault("op_control_interfaces", op_control_interfaces)
  sys.modules.setdefault("op_control_interfaces.msg", op_control_interfaces_msg)
  sys.modules.setdefault("op_control_interfaces.srv", op_control_interfaces_srv)


try:
  from sensoragent_hardware_bridge.bridge_node import HardwareBridge
except ModuleNotFoundError:
  _install_ros_stubs()
  from sensoragent_hardware_bridge.bridge_node import HardwareBridge


class HardwareBridgeGripperStateTest(TestCase):
  def test_open_target_is_detected_from_state(self) -> None:
    bridge = object.__new__(HardwareBridge)
    bridge._gripper_state = {"opening": 0.0848, "grasped": False}

    self.assertTrue(bridge._gripper_reached_target(0.0848, False))

  def test_closed_target_uses_grasped_or_near_zero_opening(self) -> None:
    bridge = object.__new__(HardwareBridge)
    bridge._gripper_state = {"opening": 0.001, "grasped": True}

    self.assertTrue(bridge._gripper_reached_target(0.0, True))

  def test_open_command_is_clamped_below_full_open(self) -> None:
    bridge = object.__new__(HardwareBridge)
    bridge._max_gripper_opening = 0.120
    bridge._max_gripper_open_command = 254.0 / 255.0

    position, target_opening = bridge._gripper_position_command(0.120, True)

    self.assertLess(position, 1.0)
    self.assertAlmostEqual(position, 254.0 / 255.0)
    self.assertAlmostEqual(target_opening, 0.120 * (254.0 / 255.0))

  def test_open_command_uses_meter_target_for_reach_check(self) -> None:
    bridge = object.__new__(HardwareBridge)
    bridge._max_gripper_opening = 0.120
    bridge._gripper_state = {"opening": 0.1196, "grasped": False}

    self.assertTrue(bridge._gripper_reached_target(0.1195, False))
