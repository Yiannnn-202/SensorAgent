#!/usr/bin/env python3
"""Print a named RM65-B joint pose from one /joint_states sample."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import JointState


JOINT_ORDER = ("joint1", "joint2", "joint3", "joint4", "joint5", "joint6")


class JointStateCapture(Node):
  def __init__(self, topic: str) -> None:
    super().__init__("sensoragent_record_rm65_joint_pose")
    self.message: JointState | None = None
    self.create_subscription(JointState, topic, self._on_joint_state, 10)

  def _on_joint_state(self, message: JointState) -> None:
    self.message = message


def _extract_joints(message: JointState) -> list[float]:
  positions = dict(zip(message.name, message.position, strict=False))
  missing = [name for name in JOINT_ORDER if name not in positions]
  if missing:
    raise RuntimeError(f"/joint_states is missing RM65-B joints: {missing}")
  return [round(float(positions[name]), 6) for name in JOINT_ORDER]


def _format_yaml(name: str, joints: list[float]) -> str:
  return (
    "scene:\n"
    f"  robot_joint_order: [{', '.join(JOINT_ORDER)}]\n"
    "  joint_poses:\n"
    f"    {name}: [{', '.join(f'{value:.6f}' for value in joints)}]\n"
  )


def main() -> int:
  parser = argparse.ArgumentParser(
    description="Record one named RM65-B joint pose from /joint_states.",
  )
  parser.add_argument("name", help="Pose name, e.g. observe_joints or place_staging_joints.")
  parser.add_argument("--topic", default="/joint_states")
  parser.add_argument("--timeout", type=float, default=5.0)
  parser.add_argument(
    "--format",
    choices=("yaml", "json"),
    default="yaml",
    help="Output format. YAML is ready to paste under configs/*.",
  )
  parser.add_argument(
    "--out",
    type=Path,
    default=None,
    help="Optional file path for the printed snippet.",
  )
  args = parser.parse_args()

  rclpy.init()
  node = JointStateCapture(args.topic)
  try:
    deadline = time.monotonic() + args.timeout
    while time.monotonic() < deadline and node.message is None:
      rclpy.spin_once(node, timeout_sec=0.1)
    if node.message is None:
      raise TimeoutError(f"Timed out waiting for {args.topic}")

    joints = _extract_joints(node.message)
    if args.format == "json":
      output = json.dumps(
        {
          "robot_joint_order": list(JOINT_ORDER),
          "joint_poses": {args.name: joints},
        },
        ensure_ascii=False,
        indent=2,
      )
    else:
      output = _format_yaml(args.name, joints)

    if args.out is not None:
      args.out.parent.mkdir(parents=True, exist_ok=True)
      args.out.write_text(output + "\n", encoding="utf-8")
    print(output)
    return 0
  finally:
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
  raise SystemExit(main())
