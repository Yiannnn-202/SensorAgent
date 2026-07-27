#!/usr/bin/env python3
"""Drive the industrial pick-place ActionList against the Gazebo bridge.

Prerequisites:

  # terminal 1
  bash scripts/linux/run_rm65_b_sim.sh
  # terminal 2
  curl http://127.0.0.1:8765/health

Plan-only dry run:

  PYTHONPATH=src .venv312/bin/python scripts/linux/run_industrial_actionlist_sim.py \
    --utterance "pick block and place into target_area_3"

Execute the workflow against Gazebo (arm will move):

  PYTHONPATH=src .venv312/bin/python scripts/linux/run_industrial_actionlist_sim.py \
    --utterance "pick block and place into target_area_3" --execute

Use `--planner llm` to route the utterance through DeepSeek. Requires the usual
`SENSORAGENT_LLM_*` environment variables from `.env`.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
  sys.path.insert(0, str(SRC))

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
  sys.path.insert(0, str(SCRIPT_DIR))

from test_gazebo_pick_pipeline import (  # noqa: E402
  _check_bridge,
  _load_agent_config,
  _print_section,
  _wait_for_bridge,
  _wait_for_ready,
)

from sensoragent.agent import build_agent  # noqa: E402
from sensoragent.agent.planner import StaticPlanner  # noqa: E402
from sensoragent.schemas import (  # noqa: E402
  AgentRequest,
  PlanTargetKind,
  TraceContext,
)
from sensoragent.tools.robot.joint_poses import (  # noqa: E402
  DEFAULT_HOME_JOINTS,
  configured_joint_pose,
)


DEFAULT_UTTERANCE = "pick block and place into target_area_3"
DEFAULT_TARGET = "target_area_3"
DEFAULT_OBJECT_QUERY = "block"
ACTIONLIST_NAME = "industrial.pick_place_actionlist"
ARM_MOTION_SPEED = 1.2


def _json_dump(value: Any) -> str:
  return json.dumps(value, ensure_ascii=False, indent=2, default=str, sort_keys=True)


def _build_parser() -> argparse.ArgumentParser:
  parser = argparse.ArgumentParser(
    description="Run the industrial pick-place ActionList against Gazebo.",
  )
  parser.add_argument(
    "--utterance",
    default=DEFAULT_UTTERANCE,
    help="Operator utterance passed to the planner (LLM mode only).",
  )
  parser.add_argument(
    "--object-query",
    default=DEFAULT_OBJECT_QUERY,
    help="Static planner fallback: object_query to send to vision.config_detect.",
  )
  parser.add_argument(
    "--target",
    default=DEFAULT_TARGET,
    help="Static planner fallback: named place target (e.g. target_area_3).",
  )
  parser.add_argument(
    "--planner",
    choices=("static", "llm"),
    default="static",
    help="Planner mode. 'static' bypasses the LLM; 'llm' calls DeepSeek.",
  )
  parser.add_argument("--config", type=Path, default=ROOT / "configs" / "robot_sim.yaml")
  parser.add_argument("--endpoint", default=None)
  parser.add_argument("--execute", action="store_true", help="Actually move the robot.")
  parser.add_argument("--skip-bridge-check", action="store_true")
  parser.add_argument("--wait-bridge-seconds", type=float, default=30.0)
  parser.add_argument("--wait-ready-seconds", type=float, default=60.0)
  parser.add_argument(
    "--reset-home",
    action=argparse.BooleanOptionalAction,
    default=True,
    help="Send the arm to the zero-joints home before starting the workflow.",
  )
  parser.add_argument("--json-out", type=Path, default=None)
  return parser


def _plan_only_config(config):
  """Force the robot backend to fake so nothing moves during dry runs."""

  robot = dict(config.integrations.robot)
  robot["backend"] = "fake"
  return replace(config, integrations=replace(config.integrations, robot=robot))


def _actionlist_input(args: argparse.Namespace) -> dict:
  return {"object_query": args.object_query, "target": args.target}


def _dispatch_via_planner(bundle, args, actionlist_input):
  task = bundle.agent.run_task(args.utterance, actionlist_input)
  plan = task.plan.to_dict() if task.plan is not None else None
  _print_section("plan", plan)
  if task.plan is not None:
    if task.plan.target_kind != PlanTargetKind.ACTIONLIST:
      raise RuntimeError(
        f"Planner picked kind={task.plan.target_kind}, expected actionlist",
      )
    if task.plan.target != ACTIONLIST_NAME:
      raise RuntimeError(
        f"Planner picked target={task.plan.target}, expected {ACTIONLIST_NAME}",
      )
  return {
    "status": task.status.value if task.status is not None else None,
    "error": task.error,
    "result": task.result,
  }


def _dispatch_directly(bundle, actionlist_input):
  response = bundle.agent.handle(
    AgentRequest(
      actionlist=ACTIONLIST_NAME,
      input=actionlist_input,
      trace=TraceContext(),
    )
  )
  return {
    "success": response.success,
    "error": response.error,
    "result": response.result,
  }


def _reset_home(bundle, trace: TraceContext, home_joints: list[float]) -> None:
  """Send the arm to the zero-joints home so cartesian planning has a clean start."""

  result = bundle.tool_runtime.invoke(
    "robot.move_joints",
    {"joints": home_joints, "speed": ARM_MOTION_SPEED, "wait": True},
    trace,
  )
  _print_section("reset_home", {"success": result.success, "error": result.error})
  if not result.success:
    raise RuntimeError(f"reset_home failed: {result.error}")


def main() -> int:
  args = _build_parser().parse_args()
  config = _load_agent_config(args.config, args.endpoint)
  endpoint = str(config.integrations.robot.get("endpoint", "http://127.0.0.1:8765"))

  if args.execute:
    if not args.skip_bridge_check:
      _wait_for_bridge(endpoint, args.wait_bridge_seconds)
      _check_bridge(endpoint)
      _wait_for_ready(
        endpoint,
        args.wait_ready_seconds,
        ("move_action", "execute_trajectory", "cartesian_path", "gripper_cmd"),
      )
    active_config = config
  else:
    active_config = _plan_only_config(config)

  bundle = build_agent(
    active_config,
    planner_mode=("llm" if args.planner == "llm" else "static"),
  )

  # StaticPlanner defaults to mock.pick_place_actionlist; override for this script.
  if args.planner == "static":
    bundle.agent._planner = StaticPlanner(  # noqa: SLF001
      target=ACTIONLIST_NAME,
    )

  if args.execute and args.reset_home:
    home_joints = configured_joint_pose(
      config.scene.joint_poses,
      "home_joints",
      DEFAULT_HOME_JOINTS,
    )
    _reset_home(bundle, TraceContext(), home_joints)

  actionlist_input = _actionlist_input(args)
  _print_section(
    "run_industrial_actionlist_sim",
    {
      "planner": args.planner,
      "execute": args.execute,
      "utterance": args.utterance,
      "input": actionlist_input,
      "endpoint": endpoint if args.execute else "(fake)",
    },
  )

  if args.planner == "llm":
    summary = _dispatch_via_planner(bundle, args, actionlist_input)
  else:
    summary = _dispatch_directly(bundle, actionlist_input)

  _print_section("summary", summary)

  if args.json_out is not None:
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(_json_dump(summary), encoding="utf-8")
    print(f"wrote {args.json_out}")

  failed = summary.get("error") is not None
  if args.planner == "llm":
    failed = summary.get("status") != "succeeded"
  else:
    failed = not summary.get("success")
  return 1 if failed else 0


if __name__ == "__main__":
  sys.exit(main())
