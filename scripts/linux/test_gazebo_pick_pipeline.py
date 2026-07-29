#!/usr/bin/env python3
"""Exercise the SensorAgent 3D-position pick pipeline against Gazebo.

Run Gazebo first:

  cd ~/SensorAgent
  bash scripts/linux/run_rm65_b_sim.sh

Then run a plan-only check:

  PYTHONPATH=src .venv312/bin/python scripts/linux/test_gazebo_pick_pipeline.py \
    --world-position 0.42 -0.13 0.30

Add --execute only when the target position and clearances look safe.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

import requests


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
  sys.path.insert(0, str(SRC))

from sensoragent.agent import build_agent  # noqa: E402
from sensoragent.config import load_config  # noqa: E402
from sensoragent.schemas import TraceContext  # noqa: E402


def _float_triplet(values: list[float] | None, field: str) -> list[float] | None:
  if values is None:
    return None
  if len(values) != 3 or not all(math.isfinite(value) for value in values):
    raise ValueError(f"{field} must contain three finite numbers")
  return [float(value) for value in values]


def _float_quad(values: list[float], field: str) -> list[float]:
  if len(values) != 4 or not all(math.isfinite(value) for value in values):
    raise ValueError(f"{field} must contain four finite numbers")
  norm = math.sqrt(sum(value * value for value in values))
  if norm < 1e-9:
    raise ValueError(f"{field} must be a non-zero quaternion")
  return [float(value) / norm for value in values]


def _world_to_base_position(world_position: list[float], mount_z: float) -> list[float]:
  """Convert Gazebo world XYZ to base_link XYZ for the 180-degree robot mount."""

  return [
    -world_position[0],
    -world_position[1],
    world_position[2] - mount_z,
  ]


def _json_dump(value: Any) -> str:
  return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)


def _print_section(title: str, value: Any | None = None) -> None:
  print(f"\n=== {title} ===")
  if value is not None:
    print(_json_dump(value))


def _result_dict(result: Any) -> dict:
  return asdict(result)


def _require_success(result: Any, label: str) -> dict:
  payload = _result_dict(result)
  _print_section(label, payload)
  if not result.success:
    raise RuntimeError(f"{label} failed: {result.error}")
  return payload


def _http_get(endpoint: str, path: str, timeout: float = 4.0) -> dict:
  response = requests.get(f"{endpoint.rstrip('/')}{path}", timeout=timeout)
  response.raise_for_status()
  body = response.json()
  if not isinstance(body, dict):
    raise RuntimeError(f"{path} returned non-object JSON")
  return body


def _wait_for_bridge(endpoint: str, wait_seconds: float) -> None:
  deadline = time.monotonic() + wait_seconds
  last_error: Exception | None = None
  while time.monotonic() <= deadline:
    try:
      health = _http_get(endpoint, "/health", timeout=2.0)
      if health.get("success") is True:
        _print_section("bridge health", health)
        return
    except (requests.RequestException, ValueError, RuntimeError) as exc:
      last_error = exc
    time.sleep(1.0)
  raise RuntimeError(f"Bridge did not become healthy at {endpoint}: {last_error}")


def _wait_for_ready(
  endpoint: str,
  wait_seconds: float,
  required_interfaces: tuple[str, ...],
) -> None:
  deadline = time.monotonic() + wait_seconds
  last_ready: dict | None = None
  while time.monotonic() <= deadline:
    try:
      ready = _http_get(endpoint, "/ready", timeout=2.0)
      last_ready = ready
      state = ready.get("state", {})
      if not isinstance(state, dict):
        state = {}
      if all(state.get(name) is True for name in required_interfaces):
        _print_section("ros interface readiness", ready)
        return
    except requests.HTTPError as exc:
      if exc.response is not None and exc.response.status_code == 404:
        _print_section(
          "ros interface readiness",
          {
            "checked": False,
            "reason": "Bridge does not expose /ready. Rebuild sensoragent_robot_bridge to enable it.",
          },
        )
        return
    except (requests.RequestException, ValueError, RuntimeError):
      pass
    time.sleep(1.0)
  raise RuntimeError(
    "Required ROS interfaces did not become ready "
    f"{list(required_interfaces)}: {last_ready}"
  )


def _check_bridge(endpoint: str) -> dict:
  health = _http_get(endpoint, "/health")
  state = _http_get(endpoint, "/state")
  gripper = _http_get(endpoint, "/gripper/state")
  _print_section("bridge health", health)
  _print_section("initial robot state", state)
  _print_section("initial gripper state", gripper)
  if health.get("success") is not True:
    raise RuntimeError(f"Bridge health failed: {health}")
  if state.get("success") is not True:
    raise RuntimeError(f"Bridge state failed: {state}")
  return state


def _load_agent_config(config_path: Path, endpoint: str | None):
  config = load_config(config_path)
  if endpoint is None:
    return config
  robot = dict(config.integrations.robot)
  robot["endpoint"] = endpoint
  return replace(
    config,
    integrations=replace(config.integrations, robot=robot),
  )


def _base_position(args: argparse.Namespace) -> list[float]:
  base_position = _float_triplet(args.position, "--position")
  world_position = _float_triplet(args.world_position, "--world-position")
  if base_position is not None and world_position is not None:
    raise ValueError("Use either --position or --world-position, not both")
  if base_position is not None:
    return base_position
  if world_position is not None:
    return _world_to_base_position(world_position, args.robot_mount_z)
  return _world_to_base_position([0.42, -0.13, 0.28], args.robot_mount_z)


def _distance(left: list[float], right: list[float]) -> float:
  return math.sqrt(sum((left[index] - right[index]) ** 2 for index in range(3)))


def _verify_final_pose(state: dict, expected_position: list[float], tolerance: float) -> None:
  pose = state.get("state", {}).get("arm", {}).get("pose")
  if not isinstance(pose, dict) or not isinstance(pose.get("position"), list):
    _print_section(
      "final pose check",
      {
        "checked": False,
        "reason": "Bridge did not return a TF pose yet.",
      },
    )
    return
  measured = [float(value) for value in pose["position"][:3]]
  error = _distance(measured, expected_position)
  _print_section(
    "final pose check",
    {
      "checked": True,
      "expected_position": expected_position,
      "measured_position": measured,
      "error_m": error,
      "tolerance_m": tolerance,
      "within_tolerance": error <= tolerance,
    },
  )
  if error > tolerance:
    raise RuntimeError(
      f"Final TCP pose error {error:.4f} m exceeds tolerance {tolerance:.4f} m"
    )


def _run_arm_diagnostic(bundle: Any, trace: TraceContext, args: argparse.Namespace) -> dict:
  joints = [float(value) for value in args.arm_diagnostic_joints]
  diagnostic: dict[str, Any] = {
    "target_joints": joints,
    "speed": args.speed,
  }
  before = bundle.tool_runtime.invoke("robot.get_state", {}, trace)
  diagnostic["before"] = _require_success(before, "arm diagnostic state before")

  move = bundle.tool_runtime.invoke(
    "robot.move_joints",
    {"joints": joints, "speed": args.speed, "wait": True},
    trace,
  )
  diagnostic["move"] = _require_success(move, "arm diagnostic joint move")

  after = bundle.tool_runtime.invoke("robot.get_state", {}, trace)
  diagnostic["after"] = _require_success(after, "arm diagnostic state after")

  measured = (
    after.output
    .get("state", {})
    .get("arm", {})
    .get("joints")
  )
  if isinstance(measured, list) and len(measured) >= len(joints):
    max_error = max(
      abs(float(measured[index]) - joints[index])
      for index in range(len(joints))
    )
    diagnostic["max_joint_error_rad"] = max_error
    _print_section(
      "arm diagnostic joint check",
      {
        "target_joints": joints,
        "measured_joints": measured[: len(joints)],
        "max_joint_error_rad": max_error,
        "within_tolerance": max_error <= args.joint_tolerance,
        "tolerance_rad": args.joint_tolerance,
      },
    )
    if max_error > args.joint_tolerance:
      raise RuntimeError(
        f"Arm joint state did not reach target; max error {max_error:.4f} rad"
      )
  return diagnostic


def _build_parser() -> argparse.ArgumentParser:
  parser = argparse.ArgumentParser(
    description=(
      "Test SensorAgent top-down pick planning and optional execution against "
      "the RM65-B + Robotiq Gazebo HTTP bridge."
    )
  )
  parser.add_argument(
    "--config",
    type=Path,
    default=ROOT / "configs" / "robot_sim.yaml",
    help="SensorAgent robot config. Defaults to configs/robot_sim.yaml.",
  )
  parser.add_argument(
    "--endpoint",
    default=None,
    help="Robot HTTP bridge endpoint. Overrides the config endpoint when set.",
  )
  parser.add_argument(
    "--mock",
    action="store_true",
    help="Use configs/robot_mock.yaml and skip HTTP bridge checks.",
  )
  parser.add_argument(
    "--position",
    type=float,
    nargs=3,
    metavar=("X", "Y", "Z"),
    help="Object/grasp XYZ in base_link metres.",
  )
  parser.add_argument(
    "--world-position",
    type=float,
    nargs=3,
    metavar=("X", "Y", "Z"),
    help=(
      "Object/grasp XYZ in Gazebo/world metres. The script applies the "
      "180-degree robot mount yaw and subtracts --robot-mount-z from Z to "
      "produce base_link coordinates."
    ),
  )
  parser.add_argument(
    "--robot-mount-z",
    type=float,
    default=0.18,
    help="World-to-base_link Z offset in metres for world-position conversion.",
  )
  parser.add_argument(
    "--position-offset",
    type=float,
    nargs=3,
    default=[0.0, 0.0, 0.02],
    metavar=("DX", "DY", "DZ"),
    help=(
      "Offset from visual object XYZ to the gripper TCP grasp pose."
    ),
  )
  parser.add_argument(
    "--orientation",
    type=float,
    nargs=4,
    default=[0.0, 1.0, 0.0, 0.0],
    metavar=("QX", "QY", "QZ", "QW"),
    help="Grasp orientation quaternion in XYZW order.",
  )
  parser.add_argument("--frame-id", default="base_link")
  parser.add_argument("--object-id", default="gazebo_test_object")
  parser.add_argument("--approach-distance", type=float, default=0.10)
  parser.add_argument("--pregrasp-distance", type=float, default=0.04)
  parser.add_argument("--lift-height", type=float, default=0.12)
  parser.add_argument("--speed", type=float, default=1.2)
  parser.add_argument(
    "--pick-descent-speed",
    type=float,
    default=1.2,
    help="Speed for the vertical descent from approach to pregrasp/grasp.",
  )
  parser.add_argument("--open-opening", type=float, default=0.0848)
  parser.add_argument("--close-opening", type=float, default=0.032)
  parser.add_argument("--gripper-speed", type=float, default=0.5)
  parser.add_argument("--gripper-force", type=float, default=1.0)
  parser.add_argument(
    "--execute",
    action="store_true",
    help="Actually execute robot.pick in Gazebo. Without this, only plans.",
  )
  parser.add_argument(
    "--arm-diagnostic",
    action="store_true",
    help="Run an arm-only joint move before planning/picking.",
  )
  parser.add_argument(
    "--diagnose-only",
    action="store_true",
    help="Only run bridge/readiness checks and the arm diagnostic; skip pick planning.",
  )
  parser.add_argument(
    "--arm-diagnostic-joints",
    type=float,
    nargs=6,
    default=[0.25, 0.0, 0.0, 0.0, 0.0, 0.0],
    metavar=("J1", "J2", "J3", "J4", "J5", "J6"),
    help="Joint target used by --arm-diagnostic.",
  )
  parser.add_argument(
    "--joint-tolerance",
    type=float,
    default=0.02,
    help="Allowed joint-state error for --arm-diagnostic.",
  )
  parser.add_argument(
    "--skip-bridge-check",
    action="store_true",
    help="Skip direct /health and /state checks before invoking SensorAgent tools.",
  )
  parser.add_argument(
    "--wait-bridge-seconds",
    type=float,
    default=30.0,
    help="How long to wait for /health before failing.",
  )
  parser.add_argument(
    "--wait-ready-seconds",
    type=float,
    default=60.0,
    help="How long to wait for MoveIt, Cartesian path, and gripper action interfaces.",
  )
  parser.add_argument(
    "--min-grasp-z",
    type=float,
    default=0.03,
    help="Minimum allowed planned grasp Z in base_link metres.",
  )
  parser.add_argument(
    "--pose-tolerance",
    type=float,
    default=0.02,
    help="Allowed final TCP position error after execution.",
  )
  parser.add_argument(
    "--json-out",
    type=Path,
    default=None,
    help="Optional path to write the combined JSON result.",
  )
  return parser


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

  position = _base_position(args)
  position_offset = _float_triplet(args.position_offset, "--position-offset")
  orientation = _float_quad(args.orientation, "--orientation")
  if args.speed <= 0.0 or args.speed > 2.0:
    raise ValueError("--speed must be greater than 0 and at most 2")
  if args.pick_descent_speed <= 0.0 or args.pick_descent_speed > 2.0:
    raise ValueError("--pick-descent-speed must be greater than 0 and at most 2")

  config = _load_agent_config(config_path, None if args.mock else endpoint)
  bundle = build_agent(config)
  trace = TraceContext()

  results: dict[str, Any] = {
    "trace": trace.to_dict(),
    "config": str(config_path),
    "endpoint": endpoint,
    "executed": False,
  }

  if args.arm_diagnostic or args.diagnose_only:
    if not args.mock and not args.skip_bridge_check:
      _wait_for_ready(endpoint, args.wait_ready_seconds, ("move_action",))
    results["arm_diagnostic"] = _run_arm_diagnostic(bundle, trace, args)

  if args.diagnose_only:
    if args.json_out is not None:
      args.json_out.parent.mkdir(parents=True, exist_ok=True)
      args.json_out.write_text(_json_dump(results) + "\n", encoding="utf-8")
      print(f"\nWrote JSON result: {args.json_out}")
    return 0

  plan_input = {
    "pose_3d": position,
    "position_offset": position_offset,
    "orientation": orientation,
    "frame_id": args.frame_id,
    "approach_distance": args.approach_distance,
    "pregrasp_distance": args.pregrasp_distance,
    "lift_height": args.lift_height,
  }
  _print_section("planning input", plan_input)

  plan = bundle.tool_runtime.invoke("robot.plan_top_down_pick", plan_input, trace)
  plan_payload = _require_success(plan, "top-down pick plan")
  pick_plan = plan.output["plan"]

  grasp_z = float(pick_plan["grasp"]["position"][2])
  if grasp_z < args.min_grasp_z:
    raise RuntimeError(
      f"Refusing unsafe grasp Z {grasp_z:.4f} m below --min-grasp-z {args.min_grasp_z:.4f} m"
    )

  results.update({
    "planning_input": plan_input,
    "plan": plan_payload,
    "executed": False,
  })

  if not args.execute:
    _print_section(
      "execution skipped",
      {
        "reason": "Pass --execute to run robot.pick in Gazebo.",
        "safe_next_command": (
          "curl -X POST http://127.0.0.1:8765/stop "
          "-H 'Content-Type: application/json' -d '{}'"
        ),
      },
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
    pick_payload = _require_success(pick, "pick execution")
    results["executed"] = True
    results["pick"] = pick_payload

    state = bundle.tool_runtime.invoke("robot.get_state", {}, trace)
    state_payload = _require_success(state, "final robot state")
    results["final_state"] = state_payload
    _verify_final_pose(
      state.output,
      [float(value) for value in pick_plan["lift"]["position"]],
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
