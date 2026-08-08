#!/usr/bin/env python3
"""Run the config-driven verified route for the industrial sorting scene."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
  sys.path.insert(0, str(SRC))

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
  sys.path.insert(0, str(SCRIPT_DIR))

from test_gazebo_pick_pipeline import _check_bridge, _wait_for_bridge, _wait_for_ready  # noqa: E402

from sensoragent.agent import build_agent  # noqa: E402
from sensoragent.config import load_config  # noqa: E402
from sensoragent.schemas import AgentRequest, TraceContext  # noqa: E402


ACTIONLIST = "industrial.sorting_config_pick_place_actionlist"


def main() -> int:
  parser = argparse.ArgumentParser(description="Run the verified config-driven sorting route.")
  parser.add_argument("--config", type=Path, default=ROOT / "configs" / "robot_sorting_sim.yaml")
  parser.add_argument("--object-query", default="block")
  parser.add_argument("--target", default="bin_cell_5")
  parser.add_argument("--execute", action="store_true")
  args = parser.parse_args()

  config = load_config(args.config)
  endpoint = str(config.integrations.robot.get("endpoint", "http://127.0.0.1:8765"))
  if args.execute:
    _wait_for_bridge(endpoint, 30.0)
    _check_bridge(endpoint)
    _wait_for_ready(endpoint, 60.0, ("move_action", "execute_trajectory", "cartesian_path", "gripper_cmd"))

  active_config = config
  if not args.execute:
    robot = dict(config.integrations.robot)
    robot["backend"] = "fake"
    from dataclasses import replace
    active_config = replace(config, integrations=replace(config.integrations, robot=robot))

  bundle = build_agent(active_config)
  response = bundle.agent.handle(
    AgentRequest(
      actionlist=ACTIONLIST,
      input={"object_query": args.object_query, "target": args.target},
      trace=TraceContext(),
    )
  )
  print(json.dumps({"success": response.success, "error": response.error, "result": response.result}, ensure_ascii=False, indent=2, default=str))
  return 0 if response.success else 1


if __name__ == "__main__":
  raise SystemExit(main())
