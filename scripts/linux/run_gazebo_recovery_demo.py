#!/usr/bin/env python3
"""Run the industrial recovery DecisionTree against Gazebo with failure injection.

Default demo story:

  1. Pick the configured object.
  2. Inject a wrong placement by resolving the first place target to another
     bin cell or a reachable tabletop pose while keeping the requested target
     unchanged.
  3. Let vision.verify_object_in_bin classify the mismatch as WRONG_BIN.
  4. Re-detect the object at the injected wrong-bin pose, re-pick it, and place
     it into the requested target through industrial.recovery_pick_place_tree.

Run Gazebo first:

  bash scripts/linux/run_rm65_b_sim.sh

Then run the demo:

  PYTHONPATH=src .venv312/bin/python scripts/linux/run_gazebo_recovery_demo.py \
    --failure wrong-table --object-query roller --target target_area_3 --execute
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import fields, is_dataclass, replace
from enum import Enum
from pathlib import Path
from types import MappingProxyType
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
from run_gazebo_vision_actionlist_sim import _capture_frame, _frame_manifest  # noqa: E402

from sensoragent.agent import build_agent  # noqa: E402
from sensoragent.schemas import ToolCall, ToolResult, TraceContext  # noqa: E402
from sensoragent.tools.base import Tool  # noqa: E402


TREE_NAME = "industrial.recovery_pick_place_tree"
HOME_JOINTS = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
TABLETOP_PLACE_POSE = {
  "position": [0.28, 0.22, 0.20],
  "orientation": [0.9962, -0.0872, 0.0, 0.0],
  "frame_id": "base_link",
}
TABLETOP_OBJECT_POSE_3D = [0.28, 0.22, 0.142, 0.0, 0.0, 0.0]


def _json_dump(value: Any) -> str:
  return json.dumps(value, ensure_ascii=False, indent=2, default=str, sort_keys=True)


def _json_safe(value: Any, active: set[int] | None = None) -> Any:
  """Convert dataclasses and containers to JSON-safe values without following cycles."""

  if value is None or isinstance(value, (str, int, float, bool)):
    return value
  if isinstance(value, Enum):
    return value.value

  if active is None:
    active = set()

  if is_dataclass(value) and not isinstance(value, type):
    value_id = id(value)
    if value_id in active:
      return f"<recursive {type(value).__name__}>"
    active.add(value_id)
    try:
      return {field.name: _json_safe(getattr(value, field.name), active) for field in fields(value)}
    finally:
      active.remove(value_id)

  if isinstance(value, dict | MappingProxyType):
    value_id = id(value)
    if value_id in active:
      return "<recursive dict>"
    active.add(value_id)
    try:
      return {
        key if isinstance(key, str) else str(_json_safe(key, active)): _json_safe(item, active)
        for key, item in value.items()
      }
    finally:
      active.remove(value_id)

  if isinstance(value, list | tuple | set | frozenset):
    value_id = id(value)
    if value_id in active:
      return f"<recursive {type(value).__name__}>"
    active.add(value_id)
    try:
      return [_json_safe(item, active) for item in value]
    finally:
      active.remove(value_id)

  return str(value)


def _build_parser() -> argparse.ArgumentParser:
  parser = argparse.ArgumentParser(
    description="Run a Gazebo industrial recovery-tree demo with deterministic failure injection.",
  )
  parser.add_argument("--object-query", default="roller")
  parser.add_argument("--target", default="target_area_3")
  parser.add_argument(
    "--failure",
    choices=("wrong-bin", "wrong-table", "place-plan", "release", "none"),
    default="wrong-bin",
    help="Failure to inject before recovery. Use wrong-table for an easier video demo.",
  )
  parser.add_argument(
    "--wrong-target",
    default="target_area_2",
    help="First placement target used only by --failure wrong-bin.",
  )
  parser.add_argument("--config", type=Path, default=ROOT / "configs" / "robot_sim.yaml")
  parser.add_argument("--endpoint", default=None)
  parser.add_argument("--execute", action="store_true", help="Actually move the Gazebo robot.")
  parser.add_argument("--skip-bridge-check", action="store_true")
  parser.add_argument("--wait-bridge-seconds", type=float, default=30.0)
  parser.add_argument("--wait-ready-seconds", type=float, default=60.0)
  parser.add_argument("--frame-dir", type=Path, default=ROOT / "logs" / "vision" / "recovery_latest")
  parser.add_argument(
    "--capture-recovery-frame",
    action=argparse.BooleanOptionalAction,
    default=True,
    help="Capture a fresh RGB-D frame before wrong-table recovery re-detection.",
  )
  parser.add_argument(
    "--recovery-vision-radius",
    type=float,
    default=0.12,
    help="Maximum base-frame distance from the expected wrong-table drop pose for YOLOE recovery detections.",
  )
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


def _vision_backend(config: Any) -> str:
  return str(config.integrations.vision.get("backend", "yoloe")).casefold().replace("-", "_")


def _recovery_vision_queries(query: object) -> list[str]:
  base = str(query or "").strip()
  queries = [base] if base else []
  if "roller" in base.casefold() or "滚柱" in base:
    queries.extend([
      "red roller",
      "red cylinder",
      "red cylindrical object",
      "blue roller",
      "blue cylinder",
      "cylinder",
      "metal cylinder",
      "industrial part",
    ])
  for fallback in ("object", "part"):
    queries.append(fallback)

  result: list[str] = []
  seen: set[str] = set()
  for item in queries:
    normalized = item.strip()
    key = normalized.casefold()
    if normalized and key not in seen:
      result.append(normalized)
      seen.add(key)
  return result


def _distance_3d(left: list[float], right: list[float]) -> float:
  return math.sqrt(sum((float(left[index]) - float(right[index])) ** 2 for index in range(3)))


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


class _WrongTableResolveTool:
  """Resolve the first requested target to a reachable tabletop pose."""

  def __init__(
    self,
    wrapped: Tool,
    *,
    requested_target: str,
    state: dict,
  ) -> None:
    self.spec = wrapped.spec
    self._wrapped = wrapped
    self._requested_target = requested_target
    self._state = state
    self._used_table_pose = False

  def run(self, call: ToolCall) -> ToolResult:
    target = call.input.get("target")
    if not self._used_table_pose and target == self._requested_target:
      self._used_table_pose = True
      place_pose = dict(TABLETOP_PLACE_POSE)
      observed_pose = list(TABLETOP_OBJECT_POSE_3D)
      self._state["misplaced_pose"] = place_pose
      self._state["recovery_observed_pose_3d"] = observed_pose
      self._state["wrong_target"] = "tabletop"
      self._state["requested_target"] = self._requested_target
      return ToolResult(
        tool=self.spec.name,
        success=True,
        output={
          "target": self._requested_target,
          "place_pose": place_pose,
          "injected_wrong_target": "tabletop",
          "injected_wrong_place_pose": place_pose,
          "injected_observed_object_pose_3d": observed_pose,
        },
      )
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

  def __init__(
    self,
    wrapped: Tool,
    *,
    state: dict,
    open_vocab_tool: Tool | None = None,
    frame_dir: Path | None = None,
    config: Any | None = None,
    use_live_vision: bool = False,
    capture_frame: bool = True,
    search_radius: float = 0.12,
  ) -> None:
    self.spec = wrapped.spec
    self._wrapped = wrapped
    self._state = state
    self._open_vocab_tool = open_vocab_tool
    self._frame_dir = frame_dir
    self._config = config
    self._use_live_vision = use_live_vision
    self._capture_frame = capture_frame
    self._search_radius = float(search_radius)

  def run(self, call: ToolCall) -> ToolResult:
    if self._state.get("wrong_bin_detected") and self._state.get("misplaced_pose"):
      if self._use_live_vision and self._open_vocab_tool is not None and self._frame_dir is not None:
        backend = _vision_backend(self._config)
        self._state["recovery_vision_backend"] = backend
        if backend != "yoloe":
          return ToolResult(
            tool=self.spec.name,
            success=False,
            error=f"RECOVERY_VISION_FAILED: wrong-table recovery requires YOLOE, got {backend}",
          )
        manifest = _capture_frame(self._frame_dir) if self._capture_frame else _frame_manifest(self._frame_dir)
        self._state["recovery_vision_manifest"] = manifest
        attempts: list[dict[str, Any]] = []
        result = None
        selected_output = None
        selected_distance = None
        expected_pose = self._state.get("recovery_observed_pose_3d")
        t_base_camera = manifest.get("T_base_camera") or self._config.integrations.vision.get("T_base_camera")
        t_world_camera = manifest.get("T_world_camera")
        for query in _recovery_vision_queries(call.input.get("query", "recovered_object")):
          for box_threshold, text_threshold in ((0.25, 0.15), (0.15, 0.10), (0.08, 0.05)):
            vision_input = {
              "query": query,
              "image_path": manifest["image_path"],
              "depth_path": manifest["depth_path"],
              "camera_info_path": manifest["camera_info_path"],
              "T_base_camera": t_base_camera,
              "T_world_camera": t_world_camera,
              "world_frame": manifest.get("world_frame", "world"),
              "box_threshold": box_threshold,
              "text_threshold": text_threshold,
            }
            result = self._open_vocab_tool.run(
              ToolCall(tool=self._open_vocab_tool.spec.name, input=vision_input, trace=call.trace)
            )
            attempt = {
              "query": query,
              "box_threshold": box_threshold,
              "text_threshold": text_threshold,
              "success": result.success,
              "error": result.error,
            }
            if result.output:
              attempt["confidence"] = result.output.get("confidence")
              attempt["pose_3d"] = result.output.get("pose_3d")
              if isinstance(expected_pose, list) and isinstance(result.output.get("pose_3d"), list):
                attempt["distance_from_expected_m"] = _distance_3d(result.output["pose_3d"], expected_pose)
            attempts.append(attempt)
            if result.success and result.output:
              candidate = dict(result.output)
              pose_3d = candidate.get("pose_3d")
              if not isinstance(pose_3d, list) or len(pose_3d) < 3:
                continue
              distance = (
                _distance_3d(pose_3d, expected_pose)
                if isinstance(expected_pose, list) and len(expected_pose) >= 3
                else 0.0
              )
              if distance > self._search_radius:
                attempt["rejected_reason"] = "outside_recovery_search_radius"
                continue
              if selected_output is None or distance < float(selected_distance):
                selected_output = candidate
                selected_distance = distance
        self._state["recovery_vision_attempts"] = attempts
        self._state["recovery_vision_search_radius"] = self._search_radius
        if selected_output is not None:
          output = selected_output
          if not isinstance(output.get("pose_3d"), list) or len(output["pose_3d"]) < 3:
            self._state["recovery_vision"] = {
              "used": True,
              "success": False,
              "error": "YOLOE did not return pose_3d",
              "output": output,
              "attempts": attempts,
            }
            return ToolResult(
              tool=self.spec.name,
              success=False,
              output=output,
              error="RECOVERY_VISION_FAILED: YOLOE did not return pose_3d",
            )
          output["source"] = "live_recovery_vision"
          self._state["recovery_vision"] = {
            "used": True,
            "success": True,
            "backend": backend,
            "query": output.get("label"),
            "pose_3d": output.get("pose_3d"),
            "confidence": output.get("confidence"),
            "distance_from_expected_m": selected_distance,
            "attempts": attempts,
          }
          return ToolResult(tool=self.spec.name, success=True, output=output)
        rejected = [
          attempt
          for attempt in attempts
          if attempt.get("success") and attempt.get("rejected_reason") == "outside_recovery_search_radius"
        ]
        if rejected:
          error = (
            "YOLOE detections were outside recovery search radius "
            f"{self._search_radius:.3f} m"
          )
          self._state["recovery_vision"] = {
            "used": True,
            "success": False,
            "error": error,
            "attempts": attempts,
          }
          return ToolResult(
            tool=self.spec.name,
            success=False,
            output={"attempts": attempts},
            error=f"RECOVERY_VISION_FAILED: {error}",
          )
        self._state["recovery_vision"] = {
          "used": True,
          "success": False,
          "error": result.error if result is not None else "YOLOE was not invoked",
          "output": result.output if result is not None else None,
          "attempts": attempts,
        }
        return ToolResult(
          tool=self.spec.name,
          success=False,
          output=result.output if result is not None else None,
          error=f"RECOVERY_VISION_FAILED: {result.error if result is not None else 'YOLOE was not invoked'}",
        )

      pose = self._state["misplaced_pose"]
      recovery_pose = self._state.get("recovery_observed_pose_3d")
      position = pose.get("position") if isinstance(pose, dict) else None
      if isinstance(recovery_pose, list) and len(recovery_pose) >= 3:
        pose_3d = [float(value) for value in recovery_pose[:6]]
      elif isinstance(position, list) and len(position) >= 3:
        pose_3d = [float(position[0]), float(position[1]), float(position[2]), 0.0, 0.0, 0.0]
      else:
        pose_3d = None
      if pose_3d is not None:
        return ToolResult(
          tool=self.spec.name,
          success=True,
          output={
            "found": True,
            "label": str(call.input.get("query", "recovered_object")),
            "confidence": 1.0,
            "object_id": f"{self._state.get('wrong_target', 'wrong_place')}_recovery_target",
            "pose_3d": pose_3d,
            "source": f"injected_{self._state.get('wrong_target', 'wrong_place')}_pose",
          },
        )
    return self._wrapped.run(call)


class _WrongBinRecoveryPickPlanTool:
  """Tune recovery pick waypoints for staged wrong-placement recovery."""

  def __init__(self, wrapped: Tool, *, state: dict) -> None:
    self.spec = wrapped.spec
    self._wrapped = wrapped
    self._state = state

  def run(self, call: ToolCall) -> ToolResult:
    pose = self._state.get("misplaced_pose")
    orientation = pose.get("orientation") if isinstance(pose, dict) else None
    if not self._state.get("wrong_bin_detected"):
      return self._wrapped.run(call)

    if self._state.get("failure") == "wrong-bin":
      tuned_input = {
        **call.input,
        "approach_distance": 0.03,
        "pregrasp_distance": 0.015,
        "lift_height": 0.08,
      }
      self._state["recovery_pick_distances"] = {
        "approach_distance": tuned_input["approach_distance"],
        "pregrasp_distance": tuned_input["pregrasp_distance"],
        "lift_height": tuned_input["lift_height"],
      }
      if isinstance(orientation, list) and len(orientation) == 4:
        tuned_input["orientation"] = orientation
        self._state["recovery_pick_orientation"] = orientation
      call = ToolCall(tool=call.tool, input=tuned_input, trace=call.trace)
    elif self._state.get("failure") == "wrong-table":
      tuned_input = {
        **call.input,
        "orientation": TABLETOP_PLACE_POSE["orientation"],
        "position_offset": [0.0, 0.0, 0.02],
        "approach_distance": 0.08,
        "pregrasp_distance": 0.03,
        "lift_height": 0.10,
      }
      self._state["recovery_pick_orientation"] = TABLETOP_PLACE_POSE["orientation"]
      self._state["recovery_pick_position_offset"] = tuned_input["position_offset"]
      self._state["recovery_pick_distances"] = {
        "approach_distance": tuned_input["approach_distance"],
        "pregrasp_distance": tuned_input["pregrasp_distance"],
        "lift_height": tuned_input["lift_height"],
      }
      call = ToolCall(tool=call.tool, input=tuned_input, trace=call.trace)
    return self._wrapped.run(call)


def _inject_failure(bundle, args: argparse.Namespace, config: Any) -> dict:
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
    _replace_tool(
      bundle,
      "robot.plan_top_down_pick",
      _WrongBinRecoveryPickPlanTool(
        bundle.tool_registry.get("robot.plan_top_down_pick"),
        state=state,
      ),
    )
    return state
  if args.failure == "wrong-table":
    _replace_tool(
      bundle,
      "robot.resolve_place_target",
      _WrongTableResolveTool(
        bundle.tool_registry.get("robot.resolve_place_target"),
        requested_target=args.target,
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
        open_vocab_tool=bundle.tool_registry.get("vision.open_vocab_detect"),
        frame_dir=args.frame_dir,
        config=config,
        use_live_vision=bool(args.execute),
        capture_frame=bool(args.capture_recovery_frame),
        search_radius=float(args.recovery_vision_radius),
      ),
    )
    _replace_tool(
      bundle,
      "robot.plan_top_down_pick",
      _WrongBinRecoveryPickPlanTool(
        bundle.tool_registry.get("robot.plan_top_down_pick"),
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
  injection_state = _inject_failure(bundle, args, active_config)
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
      "wrong_target": (
        args.wrong_target
        if args.failure == "wrong-bin"
        else "tabletop"
        if args.failure == "wrong-table"
        else None
      ),
      "endpoint": endpoint if args.execute else "(fake)",
    },
  )
  tree = bundle.decision_trees[TREE_NAME]
  result = bundle.decision_tree_runtime.run(tree, request_input, trace)
  output = result.output or {}
  summary = _json_safe({
    "success": result.success,
    "error": result.error,
    "failure_injection": injection_state,
    "classification": output.get("classification"),
    "recovery": output.get("recovery"),
    "bin_check": output.get("bin_check"),
    "last_failure": output.get("last_failure"),
    "result": output,
    "trace": trace.to_dict(),
    "nodes": result.nodes,
  })
  _print_section("recovery demo summary", summary)

  if args.json_out is not None:
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(_json_dump(summary), encoding="utf-8")
    print(f"wrote {args.json_out}")
  return 0 if result.success else 1


if __name__ == "__main__":
  raise SystemExit(main())
