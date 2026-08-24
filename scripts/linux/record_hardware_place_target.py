#!/usr/bin/env python3
"""Record a hardware place target from the current robot TCP pose.

Run this after manually moving the robot to a desired release pose. The script
reads the live `/state` response from the hardware bridge, extracts
`arm.pose`, and either prints a YAML snippet or updates a config file in place.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import requests
import yaml


ROOT = Path(__file__).resolve().parents[2]


def _fetch_pose(endpoint: str, timeout_seconds: float) -> dict:
  response = requests.get(f"{endpoint.rstrip('/')}/state", timeout=timeout_seconds)
  response.raise_for_status()
  payload = response.json()
  if not isinstance(payload, dict):
    raise ValueError("Robot bridge /state response must be a JSON object")
  pose = payload.get("state", {}).get("arm", {}).get("pose")
  if not isinstance(pose, dict):
    raise ValueError("Robot bridge /state response did not contain arm.pose")
  position = pose.get("position")
  orientation = pose.get("orientation")
  frame_id = pose.get("frame_id", "base_link")
  if not isinstance(position, list) or len(position) != 3:
    raise ValueError("arm.pose.position must be a 3-element list")
  if not isinstance(orientation, list) or len(orientation) != 4:
    raise ValueError("arm.pose.orientation must be a 4-element list")
  return {
    "position": [float(value) for value in position],
    "orientation": [float(value) for value in orientation],
    "frame_id": str(frame_id),
  }


def _update_config(config_path: Path, target: str, pose: dict) -> None:
  payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
  scene = payload.setdefault("scene", {})
  place_targets = scene.setdefault("place_targets", {})
  place_targets[target] = pose
  config_path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8")


def _render_snippet(target: str, pose: dict) -> str:
  return yaml.safe_dump(
    {
      "scene": {
        "place_targets": {
          target: pose,
        }
      }
    },
    sort_keys=False,
    allow_unicode=True,
  ).rstrip()


def main() -> int:
  parser = argparse.ArgumentParser(description="Record a hardware place target from /state.")
  parser.add_argument("target", help="Place target id, e.g. bin_cell_1")
  parser.add_argument(
    "--endpoint",
    default="http://127.0.0.1:8766",
    help="Robot bridge endpoint.",
  )
  parser.add_argument(
    "--config",
    type=Path,
    default=ROOT / "configs" / "robot_hardware_sensoragent_v1i_baseline.yaml",
    help="Config file to update when --in-place is set.",
  )
  parser.add_argument(
    "--in-place",
    action="store_true",
    help="Write the current pose back into --config.",
  )
  parser.add_argument(
    "--timeout",
    type=float,
    default=4.0,
    help="HTTP timeout for /state.",
  )
  args = parser.parse_args()

  pose = _fetch_pose(args.endpoint, args.timeout)
  if args.in_place:
    _update_config(args.config, args.target, pose)
    print(f"updated {args.config}: {args.target}")
    return 0

  print(_render_snippet(args.target, pose))
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
