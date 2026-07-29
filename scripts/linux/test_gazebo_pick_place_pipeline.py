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
  _world_to_base_position,
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
    return _world_to_base_position(world_position, mount_z)
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
  parser.add_argument(
    "--pick-offset",
    type=float,
    nargs=3,
    default=[0.0, 0.0, 0.02],
    help=(
      "Offset from visual object XYZ to the gripper TCP grasp pose."
    ),
  )
  parser.add_argument(
    "--place-offset",
    type=float,
    nargs=3,
    default=[0.0, 0.0, 0.08],
    help=(
      "Offset added to the place point. The default keeps the gripper TCP "
      "above the 0.30 m workbench before release."
    ),
  )
  parser.add_argument("--orientation", type=float, nargs=4, default=[0.0, 1.0, 0.0, 0.0])
  parser.add_argument("--frame-id", default="base_link")
  parser.add_argument("--object-id", default="gazebo_test_object")
  parser.add_argument("--target", default="gazebo_test_place")
  parser.add_argument("--approach-distance", type=float, default=0.10)
  parser.add_argument("--pregrasp-distance", type=float, default=0.04)
  parser.add_argument("--lift-height", type=float, default=0.12)
  parser.add_argument(
    "--place-clearance",
    type=float,
    default=0.15,
    help="Vertical approach/retreat clearance above the adjusted place pose.",
  )
  parser.add_argument(
    "--place-mode",
    choices=("near_pick", "area", "exact"),
    default="near_pick",
    help="Place near the pick area, anywhere in a requested area, or at an exact point.",
  )
  parser.add_argument(
    "--near-pick-place-offset",
    type=float,
    nargs=3,
    default=[0.10, -0.12, 0.0],
    metavar=("DX", "DY", "DZ"),
    help="Offset from the pick position used as the near-pick place area center.",
  )
  parser.add_argument(
    "--place-area-size",
    type=float,
    nargs=2,
    default=[0.24, 0.18],
    metavar=("SIZE_X", "SIZE_Y"),
    help="Place area size in metres when --place-mode area.",
  )
  parser.add_argument(
    "--place-area-samples",
    type=int,
    nargs=2,
    default=[3, 3],
    metavar=("NX", "NY"),
    help="Candidate grid samples across the place area.",
  )
  parser.add_argument("--speed", type=float, default=1.2)
  parser.add_argument(
    "--pick-descent-speed",
    type=float,
    default=1.2,
    help="Speed for the vertical descent from pick approach to pregrasp/grasp.",
  )
  parser.add_argument("--open-opening", type=float, default=0.0848)
  parser.add_argument("--close-opening", type=float, default=0.032)
  parser.add_argument("--gripper-speed", type=float, default=0.5)
  parser.add_argument("--gripper-force", type=float, default=1.0)
  parser.add_argument(
    "--pre-place-joints",
    type=float,
    nargs=6,
    default=None,
    metavar=("J1", "J2", "J3", "J4", "J5", "J6"),
    help="Optional joint-space staging pose before the place approach. Disabled by default.",
  )
  parser.add_argument(
    "--place-fallback-offsets",
    type=float,
    nargs=3,
    action="append",
    default=[
      [-0.08, 0.0, 0.0],
      [-0.14, 0.0, 0.0],
      [-0.08, -0.08, 0.0],
      [-0.14, -0.08, 0.0],
    ],
    metavar=("DX", "DY", "DZ"),
    help=(
      "Fallback offsets from the requested place position, in base_link metres. "
      "Used when the exact place approach is rejected by MoveIt."
    ),
  )
  parser.add_argument(
    "--no-place-fallbacks",
    action="store_true",
    help="Do not try fallback place positions if the requested place fails.",
  )
  parser.add_argument("--execute", action="store_true")
  parser.add_argument("--skip-bridge-check", action="store_true")
  parser.add_argument("--wait-bridge-seconds", type=float, default=30.0)
  parser.add_argument("--wait-ready-seconds", type=float, default=60.0)
  parser.add_argument("--pose-tolerance", type=float, default=0.03)
  parser.add_argument("--json-out", type=Path, default=None)
  return parser


def _add(left: list[float], right: list[float]) -> list[float]:
  return [left[index] + right[index] for index in range(3)]


def _linspace_span(size: float, samples: int) -> list[float]:
  if samples <= 1:
    return [0.0]
  step = float(size) / float(samples - 1)
  return [-float(size) / 2.0 + step * index for index in range(samples)]


def _candidate_key(candidate: dict) -> tuple[float, float]:
  position = candidate["position"]
  offset = candidate["area_offset"]
  reach_cost = position[0] * position[0] + position[1] * position[1]
  center_cost = offset[0] * offset[0] + offset[1] * offset[1]
  return (reach_cost, center_cost)


def _place_candidates(args: argparse.Namespace, place_position: list[float]) -> list[dict]:
  candidates: list[dict] = []
  seen: set[tuple[float, float, float]] = set()

  def add_candidate(label: str, offset: list[float]) -> None:
    position = _add(place_position, offset)
    key = tuple(round(value, 6) for value in position)
    if key in seen:
      return
    seen.add(key)
    candidates.append(
      {
        "label": label,
        "position": position,
        "area_offset": offset,
      }
    )

  if args.place_mode in ("area", "near_pick"):
    size_x, size_y = (float(value) for value in args.place_area_size)
    samples_x, samples_y = (int(value) for value in args.place_area_samples)
    if size_x < 0.0 or size_y < 0.0:
      raise ValueError("--place-area-size values must be non-negative")
    if samples_x <= 0 or samples_y <= 0:
      raise ValueError("--place-area-samples values must be positive")
    for dx in _linspace_span(size_x, samples_x):
      for dy in _linspace_span(size_y, samples_y):
        add_candidate("area", [dx, dy, 0.0])
    candidates.sort(key=_candidate_key)
  else:
    add_candidate("requested", [0.0, 0.0, 0.0])

  if not args.no_place_fallbacks:
    for offset in args.place_fallback_offsets:
      add_candidate("fallback", [float(value) for value in offset])

  return candidates


def _build_place_plan(bundle: Any, trace: TraceContext, args: argparse.Namespace, place_position: list[float], place_offset: list[float], orientation: list[float], label: str) -> tuple[dict, dict]:
  place_pose = {
    "position": _add(place_position, place_offset),
    "orientation": orientation,
    "frame_id": args.frame_id,
  }
  place_plan_input = {
    "place_pose": place_pose,
    "clearance": args.place_clearance,
  }
  _print_section(f"{label} place planning input", place_plan_input)
  place_plan_result = bundle.tool_runtime.invoke("robot.plan_place", place_plan_input, trace)
  place_plan_payload = _require_success(place_plan_result, f"{label} place plan")
  return place_plan_result.output["plan"], place_plan_payload


def _place_input(args: argparse.Namespace, place_plan: dict) -> dict:
  place_input = {
    "object_id": args.object_id,
    "target": args.target,
    "plan": place_plan,
    "speed": args.speed,
    "open_opening": args.open_opening,
    "gripper_speed": args.gripper_speed,
  }
  if args.pre_place_joints is not None:
    place_input["pre_approach_joints"] = [float(value) for value in args.pre_place_joints]
  return place_input


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
  ) or _world_to_base_position([0.24, 0.23, 0.322], args.robot_mount_z)
  requested_place_position = _position_from_args(
    args.place_position,
    args.place_world_position,
    args.robot_mount_z,
  ) or _world_to_base_position([0.50, 0.10, 0.32], args.robot_mount_z)
  place_position = (
    _add(pick_position, [float(value) for value in args.near_pick_place_offset])
    if args.place_mode == "near_pick"
    else requested_place_position
  )
  pick_offset = _float_triplet(args.pick_offset, "--pick-offset")
  place_offset = _float_triplet(args.place_offset, "--place-offset")
  orientation = _float_quad(args.orientation, "--orientation")
  if args.speed <= 0.0 or args.speed > 2.0:
    raise ValueError("--speed must be greater than 0 and at most 2")
  if args.pick_descent_speed <= 0.0 or args.pick_descent_speed > 2.0:
    raise ValueError("--pick-descent-speed must be greater than 0 and at most 2")
  place_candidates = _place_candidates(args, place_position)

  config = _load_agent_config(config_path, None if args.mock else endpoint)
  bundle = build_agent(config)
  trace = TraceContext()

  results: dict[str, Any] = {
    "trace": trace.to_dict(),
    "config": str(config_path),
    "endpoint": endpoint,
    "requested_place_position": requested_place_position,
    "selected_place_area_center": place_position,
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

  _print_section(
    "place candidates",
    [
      {
        "label": candidate["label"],
        "area_offset": candidate["area_offset"],
        "position": candidate["position"],
      }
      for candidate in place_candidates
    ],
  )

  first_place = place_candidates[0]
  place_plan, place_plan_payload = _build_place_plan(
    bundle,
    trace,
    args,
    first_place["position"],
    place_offset,
    orientation,
    "candidate 1",
  )
  results["place_plan"] = place_plan_payload
  results["place_candidates"] = place_candidates

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
      "descent_speed": args.pick_descent_speed,
      "open_opening": args.open_opening,
      "close_opening": args.close_opening,
      "gripper_speed": args.gripper_speed,
      "gripper_force": args.gripper_force,
    }
    _print_section("pick execution input", pick_input)
    pick = bundle.skill_runtime.invoke("robot.pick", pick_input, trace)
    results["pick"] = _require_success(pick, "pick execution")

    place = None
    results["place_attempts"] = []
    for index, candidate in enumerate(place_candidates, start=1):
      if index == 1:
        candidate_plan = place_plan
        candidate_plan_payload = place_plan_payload
      else:
        candidate_plan, candidate_plan_payload = _build_place_plan(
          bundle,
          trace,
          args,
          candidate["position"],
          place_offset,
          orientation,
          f"candidate {index}",
        )
      candidate_input = _place_input(args, candidate_plan)
      _print_section(f"candidate {index} place execution input", candidate_input)
      place = bundle.skill_runtime.invoke("robot.place", candidate_input, trace)
      results["place_attempts"].append(
        {
          "candidate": candidate,
          "plan": candidate_plan_payload,
          "result": {
            "success": place.success,
            "output": place.output,
            "error": place.error,
          },
        }
      )
      if place.success:
        place_plan = candidate_plan
        break
    if place is None:
      raise RuntimeError("No place candidates were generated.")
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
