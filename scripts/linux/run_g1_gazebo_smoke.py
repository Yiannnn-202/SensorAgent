#!/usr/bin/env python3
"""Run the Phase G1 Gazebo smoke checks for the stable sorting baseline.

Without ``--execute`` this is a fake-backend smoke test for script/config
plumbing. With ``--execute`` it checks the running Gazebo/MoveIt bridge, executes
one config-driven sorting ActionList, then resets the scene and runs one grasp
matrix attempt.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, replace
from datetime import datetime, timezone
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
  sys.path.insert(0, str(SRC))

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
  sys.path.insert(0, str(SCRIPT_DIR))

from test_gazebo_pick_pipeline import _check_bridge, _wait_for_bridge, _wait_for_ready  # noqa: E402
from test_sorting_scene_grasp_matrix import _prepare_robot, run_grasp_attempt  # noqa: E402

from sensoragent.agent import build_agent  # noqa: E402
from sensoragent.config import SensorAgentConfig, load_config  # noqa: E402
from sensoragent.schemas import AgentRequest, TraceContext  # noqa: E402


ACTIONLIST = "industrial.sorting_config_pick_place_actionlist"


def _default_output_path() -> Path:
  timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
  return ROOT / "logs" / "tasks" / f"g1_gazebo_smoke_{timestamp}.json"


def _active_config(config: SensorAgentConfig, *, execute: bool) -> SensorAgentConfig:
  robot = dict(config.integrations.robot)
  if not execute:
    robot["backend"] = "fake"
  tools = replace(
    config.tools,
    enabled=[
      name
      for name in config.tools.enabled
      if not name.startswith("audio.")
    ],
  )
  skills = replace(
    config.skills,
    enabled=[
      name
      for name in config.skills.enabled
      if not name.startswith("audio.")
    ],
  )
  return replace(
    config,
    tools=tools,
    skills=skills,
    integrations=replace(config.integrations, robot=robot),
  )


def _run_actionlist(bundle, *, object_query: str, target: str) -> dict:
  trace = TraceContext()
  response = bundle.agent.handle(
    AgentRequest(
      actionlist=ACTIONLIST,
      input={"object_query": object_query, "target": target},
      trace=trace,
    )
  )
  return {
    "success": response.success,
    "error": response.error,
    "trace": trace.to_dict(),
    "result": response.result,
  }


def _parser() -> argparse.ArgumentParser:
  parser = argparse.ArgumentParser(
    description="Run the Phase G1 sorting Gazebo smoke test.",
  )
  parser.add_argument(
    "--config",
    type=Path,
    default=ROOT / "configs" / "robot_sorting_sim.yaml",
  )
  parser.add_argument(
    "--object-query",
    default="metal_hex_nut_02",
    help="Object used by the stable sorting ActionList smoke.",
  )
  parser.add_argument(
    "--target",
    default="bin_cell_5",
    help="Target cell used by the stable sorting ActionList smoke.",
  )
  parser.add_argument(
    "--matrix-instance",
    default="metal_hex_nut_02",
    help="Single instance used by the grasp-matrix smoke after scene reset.",
  )
  parser.add_argument("--execute", action="store_true")
  parser.add_argument("--wait-bridge-seconds", type=float, default=30.0)
  parser.add_argument("--wait-ready-seconds", type=float, default=60.0)
  parser.add_argument("--settle-seconds", type=float, default=1.0)
  parser.add_argument("--json-out", type=Path, default=None)
  return parser


def main(argv: list[str] | None = None) -> int:
  args = _parser().parse_args(argv)
  config = load_config(args.config)
  endpoint = str(config.integrations.robot.get("endpoint", "http://127.0.0.1:8765"))
  if args.execute:
    _wait_for_bridge(endpoint, args.wait_bridge_seconds)
    _check_bridge(endpoint)
    _wait_for_ready(
      endpoint,
      args.wait_ready_seconds,
      ("move_action", "execute_trajectory", "cartesian_path", "gripper_cmd"),
    )

  output_path = args.json_out or _default_output_path()
  active_config = _active_config(config, execute=args.execute)
  bundle = build_agent(active_config, log_path=output_path.with_suffix(".trace.jsonl"))

  actionlist_result = _run_actionlist(
    bundle,
    object_query=args.object_query,
    target=args.target,
  )

  matrix_preparation = _prepare_robot(
    bundle,
    active_config,
    execute=args.execute,
    settle_seconds=args.settle_seconds,
  )
  matrix_result = run_grasp_attempt(
    bundle,
    active_config,
    args.matrix_instance,
    attempt=1,
  )

  report = {
    "success": bool(actionlist_result["success"] and matrix_result["success"]),
    "mode": "gazebo" if args.execute else "fake",
    "config": str(args.config),
    "actionlist": {
      "name": ACTIONLIST,
      "object_query": args.object_query,
      "target": args.target,
      **actionlist_result,
    },
    "grasp_matrix_smoke": {
      "instance_id": args.matrix_instance,
      "preparation": [
        asdict(item) if hasattr(item, "__dataclass_fields__") else item
        for item in matrix_preparation
      ],
      "result": matrix_result,
    },
  }
  output_path.parent.mkdir(parents=True, exist_ok=True)
  output_path.write_text(
    json.dumps(report, ensure_ascii=False, indent=2, default=str),
    encoding="utf-8",
  )
  print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
  print(f"report: {output_path}")
  return 0 if report["success"] else 1


if __name__ == "__main__":
  raise SystemExit(main())
