#!/usr/bin/env python3
"""Test grasp reachability for every part in the current sorting scene."""

from __future__ import annotations

import argparse
from dataclasses import asdict, replace
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys
import time


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
  sys.path.insert(0, str(SRC))

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
  sys.path.insert(0, str(SCRIPT_DIR))

from collect_randomized_sorting_dataset import _set_pose  # noqa: E402
from test_gazebo_pick_pipeline import (  # noqa: E402
  _check_bridge,
  _wait_for_bridge,
  _wait_for_ready,
)

from sensoragent.agent import AgentBundle, build_agent  # noqa: E402
from sensoragent.config import SensorAgentConfig, load_config  # noqa: E402
from sensoragent.schemas import TraceContext  # noqa: E402


SCENE_PARTS = {
  "metal_roller_01": (0.1725, -0.225, 0.320, 0.0, math.pi / 2.0, 0.0),
  "metal_roller_02": (0.3475, -0.112, 0.320, 0.0, math.pi / 2.0, 0.0),
  "metal_roller_03": (0.2525, -0.030, 0.320, 0.0, math.pi / 2.0, 0.0),
  "metal_hex_nut_01": (0.2675, -0.215, 0.3125, 0.0, 0.0, -0.35),
  "metal_hex_nut_02": (0.1875, -0.128, 0.3125, 0.0, 0.0, 0.15),
  "metal_hex_nut_03": (0.3575, -0.035, 0.3125, 0.0, 0.0, 0.42),
  "metal_short_bolt_01": (0.3575, -0.232, 0.3325, math.pi, 0.0, -0.25),
  "metal_short_bolt_02": (0.2775, -0.142, 0.3325, math.pi, 0.0, 0.20),
  "metal_short_bolt_03": (0.1625, -0.045, 0.3325, math.pi, 0.0, -0.40),
}


def _default_output_path() -> Path:
  timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
  return ROOT / "logs" / "tasks" / f"sorting_grasp_matrix_{timestamp}.json"


def _result_payload(result) -> dict:
  return asdict(result)


def _prepare_robot(
  bundle: AgentBundle,
  config: SensorAgentConfig,
  *,
  execute: bool,
  settle_seconds: float,
) -> list[dict]:
  trace = TraceContext()
  stages: list[dict] = []
  stop = bundle.tool_runtime.invoke("robot.stop", {}, trace)
  stages.append({"stage": "stop", **_result_payload(stop)})
  if not stop.success:
    raise RuntimeError(f"Could not stop active robot motion: {stop.error}")

  opened = bundle.tool_runtime.invoke(
    "gripper.open",
    {"opening": 0.0848, "speed": 0.5},
    trace,
  )
  stages.append({"stage": "open_gripper", **_result_payload(opened)})
  if not opened.success:
    gripper_state = bundle.tool_runtime.invoke("gripper.get_state", {}, trace)
    stages.append(
      {"stage": "open_gripper_state_check", **_result_payload(gripper_state)}
    )
    opening = (
      (gripper_state.output or {}).get("state", {}).get("opening")
      if gripper_state.success
      else None
    )
    if not isinstance(opening, (int, float)) or float(opening) < 0.0818:
      raise RuntimeError(f"Could not open gripper safely: {opened.error}")

  observe = config.scene.joint_poses.get("observe_joints")
  if observe is not None:
    moved = bundle.tool_runtime.invoke(
      "robot.move_joints",
      {"joints": observe, "speed": 0.35, "wait": True},
      trace,
    )
    stages.append({"stage": "move_observe", **_result_payload(moved)})
    if not moved.success:
      raise RuntimeError(f"Could not move to observe_joints: {moved.error}")

  if execute:
    for entity, pose in SCENE_PARTS.items():
      _set_pose(entity, *pose)
    time.sleep(settle_seconds)
  return stages


def run_grasp_attempt(
  bundle: AgentBundle,
  config: SensorAgentConfig,
  instance_id: str,
  *,
  attempt: int,
) -> dict:
  trace = TraceContext()
  stages: list[dict] = []

  detected = bundle.tool_runtime.invoke(
    "vision.config_detect",
    {"query": instance_id},
    trace,
  )
  stages.append({"stage": "resolve_config_pose", **_result_payload(detected)})
  if not detected.success or not detected.output:
    return {
      "instance_id": instance_id,
      "attempt": attempt,
      "success": False,
      "failed_stage": "resolve_config_pose",
      "error": detected.error,
      "stages": stages,
    }

  object_data = detected.output
  planned = bundle.tool_runtime.invoke(
    "robot.plan_top_down_pick",
    {
      "pose_3d": object_data["pose_3d"],
      "orientation": object_data["grasp_orientation"],
      "position_offset": [0.0, 0.0, object_data["pick_offset_z"]],
      "approach_distance": 0.10,
      "pregrasp_distance": 0.08,
      "lift_height": 0.18,
    },
    trace,
  )
  stages.append({"stage": "plan_pick_waypoints", **_result_payload(planned)})
  if not planned.success or not planned.output:
    return {
      "instance_id": instance_id,
      "attempt": attempt,
      "success": False,
      "failed_stage": "plan_pick_waypoints",
      "error": planned.error,
      "stages": stages,
    }

  picked = bundle.skill_runtime.invoke(
    "robot.pick",
    {
      "plan": planned.output["plan"],
      "object_id": instance_id,
      "pre_approach_joints": config.scene.joint_poses.get(
        "pick_staging_joints"
      ),
      "speed": 0.35,
      "descent_speed": 0.25,
      "open_opening": object_data["release_opening"],
      "close_opening": object_data["grasp_opening"],
      "grasp_avoid_collisions": False,
      "gripper_force": 1.0,
    },
    trace,
  )
  stages.append({"stage": "pick_and_lift", **_result_payload(picked)})
  if not picked.success:
    return {
      "instance_id": instance_id,
      "attempt": attempt,
      "success": False,
      "failed_stage": "pick_and_lift",
      "error": picked.error,
      "stages": stages,
    }

  verified = bundle.skill_runtime.invoke(
    "robot.verify_grasp",
    {"min_opening": 0.002, "max_opening": 0.08},
    trace,
  )
  stages.append({"stage": "verify_grasp", **_result_payload(verified)})
  state = bundle.tool_runtime.invoke("robot.get_state", {}, trace)
  stages.append({"stage": "final_state", **_result_payload(state)})
  return {
    "instance_id": instance_id,
    "attempt": attempt,
    "success": verified.success,
    "failed_stage": None if verified.success else "verify_grasp",
    "error": verified.error,
    "gripper_opening": (
      (verified.output or {}).get("opening") if verified.output else None
    ),
    "stages": stages,
  }


def _active_config(config: SensorAgentConfig, execute: bool) -> SensorAgentConfig:
  if execute:
    return config
  robot = dict(config.integrations.robot)
  robot["backend"] = "fake"
  return replace(
    config,
    integrations=replace(config.integrations, robot=robot),
  )


def _parser() -> argparse.ArgumentParser:
  parser = argparse.ArgumentParser(
    description="Test grasp reachability for all nine sorting-scene parts.",
  )
  parser.add_argument(
    "--config",
    type=Path,
    default=ROOT / "configs" / "robot_sorting_sim.yaml",
  )
  parser.add_argument(
    "--instance",
    action="append",
    choices=tuple(SCENE_PARTS),
    help="Test only this instance; repeat the option to select several.",
  )
  parser.add_argument("--repeat", type=int, default=1)
  parser.add_argument("--settle-seconds", type=float, default=1.0)
  parser.add_argument(
    "--execute",
    action="store_true",
    help="Execute against Gazebo. Without this flag, use the fake backend.",
  )
  parser.add_argument("--wait-bridge-seconds", type=float, default=30.0)
  parser.add_argument("--wait-ready-seconds", type=float, default=60.0)
  parser.add_argument("--stop-on-failure", action="store_true")
  parser.add_argument("--json-out", type=Path, default=None)
  return parser


def main(argv: list[str] | None = None) -> int:
  args = _parser().parse_args(argv)
  if args.repeat < 1:
    raise ValueError("--repeat must be >= 1")
  if args.settle_seconds < 0.0:
    raise ValueError("--settle-seconds must be >= 0")

  config = load_config(args.config)
  endpoint = str(
    config.integrations.robot.get("endpoint", "http://127.0.0.1:8765")
  )
  if args.execute:
    _wait_for_bridge(endpoint, args.wait_bridge_seconds)
    _check_bridge(endpoint)
    _wait_for_ready(
      endpoint,
      args.wait_ready_seconds,
      ("move_action", "execute_trajectory", "cartesian_path", "gripper_cmd"),
    )

  active_config = _active_config(config, args.execute)
  output_path = args.json_out or _default_output_path()
  bundle = build_agent(active_config, log_path=output_path.with_suffix(".jsonl"))
  selected = args.instance or list(SCENE_PARTS)
  results: list[dict] = []
  stopped_early = False

  for instance_id in selected:
    for attempt in range(1, args.repeat + 1):
      preparation = _prepare_robot(
        bundle,
        active_config,
        execute=args.execute,
        settle_seconds=args.settle_seconds,
      )
      result = run_grasp_attempt(
        bundle,
        active_config,
        instance_id,
        attempt=attempt,
      )
      result["preparation"] = preparation
      results.append(result)
      print(
        json.dumps(
          {
            "instance_id": instance_id,
            "attempt": attempt,
            "success": result["success"],
            "failed_stage": result["failed_stage"],
            "error": result["error"],
          },
          ensure_ascii=False,
        ),
        flush=True,
      )
      if not result["success"] and args.stop_on_failure:
        stopped_early = True
        break
    if stopped_early:
      break

  final_preparation = _prepare_robot(
    bundle,
    active_config,
    execute=args.execute,
    settle_seconds=args.settle_seconds,
  )
  passed = sum(result["success"] for result in results)
  report = {
    "success": passed == len(results) and not stopped_early,
    "mode": "gazebo" if args.execute else "fake",
    "config": str(args.config),
    "selected_instances": selected,
    "repeat": args.repeat,
    "summary": {
      "passed": passed,
      "failed": len(results) - passed,
      "total": len(results),
      "stopped_early": stopped_early,
    },
    "results": results,
    "final_preparation": final_preparation,
  }
  output_path.parent.mkdir(parents=True, exist_ok=True)
  output_path.write_text(
    json.dumps(report, ensure_ascii=False, indent=2, default=str),
    encoding="utf-8",
  )
  print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
  print(f"report: {output_path}")
  return 0 if report["success"] else 1


if __name__ == "__main__":
  raise SystemExit(main())
