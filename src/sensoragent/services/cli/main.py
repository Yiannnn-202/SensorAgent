"""Command-line entry point for SensorAgent."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Sequence

from sensoragent.agent import build_agent_from_env
from sensoragent.mcp import MockMcpEndpoint
from sensoragent.schemas import TraceContext
from sensoragent.tools.vision import SPATIAL_RELATIONS


def _default_task_log_path(prefix: str = "mock_pick_place") -> Path:
  timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
  return Path("logs") / "tasks" / f"{prefix}_{timestamp}.jsonl"


def _build_parser() -> argparse.ArgumentParser:
  parser = argparse.ArgumentParser(
    prog="sensoragent",
    description="SensorAgent command-line tools.",
  )
  subparsers = parser.add_subparsers(dest="command", required=True)

  mock_pick = subparsers.add_parser(
    "mock-pick-place",
    help="Run the local mock pick-and-place Agent chain.",
  )
  mock_pick.add_argument(
    "--config",
    type=Path,
    default=None,
    help="Path to a SensorAgent config file. Defaults to env resolution.",
  )
  mock_pick.add_argument(
    "--object-query",
    default="silver roller",
    help="Object query passed to the mock vision tool.",
  )
  mock_pick.add_argument(
    "--target",
    default="third bin cell",
    help="Target location passed to the mock robot place tool.",
  )
  mock_pick.add_argument(
    "--log-path",
    type=Path,
    default=None,
    help="Path to the JSONL task log. Defaults to logs/tasks/*.jsonl.",
  )

  run_task = subparsers.add_parser(
    "run-task",
    help="Run a user task through the Agent planner.",
  )
  run_task.add_argument("user_input", help="Natural-language task input.")
  run_task.add_argument(
    "--config",
    type=Path,
    default=None,
    help="Path to a SensorAgent config file. Defaults to env resolution.",
  )
  run_task.add_argument(
    "--planner",
    choices=("static", "llm"),
    default="static",
    help="Planner mode used to create the AgentPlan.",
  )
  run_task.add_argument(
    "--object-query",
    default=None,
    help="Optional structured object query passed as initial input.",
  )
  run_task.add_argument(
    "--target",
    default=None,
    help="Optional structured target passed as initial input.",
  )
  run_task.add_argument(
    "--log-path",
    type=Path,
    default=None,
    help="Path to the JSONL task log. Defaults to logs/tasks/*.jsonl.",
  )

  listen_task = subparsers.add_parser(
    "listen-task",
    help="Record one utterance, transcribe it, and run it as an Agent task.",
  )
  listen_task.add_argument(
    "--config",
    type=Path,
    default=None,
    help="Path to a SensorAgent config file. Defaults to env resolution.",
  )
  listen_task.add_argument(
    "--planner",
    choices=("static", "llm"),
    default="llm",
    help="Planner mode used after transcription.",
  )
  listen_task.add_argument(
    "--duration",
    type=float,
    default=5.0,
    help="Fixed microphone recording duration in seconds.",
  )
  listen_task.add_argument(
    "--language",
    default="zh",
    help="ASR language hint.",
  )
  listen_task.add_argument(
    "--audio-path",
    type=Path,
    default=None,
    help="Where to write the recorded WAV. Defaults to logs/audio/*.wav.",
  )
  listen_task.add_argument(
    "--vad-threshold",
    type=float,
    default=None,
    help="Optional VAD speech threshold override for listen-task.",
  )
  listen_task.add_argument(
    "--vad-post-roll-ms",
    type=int,
    default=None,
    help="Optional VAD silence tail wait override in milliseconds.",
  )
  listen_task.add_argument(
    "--vad-tail-padding-ms",
    type=int,
    default=None,
    help="Optional silent padding appended before ASR in milliseconds.",
  )
  listen_task.add_argument(
    "--object-query",
    default=None,
    help="Optional structured object query passed to the planner.",
  )
  listen_task.add_argument(
    "--target",
    default=None,
    help="Optional structured target passed to the planner.",
  )
  listen_task.add_argument(
    "--log-path",
    type=Path,
    default=None,
    help="Path to the JSONL task log. Defaults to logs/tasks/*.jsonl.",
  )

  vision_detect = subparsers.add_parser(
    "vision-detect",
    help="Run open-vocabulary detection on one RGB image.",
  )
  vision_detect.add_argument(
    "--config",
    type=Path,
    default=Path("configs/vision_grounding_dino.yaml"),
    help="Config containing vision.open_vocab_detect and its backend settings.",
  )
  vision_detect.add_argument("--image", type=Path, required=True)
  vision_detect.add_argument("--query", required=True)
  vision_detect.add_argument("--depth", type=Path, default=None)
  vision_detect.add_argument("--camera-info", type=Path, default=None)
  vision_detect.add_argument("--device", default=None)
  vision_detect.add_argument("--box-threshold", type=float, default=None)
  vision_detect.add_argument("--text-threshold", type=float, default=None)
  vision_detect.add_argument("--depth-scale", type=float, default=None)
  vision_detect.add_argument(
    "--spatial-relation",
    default=None,
    choices=sorted(SPATIAL_RELATIONS),
    help=(
      "Disambiguate several identical objects by spatial relation. "
      "left/right/front/back/largest/smallest work on the image alone; "
      "nearest/farthest rank by base XY and need --camera-info."
    ),
  )
  vision_detect.add_argument(
    "--spatial-ordinal",
    type=int,
    default=1,
    help="Which candidate to take along --spatial-relation (1=first). Default 1.",
  )
  vision_detect.add_argument(
    "--no-refine",
    action="store_true",
    help="Skip SAM 2 and keep the detector bounding box.",
  )
  vision_detect.add_argument(
    "--require-masks",
    action="store_true",
    help="Fail instead of using a box when SAM 2 refinement fails.",
  )
  vision_detect.add_argument(
    "--overlay",
    type=Path,
    default=None,
    help="Optional path for a box/mask visualization (.jpg, .png, or .webp).",
  )
  vision_detect.add_argument("--log-path", type=Path, default=None)

  return parser


def _run_mock_pick_place(args: argparse.Namespace) -> int:
  log_path = args.log_path or _default_task_log_path()
  bundle = build_agent_from_env(args.config, log_path=log_path)
  endpoint = MockMcpEndpoint(bundle.agent)

  response = endpoint.call_skill(
    "mock.pick_and_place",
    {
      "object_query": args.object_query,
      "target": args.target,
    },
  )

  print(json.dumps(response.to_dict(), ensure_ascii=False, indent=2))
  print(f"Task log: {log_path}")
  return 0 if response.success else 1


def _run_task(args: argparse.Namespace) -> int:
  log_path = args.log_path or _default_task_log_path()
  initial_input = {}
  if args.object_query is not None:
    initial_input["object_query"] = args.object_query
  if args.target is not None:
    initial_input["target"] = args.target

  bundle = build_agent_from_env(
    args.config,
    log_path=log_path,
    planner_mode=args.planner,
  )
  task = bundle.agent.run_task(args.user_input, initial_input)

  print(json.dumps(task.to_dict(), ensure_ascii=False, indent=2))
  print(f"Task log: {log_path}")
  return 0 if task.error is None else 1


def _run_listen_task(args: argparse.Namespace) -> int:
  log_path = args.log_path or _default_task_log_path()
  bundle = build_agent_from_env(
    args.config,
    log_path=log_path,
    planner_mode=args.planner,
  )
  listen_input = {
    "duration_seconds": args.duration,
    "language": args.language,
  }
  if args.audio_path is not None:
    listen_input["output_path"] = str(args.audio_path)
  vad_input = {}
  if args.vad_threshold is not None:
    vad_input["threshold"] = args.vad_threshold
  if args.vad_post_roll_ms is not None:
    vad_input["post_roll_ms"] = args.vad_post_roll_ms
  if args.vad_tail_padding_ms is not None:
    vad_input["tail_padding_ms"] = args.vad_tail_padding_ms
  if vad_input:
    listen_input["vad"] = vad_input

  transcript = bundle.tool_runtime.invoke(
    "audio.listen_vad_transcribe",
    listen_input,
    trace=TraceContext(),
  )
  if not transcript.success or not transcript.output:
    print(json.dumps({"success": False, "error": transcript.error}, ensure_ascii=False, indent=2))
    print(f"Task log: {log_path}")
    return 1

  initial_input = {}
  if args.object_query is not None:
    initial_input["object_query"] = args.object_query
  if args.target is not None:
    initial_input["target"] = args.target

  task = bundle.agent.run_task(transcript.output["text"], initial_input)
  print(
    json.dumps(
      {
        "transcript": transcript.output,
        "task": task.to_dict(),
      },
      ensure_ascii=False,
      indent=2,
    )
  )
  print(f"Task log: {log_path}")
  return 0 if task.error is None else 1


def _run_vision_detect(args: argparse.Namespace) -> int:
  if args.spatial_ordinal < 1:
    raise SystemExit("--spatial-ordinal must be >= 1")
  log_path = args.log_path or _default_task_log_path("vision_detect")
  bundle = build_agent_from_env(args.config, log_path=log_path)
  input_data = {
    "query": args.query,
    "image_path": str(args.image),
    "refine_masks": not args.no_refine,
    "require_masks": args.require_masks,
  }
  optional = {
    "depth_path": str(args.depth) if args.depth is not None else None,
    "camera_info_path": (
      str(args.camera_info) if args.camera_info is not None else None
    ),
    "device": args.device,
    "box_threshold": args.box_threshold,
    "text_threshold": args.text_threshold,
    "depth_scale": args.depth_scale,
    "overlay_path": str(args.overlay) if args.overlay is not None else None,
  }
  input_data.update({key: value for key, value in optional.items() if value is not None})
  if args.spatial_relation is not None:
    input_data["spatial_constraint"] = {
      "relation": args.spatial_relation,
      "ordinal": args.spatial_ordinal,
    }
  result = bundle.tool_runtime.invoke(
    "vision.open_vocab_detect",
    input_data,
    trace=TraceContext(),
  )
  print(
    json.dumps(
      {
        "tool": result.tool,
        "success": result.success,
        "output": result.output,
        "error": result.error,
      },
      ensure_ascii=False,
      indent=2,
    )
  )
  return 0 if result.success else 1


def main(argv: Sequence[str] | None = None) -> int:
  parser = _build_parser()
  args = parser.parse_args(argv)

  if args.command == "mock-pick-place":
    return _run_mock_pick_place(args)
  if args.command == "run-task":
    return _run_task(args)
  if args.command == "listen-task":
    return _run_listen_task(args)
  if args.command == "vision-detect":
    return _run_vision_detect(args)

  parser.error(f"Unknown command: {args.command}")
  return 2


if __name__ == "__main__":
  raise SystemExit(main())
