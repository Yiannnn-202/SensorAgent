#!/usr/bin/env python3
"""Run the industrial recovery DecisionTree against Gazebo with failure injection.

Default demo story:

  1. Pick the configured object.
  2. Inject a wrong-bin placement by resolving the first place target to another
     bin cell while keeping the requested target unchanged.
  3. Let vision.verify_object_in_bin classify the mismatch as WRONG_BIN.
  4. Re-detect the object at the injected wrong-bin pose, re-pick it, and place
     it into the requested target through industrial.recovery_pick_place_tree.

Run Gazebo first:

  bash scripts/linux/run_rm65_b_sim.sh

Then run the demo:

  PYTHONPATH=src .venv312/bin/python scripts/linux/run_gazebo_recovery_demo.py \
    --failure wrong-bin --object-query roller --target bin_cell_3 --wrong-target bin_cell_2 --execute
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
from sensoragent.schemas import ToolCall, ToolResult, TraceContext  # noqa: E402
from sensoragent.tools.base import Tool  # noqa: E402


TREE_NAME = "industrial.recovery_pick_place_tree"
HOME_JOINTS = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]


def _json_dump(value: Any) -> str:
  return json.dumps(value, ensure_ascii=False, indent=2, default=str, sort_keys=True)


def _build_parser() -> argparse.ArgumentParser:
  parser = argparse.ArgumentParser(
    description="Run a Gazebo industrial recovery-tree demo with deterministic failure injection.",
  )
  parser.add_argument("--object-query", default="roller")
  parser.add_argument("--target", default="bin_cell_3")
  parser.add_argument(
    "--failure",
    choices=("wrong-bin", "place-plan", "release", "none"),
    default="wrong-bin",
    help="Failure to inject before recovery. Use wrong-bin for the video demo.",
  )
  parser.add_argument(
    "--wrong-target",
    default="bin_cell_2",
    help="First placement target used only by --failure wrong-bin.",
  )
  parser.add_argument("--config", type=Path, default=ROOT / "configs" / "robot_sim.yaml")
  parser.add_argument("--endpoint", default=None)
  parser.add_argument("--execute", action="store_true", help="Actually move the Gazebo robot.")
  parser.add_argument("--skip-bridge-check", action="store_true")
  parser.add_argument("--wait-bridge-seconds", type=float, default=30.0)
  parser.add_argument("--wait-ready-seconds", type=float, default=60.0)
  parser.add_argument("--max-decision-nodes", type=int, default=100)
  parser.add_argument(
    "--reset-home",
    action=argparse.BooleanOptionalAction,
    default=True,
    help="Move the arm to all-zero joints before executing the demo.",
  )
  parser.add_argument("--json-out", type=Path, default=ROOT / "logs" / "tasks" / "recovery_demo.json")
  return parser


def _plan_only_config(config):
  """Force the robot backend to fake so the same demo can be dry-run safely."""

  robot = dict(config.integrations.robot)
  robot["backend"] = "fake"
  return replace(config, integrations=replace(config.integrations, robot=robot))


def _replace_tool(bundle, name: str, tool: Tool) -> None:
  bundle.tool_registry._tools[name] = tool  # noqa: SLF001


class _FailOnceTool:
  """Tool wrapper that fails once before delegating to the original tool."""

  def __init__(self, wrapped: Tool, *, error: str, output: dict | None = None) -> None:
    self.spec = wrapped.spec
    self._wrapped = wrapped
    self._error = error
    self._output = output
    self._failed = False

  def run(self, call: ToolCall) -> ToolResult:
    if not self._failed:
      self._failed = True
      return ToolResult(
        tool=self.spec.name,
        success=False,
        output=self._output,
        error=self._error,
      )
    return self._wrapped.run(call)


class _WrongBinResolveTool:
  """Resolve the first requested target to a wrong target pose."""

  def __init__(self, wrapped: Tool, *, requested_target: str, wrong_target: str, state: dict) -> None:
    self.spec = wrapped.spec
    self._wrapped = wrapped
    self._requested_target = requested_target
    self._wrong_target = wrong_target
    self._state = state
    self._used_wrong_target = False

  def run(self, call: ToolCall) -> ToolResult:
    target = call.input.get("target")
    if (
      not self._used_wrong_target
      and target == self._requested_target
      and self._wrong_target != self._requested_target
    ):
      self._used_wrong_target = True
      wrong_call = ToolCall(
        tool=call.tool,
        input={**call.input, "target": self._wrong_target},
        trace=call.trace,
      )
      result = self._wrapped.run(wrong_call)
      if result.success and result.output:
        place_pose = result.output.get("place_pose")
        self._state["misplaced_pose"] = place_pose
        self._state["wrong_target"] = self._wrong_target
        self._state["requested_target"] = self._requested_target
        output = dict(result.output)
        output["target"] = self._requested_target
        output["injected_wrong_target"] = self._wrong_target
        output["injected_wrong_place_pose"] = place_pose
        return ToolResult(tool=self.spec.name, success=True, output=output)
      return result
    return self._wrapped.run(call)


class _WrongBinVerifyTool:
  """Track when target-bin verification detects the injected wrong placement."""

  def __init__(self, wrapped: Tool, *, state: dict) -> None:
    self.spec = wrapped.spec
    self._wrapped = wrapped
    self._state = state

  def run(self, call: ToolCall) -> ToolResult:
    result = self._wrapped.run(call)
    if not result.success and result.error and "WRONG_BIN" in result.error:
      self._state["wrong_bin_detected"] = True
      self._state["wrong_bin_evidence"] = result.output
    return result


class _RecoveryConfigDetectTool:
  """After wrong-bin detection, report the object at the wrong-bin pose."""

  def __init__(self, wrapped: Tool, *, state: dict) -> None:
    self.spec = wrapped.spec
    self._wrapped = wrapped
    self._state = state

  def run(self, call: ToolCall) -> ToolResult:
    if self._state.get("wrong_bin_detected") and self._state.get("misplaced_pose"):
      pose = self._state["misplaced_pose"]
      position = pose.get("position") if isinstance(pose, dict) else None
      if isinstance(position, list) and len(position) >= 3:
        pose_3d = [float(position[0]), float(position[1]), float(position[2]), 0.0, 0.0, 0.0]
        return ToolResult(
          tool=self.spec.name,
          success=True,
          output={
            "found": True,
            "label": str(call.input.get("query", "recovered_object")),
            "confidence": 1.0,
            "object_id": "wrong_bin_recovery_target",
            "pose_3d": pose_3d,
            "source": "injected_wrong_bin_pose",
          },
        )
    return self._wrapped.run(call)


def _inject_failure(bundle, args: argparse.Namespace) -> dict:
  state: dict[str, Any] = {"failure": args.failure}
  if args.failure == "none":
    return state
  if args.failure == "wrong-bin":
    _replace_tool(
      bundle,
      "robot.resolve_place_target",
      _WrongBinResolveTool(
        bundle.tool_registry.get("robot.resolve_place_target"),
        requested_target=args.target,
        wrong_target=args.wrong_target,
        state=state,
      ),
    )
    _replace_tool(
      bundle,
      "vision.verify_object_in_bin",
      _WrongBinVerifyTool(
        bundle.tool_registry.get("vision.verify_object_in_bin"),
        state=state,
      ),
    )
    _replace_tool(
      bundle,
      "vision.config_detect",
      _RecoveryConfigDetectTool(
        bundle.tool_registry.get("vision.config_detect"),
        state=state,
      ),
    )
    return state
  if args.failure == "place-plan":
    _replace_tool(
      bundle,
      "robot.plan_place",
      _FailOnceTool(
        bundle.tool_registry.get("robot.plan_place"),
        error="PLACE_PLAN_FAILED: injected demo planning failure",
      ),
    )
    return state
  if args.failure == "release":
    _replace_tool(
      bundle,
      "gripper.open",
      _FailOnceTool(
        bundle.tool_registry.get("gripper.open"),
        error="RELEASE_FAILED: injected demo gripper-open failure",
      ),
    )
    return state
  raise ValueError(f"Unsupported failure mode: {args.failure}")


def _reset_home(bundle, trace: TraceContext) -> None:
  result = bundle.tool_runtime.invoke(
    "robot.move_joints",
    {"joints": HOME_JOINTS, "speed": 2.0, "wait": True},
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

  bundle = build_agent(active_config)
  injection_state = _inject_failure(bundle, args)
  trace = TraceContext()
  if args.execute and args.reset_home:
    _reset_home(bundle, trace)

  request_input = {
    "object_query": args.object_query,
    "target": args.target,
    "max_decision_nodes": args.max_decision_nodes,
  }
  _print_section(
    "recovery demo input",
    {
      "decision_tree": TREE_NAME,
      "execute": args.execute,
      "failure": args.failure,
      "object_query": args.object_query,
      "target": args.target,
      "wrong_target": args.wrong_target if args.failure == "wrong-bin" else None,
      "endpoint": endpoint if args.execute else "(fake)",
    },
  )
  tree = bundle.decision_trees[TREE_NAME]
  result = bundle.decision_tree_runtime.run(tree, request_input, trace)
  output = result.output or {}
  summary = {
    "success": result.success,
    "error": result.error,
    "failure_injection": injection_state,
    "classification": output.get("classification"),
    "recovery": output.get("recovery"),
    "bin_check": output.get("bin_check"),
    "last_failure": output.get("last_failure"),
    "result": output,
    "trace": trace.to_dict(),
    "nodes": [asdict(node) for node in result.nodes],
  }
  _print_section("recovery demo summary", summary)

  if args.json_out is not None:
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(_json_dump(summary), encoding="utf-8")
    print(f"wrote {args.json_out}")
  return 0 if result.success else 1


if __name__ == "__main__":
  raise SystemExit(main())
