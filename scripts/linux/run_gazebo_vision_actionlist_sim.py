#!/usr/bin/env python3
"""Run text-guided Gazebo RGB-D vision -> pick -> place ActionList."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, replace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
  sys.path.insert(0, str(SRC))

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
  sys.path.insert(0, str(SCRIPT_DIR))

from test_gazebo_pick_pipeline import _check_bridge, _load_agent_config, _print_section, _wait_for_bridge, _wait_for_ready  # noqa: E402

from sensoragent.agent import build_agent  # noqa: E402
from sensoragent.schemas import ToolCall, ToolResult, TraceContext  # noqa: E402
from sensoragent.tools.base import Tool  # noqa: E402
from sensoragent.tools.vision import VisionCaptureFrameTool  # noqa: E402


ACTIONLIST_NAME = "industrial.vision_pick_place_actionlist"


def _json_dump(value) -> str:
  return json.dumps(value, ensure_ascii=False, indent=2, default=str, sort_keys=True)


def _vision_query_aliases(query: str) -> list[str]:
  aliases = [query]
  normalized = query.casefold()
  if "block" in normalized or "cube" in normalized or "方块" in query:
    aliases.extend([
      "block",
      "red block",
      "cube",
      "red cube",
      "box",
      "red box",
      "industrial part",
    ])
  if "roller" in normalized or "cylinder" in normalized or "滚柱" in query:
    aliases.extend([
      "roller",
      "red cylinder",
      "red cylindrical object",
      "cylinder",
      "blue roller",
      "blue cylinder",
    ])
  aliases.extend(["block", "object", "part"])
  result: list[str] = []
  seen: set[str] = set()
  for alias in aliases:
    candidate = alias.strip()
    key = candidate.casefold()
    if candidate and key not in seen:
      result.append(candidate)
      seen.add(key)
  return result


class _VisionQueryRetryTool:
  """Retry YOLOE detection with practical aliases when a prompt is too narrow."""

  def __init__(self, wrapped: Tool) -> None:
    self.spec = wrapped.spec
    self._wrapped = wrapped

  def run(self, call: ToolCall) -> ToolResult:
    query = call.input.get("query")
    if not isinstance(query, str):
      return self._wrapped.run(call)
    attempts: list[dict] = []
    last_result: ToolResult | None = None
    thresholds = (
      (
        call.input.get("box_threshold"),
        call.input.get("text_threshold"),
      ),
      (0.25, 0.15),
      (0.15, 0.10),
      (0.08, 0.05),
    )
    seen_thresholds: set[tuple[object, object]] = set()
    for alias in _vision_query_aliases(query):
      for box_threshold, text_threshold in thresholds:
        threshold_key = (box_threshold, text_threshold)
        if threshold_key in seen_thresholds and alias == query:
          continue
        input_data = {**call.input, "query": alias}
        if box_threshold is not None:
          input_data["box_threshold"] = box_threshold
        if text_threshold is not None:
          input_data["text_threshold"] = text_threshold
        result = self._wrapped.run(ToolCall(tool=call.tool, input=input_data, trace=call.trace))
        last_result = result
        attempt = {
          "query": alias,
          "box_threshold": input_data.get("box_threshold"),
          "text_threshold": input_data.get("text_threshold"),
          "success": result.success,
          "error": result.error,
        }
        if result.output:
          attempt["confidence"] = result.output.get("confidence")
          attempt["pose_3d"] = result.output.get("pose_3d")
        attempts.append(attempt)
        if result.success and result.output:
          output = dict(result.output)
          output["query_attempts"] = attempts
          return ToolResult(tool=result.tool, success=True, output=output, error=None)
        if result.error != "OBJECT_NOT_FOUND":
          output = dict(result.output) if result.output else {}
          output["query_attempts"] = attempts
          return ToolResult(tool=result.tool, success=False, output=output, error=result.error)
      seen_thresholds.clear()
    output = dict(last_result.output) if last_result and last_result.output else {}
    output["query_attempts"] = attempts
    return ToolResult(
      tool=self.spec.name,
      success=False,
      output=output or None,
      error=last_result.error if last_result else "OBJECT_NOT_FOUND",
    )


def _build_parser() -> argparse.ArgumentParser:
  parser = argparse.ArgumentParser(
    description="Capture Gazebo RGB-D, run open-vocabulary vision, then execute industrial pick-place.",
  )
  parser.add_argument("--utterance", default="pick block and place into target_area_3")
  parser.add_argument("--object-query", default="block")
  parser.add_argument("--target", default="target_area_3")
  parser.add_argument(
    "--spatial-relation",
    default=None,
    help="Optional spatial relation (left/right/front/back/nearest/farthest/largest/smallest).",
  )
  parser.add_argument(
    "--spatial-ordinal",
    type=int,
    default=1,
    help="Ordinal for the spatial relation (1=first, 2=second, ...).",
  )
  parser.add_argument("--config", type=Path, default=ROOT / "configs" / "robot_sim.yaml")
  parser.add_argument("--endpoint", default=None)
  parser.add_argument("--frame-dir", type=Path, default=ROOT / "logs" / "vision" / "latest")
  parser.add_argument("--capture", action=argparse.BooleanOptionalAction, default=True)
  parser.add_argument("--execute", action="store_true")
  parser.add_argument("--skip-bridge-check", action="store_true")
  parser.add_argument("--wait-bridge-seconds", type=float, default=30.0)
  parser.add_argument("--wait-ready-seconds", type=float, default=60.0)
  parser.add_argument("--json-out", type=Path, default=None)
  return parser


def _capture_frame(frame_dir: Path) -> dict:
  script = ROOT / "scripts" / "linux" / "capture_gazebo_rgbd_frame.py"
  result = VisionCaptureFrameTool(
    script=str(script),
    out_dir=str(frame_dir),
  ).run(
    ToolCall(tool="vision.capture_frame", input={}, trace=TraceContext())
  )
  if result.success and result.output:
    return result.output
  raise RuntimeError(result.error or "RGB-D frame capture failed.")


def _frame_manifest(frame_dir: Path) -> dict:
  manifest_path = frame_dir / "manifest.json"
  if not manifest_path.exists():
    raise FileNotFoundError(f"Frame manifest not found: {manifest_path}")
  return json.loads(manifest_path.read_text(encoding="utf-8"))


def _gazebo_world_camera_fallback() -> list[list[float]]:
  return [
    [0.0, -1.0, 0.0, 0.34],
    [-1.0, 0.0, 0.0, 0.0],
    [0.0, 0.0, -1.0, 1.06],
    [0.0, 0.0, 0.0, 1.0],
  ]


def main() -> int:
  args = _build_parser().parse_args()
  config = _load_agent_config(args.config, args.endpoint)
  endpoint = str(config.integrations.robot.get("endpoint", "http://127.0.0.1:8765"))
  if not args.skip_bridge_check:
    _wait_for_bridge(endpoint, args.wait_bridge_seconds)
    _check_bridge(endpoint)
    if args.execute:
      _wait_for_ready(
        endpoint,
        args.wait_ready_seconds,
        ("move_action", "execute_trajectory", "cartesian_path", "gripper_cmd"),
      )

  if args.capture:
    manifest = _capture_frame(args.frame_dir)
  else:
    manifest = _frame_manifest(args.frame_dir)
  _print_section("captured frame", manifest)

  if not args.execute:
    robot = dict(config.integrations.robot)
    robot["backend"] = "fake"
    config = replace(config, integrations=replace(config.integrations, robot=robot))

  bundle = build_agent(config)
  bundle.tool_registry._tools["vision.open_vocab_detect"] = _VisionQueryRetryTool(  # noqa: SLF001
    bundle.tool_registry.get("vision.open_vocab_detect")
  )
  action_input = {
    "object_query": args.object_query,
    "target": args.target,
    "image_path": manifest["image_path"],
    "depth_path": manifest["depth_path"],
    "camera_info_path": manifest["camera_info_path"],
    "T_base_camera": manifest.get("T_base_camera")
    or config.integrations.vision.get("T_base_camera"),
    "T_world_camera": manifest.get("T_world_camera")
    or _gazebo_world_camera_fallback(),
    "spatial_constraint": (
      {"relation": args.spatial_relation, "ordinal": args.spatial_ordinal}
      if args.spatial_relation
      else {}
    ),
  }
  _print_section(
    "vision actionlist input",
    {
      "utterance": args.utterance,
      "actionlist": ACTIONLIST_NAME,
      "execute": args.execute,
      "input": action_input,
    },
  )
  trace = TraceContext()
  actionlist = bundle.actionlists[ACTIONLIST_NAME]
  result = bundle.actionlist_runtime.run(actionlist, action_input, trace)
  summary = {
    "success": result.success,
    "error": result.error,
    "result": result.output,
    "steps": [asdict(step) for step in result.steps],
    "trace": trace.to_dict(),
  }
  _print_section("summary", summary)
  if args.json_out is not None:
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(_json_dump(summary), encoding="utf-8")
  return 0 if result.success else 1


if __name__ == "__main__":
  raise SystemExit(main())
