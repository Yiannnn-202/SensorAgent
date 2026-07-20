#!/usr/bin/env python3
"""Exercise a full SensorAgent pick -> place pipeline against Gazebo."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
  sys.path.insert(0, str(SCRIPT_DIR))

from test_gazebo_pick_pipeline import (  # noqa: E402
  ROOT,
  _check_bridge,
  _float_quad,
  _float_triplet,
  _json_dump,
  _load_agent_config,
  _print_section,
  _require_success,
  _verify_final_pose,
  _wait_for_bridge,
  _wait_for_ready,
)

from sensoragent.agent import build_agent  # noqa: E402
from sensoragent.config import load_config  # noqa: E402
from sensoragent.schemas import TraceContext  # noqa: E402


def _position_from_args(values: list[float] | None, world_values: list[float] | None, mount_z: float):
  base_position = _float_triplet(values, "--position")
  world_position = _float_triplet(world_values, "--world-position")
  if base_position is not None and world_position is not None:
    raise ValueError("Use either base_link position or world position, not both")
  if base_position is not None:
    return base_position
  if world_position is not None:
    return [world_position[0], world_position[1], world_position[2] - mount_z]
  return None


def _build_parser() -> argparse.ArgumentParser:
  parser = argparse.ArgumentParser(
    description="Test SensorAgent pick then place execution against Gazebo."
  )
  parser.add_argument("--config", type=Path, default=ROOT / "configs" / "robot_sim.yaml")
  parser.add_argument("--endpoint", default=None)
  parser.add_argument("--mock", action="store_true")
  parser.add_argument("--pick-position", type=float, nargs=3, metavar=("X", "Y", "Z"))
  parser.add_argument("--pick-world-position", type=float, nargs=3, metavar=("X", "Y", "Z"))
  parser.add_argument("--place-position", type=float, nargs=3, metavar=("X", "Y", "Z"))
  parser.add_argument("--place-world-position", type=float, nargs=3, metavar=("X", "Y", "Z"))
  parser.add_argument("--robot-mount-z", type=float, default=0.18)
  parser.add_argument("--pick-offset", type=float, nargs=3, default=[0.0, 0.0, 0.02])
  parser.add_argument("--place-offset", type=float, nargs=3, default=[0.0, 0.0, 0.02])
  parser.add_argument("--orientation", type=float, nargs=4, default=[0.0, 1.0, 0.0, 0.0])
  parser.add_argument("--frame-id", default="base_link")
  parser.add_argument("--object-id", default="gazebo_test_object")
  parser.add_argument("--target", default="gazebo_test_place")
  parser.add_argument("--approach-distance", type=float, default=0.10)
  parser.add_argument("--pregrasp-distance", type=float, default=0.03)
  parser.add_argument("--lift-height", type=float, default=0.10)
  parser.add_argument("--place-clearance", type=float, default=0.08)
  parser.add_argument("--speed", type=float, default=2.0)
  parser.add_argument("--open-opening", type=float, default=0.0848)
  parser.add_argument("--close-opening", type=float, default=0.02)
  parser.add_argument("--gripper-speed", type=float, default=0.5)
  parser.add_argument("--gripper-force", type=float, default=0.5)
  parser.add_argument("--execute", action="store_true")
  parser.add_argument("--skip-bridge-check", action="store_true")
  parser.add_argument("--wait-bridge-seconds", type=float, default=30.0)
  parser.add_argument("--wait-ready-seconds", type=float, default=60.0)
  parser.add_argument("--pose-tolerance", type=float, default=0.03)
  parser.add_argument("--json-out", type=Path, default=None)
  return parser


def _add(left: list[float], right: list[float]) -> list[float]:
  return [left[index] + right[index] for index in range(3)]


def main() -> int:
  parser = _build_parser()
  args = parser.parse_args()

  config_path = ROOT / "configs" / "robot_mock.yaml" if args.mock else args.config
  endpoint = args.endpoint
  if endpoint is None:
    loaded = load_config(config_path)
    endpoint = str(loaded.integrations.robot.get("endpoint", "http://127.0.0.1:8765"))

  if not args.mock and not args.skip_bridge_check:
    _wait_for_bridge(endpoint, args.wait_bridge_seconds)
    _check_bridge(endpoint)

  pick_position = _position_from_args(
    args.pick_position,
    args.pick_world_position,
    args.robot_mount_z,
  ) or [0.24, 0.23, 0.322 - args.robot_mount_z]
  place_position = _position_from_args(
    args.place_position,
    args.place_world_position,
    args.robot_mount_z,
  ) or [0.50, 0.10, 0.32 - args.robot_mount_z]
  pick_offset = _float_triplet(args.pick_offset, "--pick-offset")
  place_offset = _float_triplet(args.place_offset, "--place-offset")
  orientation = _float_quad(args.orientation, "--orientation")

  config = _load_agent_config(config_path, None if args.mock else endpoint)
  bundle = build_agent(config)
  trace = TraceContext()

  results: dict[str, Any] = {
    "trace": trace.to_dict(),
    "config": str(config_path),
    "endpoint": endpoint,
    "executed": False,
  }

  pick_plan_input = {
    "pose_3d": pick_position,
    "position_offset": pick_offset,
    "orientation": orientation,
    "frame_id": args.frame_id,
    "approach_distance": args.approach_distance,
    "pregrasp_distance": args.pregrasp_distance,
    "lift_height": args.lift_height,
  }
  _print_section("pick planning input", pick_plan_input)
  pick_plan_result = bundle.tool_runtime.invoke("robot.plan_top_down_pick", pick_plan_input, trace)
  results["pick_plan"] = _require_success(pick_plan_result, "top-down pick plan")
  pick_plan = pick_plan_result.output["plan"]

  place_pose = {
    "position": _add(place_position, place_offset),
    "orientation": orientation,
    "frame_id": args.frame_id,
  }
  place_plan_input = {
    "place_pose": place_pose,
    "clearance": args.place_clearance,
  }
  _print_section("place planning input", place_plan_input)
  place_plan_result = bundle.tool_runtime.invoke("robot.plan_place", place_plan_input, trace)
  results["place_plan"] = _require_success(place_plan_result, "place plan")
  place_plan = place_plan_result.output["plan"]

  if not args.execute:
    _print_section(
      "execution skipped",
      {"reason": "Pass --execute to run robot.pick followed by robot.place in Gazebo."},
    )
  else:
    if not args.mock and not args.skip_bridge_check:
      _wait_for_ready(
        endpoint,
        args.wait_ready_seconds,
        ("move_action", "execute_trajectory", "gripper_cmd", "cartesian_path"),
      )

    pick_input = {
      "object_id": args.object_id,
      "plan": pick_plan,
      "speed": args.speed,
      "open_opening": args.open_opening,
      "close_opening": args.close_opening,
      "gripper_speed": args.gripper_speed,
      "gripper_force": args.gripper_force,
    }
    _print_section("pick execution input", pick_input)
    pick = bundle.skill_runtime.invoke("robot.pick", pick_input, trace)
    results["pick"] = _require_success(pick, "pick execution")

    place_input = {
      "object_id": args.object_id,
      "target": args.target,
      "plan": place_plan,
      "speed": args.speed,
      "open_opening": args.open_opening,
      "gripper_speed": args.gripper_speed,
    }
    _print_section("place execution input", place_input)
    place = bundle.skill_runtime.invoke("robot.place", place_input, trace)
    results["place"] = _require_success(place, "place execution")
    results["executed"] = True

    state = bundle.tool_runtime.invoke("robot.get_state", {}, trace)
    results["final_state"] = _require_success(state, "final robot state")
    _verify_final_pose(
      state.output,
      [float(value) for value in place_plan["retreat"]["position"]],
      args.pose_tolerance,
    )

  if args.json_out is not None:
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(_json_dump(results) + "\n", encoding="utf-8")
    print(f"\nWrote JSON result: {args.json_out}")
  return 0


if __name__ == "__main__":
  try:
    raise SystemExit(main())
  except KeyboardInterrupt:
    print("\nInterrupted by user.", file=sys.stderr)
    raise SystemExit(130)
  except Exception as exc:
    print(f"\nERROR: {exc}", file=sys.stderr)
    raise SystemExit(1)
