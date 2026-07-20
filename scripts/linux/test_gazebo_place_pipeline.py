#!/usr/bin/env python3
"""Exercise the SensorAgent 3D-position place pipeline against Gazebo.

Run Gazebo first:

  cd ~/SensorAgent
  bash scripts/linux/run_rm65_b_sim.sh

Then run a plan-only check:

  PYTHONPATH=src .venv312/bin/python scripts/linux/test_gazebo_place_pipeline.py \
    --world-position 0.50 0.10 0.32

Add --execute only when the target position and clearances look safe.
"""

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
  _base_position,
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


def _build_parser() -> argparse.ArgumentParser:
  parser = argparse.ArgumentParser(
    description=(
      "Test SensorAgent place planning and optional execution against "
      "the RM65-B + Robotiq Gazebo HTTP bridge."
    )
  )
  parser.add_argument(
    "--config",
    type=Path,
    default=ROOT / "configs" / "robot_sim.yaml",
    help="SensorAgent robot config. Defaults to configs/robot_sim.yaml.",
  )
  parser.add_argument("--endpoint", default=None)
  parser.add_argument("--mock", action="store_true")
  parser.add_argument(
    "--position",
    type=float,
    nargs=3,
    metavar=("X", "Y", "Z"),
    help="Place XYZ in base_link metres.",
  )
  parser.add_argument(
    "--world-position",
    type=float,
    nargs=3,
    metavar=("X", "Y", "Z"),
    help="Place XYZ in Gazebo/world metres.",
  )
  parser.add_argument("--robot-mount-z", type=float, default=0.18)
  parser.add_argument(
    "--position-offset",
    type=float,
    nargs=3,
    default=[0.0, 0.0, 0.02],
    metavar=("DX", "DY", "DZ"),
    help="Offset added to the input place position before planning.",
  )
  parser.add_argument(
    "--orientation",
    type=float,
    nargs=4,
    default=[0.0, 1.0, 0.0, 0.0],
    metavar=("QX", "QY", "QZ", "QW"),
    help="Place orientation quaternion in XYZW order.",
  )
  parser.add_argument("--frame-id", default="base_link")
  parser.add_argument("--object-id", default="gazebo_test_object")
  parser.add_argument("--target", default="gazebo_test_place")
  parser.add_argument("--clearance", type=float, default=0.08)
  parser.add_argument("--speed", type=float, default=2.0)
  parser.add_argument("--open-opening", type=float, default=0.0848)
  parser.add_argument("--gripper-speed", type=float, default=0.5)
  parser.add_argument("--execute", action="store_true")
  parser.add_argument("--skip-bridge-check", action="store_true")
  parser.add_argument("--wait-bridge-seconds", type=float, default=30.0)
  parser.add_argument("--wait-ready-seconds", type=float, default=60.0)
  parser.add_argument("--pose-tolerance", type=float, default=0.03)
  parser.add_argument("--json-out", type=Path, default=None)
  return parser


def _place_pose(args: argparse.Namespace) -> dict[str, Any]:
  position = _base_position(args)
  offset = _float_triplet(args.position_offset, "--position-offset")
  orientation = _float_quad(args.orientation, "--orientation")
  return {
    "position": [position[index] + offset[index] for index in range(3)],
    "orientation": orientation,
    "frame_id": args.frame_id,
  }


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

  config = _load_agent_config(config_path, None if args.mock else endpoint)
  bundle = build_agent(config)
  trace = TraceContext()

  results: dict[str, Any] = {
    "trace": trace.to_dict(),
    "config": str(config_path),
    "endpoint": endpoint,
    "executed": False,
  }

  place_pose = _place_pose(args)
  plan_input = {
    "place_pose": place_pose,
    "clearance": args.clearance,
  }
  _print_section("place planning input", plan_input)

  plan = bundle.tool_runtime.invoke("robot.plan_place", plan_input, trace)
  plan_payload = _require_success(plan, "place plan")
  place_plan = plan.output["plan"]
  results.update({"planning_input": plan_input, "plan": plan_payload})

  if not args.execute:
    _print_section(
      "execution skipped",
      {"reason": "Pass --execute to run robot.place in Gazebo."},
    )
  else:
    if not args.mock and not args.skip_bridge_check:
      _wait_for_ready(
        endpoint,
        args.wait_ready_seconds,
        ("move_action", "execute_trajectory", "gripper_cmd", "cartesian_path"),
      )
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
    results["executed"] = True
    results["place"] = _require_success(place, "place execution")

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
