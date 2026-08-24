"""Command-line entry point for SensorAgent."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from sensoragent.agent import build_agent_from_config, build_agent_from_env
from sensoragent.config import load_config, resolve_config_path
from sensoragent.mcp import MockMcpEndpoint
from sensoragent.schemas import AgentRequest, TraceContext
from sensoragent.tools.vision import SPATIAL_RELATIONS


def _default_task_log_path(prefix: str = "mock_pick_place") -> Path:
  timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
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

  run_actionlist = subparsers.add_parser(
    "run-actionlist",
    help="Run one named ActionList directly.",
  )
  run_actionlist.add_argument("actionlist", help="Registered ActionList name.")
  run_actionlist.add_argument(
    "--config",
    type=Path,
    default=None,
    help="Path to a SensorAgent config file.",
  )
  run_actionlist.add_argument(
    "--object-query",
    required=True,
    help="Object query passed to the ActionList.",
  )
  run_actionlist.add_argument(
    "--pick-profile",
    default="",
    help="Optional configured pick profile, for example short_bolt.",
  )
  run_actionlist.add_argument(
    "--spatial-relation",
    choices=tuple(sorted(SPATIAL_RELATIONS)),
    default=None,
    help="Optional spatial selection relation.",
  )
  run_actionlist.add_argument(
    "--spatial-ordinal",
    type=int,
    default=1,
    help="Ordinal used with --spatial-relation.",
  )
  run_actionlist.add_argument(
    "--log-path",
    type=Path,
    default=None,
    help="Path to the JSONL task log.",
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
    default=None,
    help="Maximum microphone recording duration in seconds. Defaults to config.",
  )
  listen_task.add_argument(
    "--language",
    default=None,
    help="ASR language hint. Defaults to config.",
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
    "--vad-min-rms",
    type=float,
    default=None,
    help="Optional VAD minimum RMS energy gate for listen-task.",
  )
  listen_task.add_argument(
    "--vad-pre-roll-ms",
    type=int,
    default=None,
    help="Optional VAD pre-speech audio buffer override in milliseconds.",
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
  listen_task.add_argument(
    "--max-turns",
    type=int,
    default=1,
    help="Maximum listen-transcribe-execute turns. Use 100 for a bounded session.",
  )

  vision_detect = subparsers.add_parser(
    "vision-detect",
    help="Run open-vocabulary detection on one RGB image.",
  )
  vision_detect.add_argument(
    "--config",
    type=Path,
    default=Path("configs/vision_grounding_dino.yaml"),
    help="Config containing the selected vision Tool and its backend settings.",
  )
  vision_detect.add_argument(
    "--tool",
    choices=(
      "vision.open_vocab_detect",
      "vision.grounded_sam2",
      "vision.yolo11_seg_detect",
    ),
    default="vision.open_vocab_detect",
    help=(
      "Vision Tool to invoke. Grounded SAM2 and YOLO11-seg always require "
      "native/refined masks."
    ),
  )
  vision_detect.add_argument("--image", type=Path, required=True)
  vision_detect.add_argument("--query", required=True)
  vision_detect.add_argument("--depth", type=Path, default=None)
  vision_detect.add_argument("--camera-info", type=Path, default=None)
  vision_detect.add_argument("--device", default=None)
  vision_detect.add_argument("--box-threshold", type=float, default=None)
  vision_detect.add_argument("--text-threshold", type=float, default=None)
  vision_detect.add_argument("--nms-iou-threshold", type=float, default=None)
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

  competition = subparsers.add_parser(
    "competition",
    help="Run a batch of recovery-tree scenarios and write competition metrics.",
  )
  competition.add_argument(
    "--config",
    type=Path,
    default=Path("configs/robot_mock.yaml"),
    help="SensorAgent config with a fake/local backend (default: configs/robot_mock.yaml).",
  )
  competition.add_argument(
    "--scenarios",
    type=Path,
    required=True,
    help="YAML file with a top-level 'scenarios' list.",
  )
  competition.add_argument(
    "--out-dir",
    type=Path,
    default=None,
    help="Directory for results.jsonl + summary.json (default: logs/competition/<ts>).",
  )
  competition.add_argument(
    "--baseline-success-rate",
    type=float,
    default=None,
    help="Override the nominal baseline success rate used for recovery_gain.",
  )

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


def _run_actionlist(args: argparse.Namespace) -> int:
  log_path = args.log_path or _default_task_log_path("actionlist")
  bundle = build_agent_from_env(args.config, log_path=log_path)
  input_data = {
    "object_query": args.object_query,
    "pick_profile": args.pick_profile,
  }
  if args.spatial_relation is not None:
    input_data["spatial_constraint"] = {
      "relation": args.spatial_relation,
      "ordinal": args.spatial_ordinal,
    }
  try:
    response = bundle.agent.handle(AgentRequest(
      actionlist=args.actionlist,
      input=input_data,
      trace=TraceContext(),
    ))
  except KeyboardInterrupt:
    # Interrupting the HTTP wait must also stop the physical controller.
    stop_result = bundle.tool_runtime.invoke("robot.stop", {}, TraceContext())
    print(
      f"Interrupted; robot.stop success={stop_result.success} "
      f"error={stop_result.error}",
      file=sys.stderr,
    )
    return 130
  print(json.dumps({
    "actionlist": args.actionlist,
    "success": response.success,
    "result": response.result,
    "error": response.error,
  }, ensure_ascii=False, indent=2))
  return 0 if response.success else 1


def _run_listen_task(args: argparse.Namespace) -> int:
  max_turns = int(getattr(args, "max_turns", 1))
  if max_turns < 1:
    raise ValueError("--max-turns must be at least 1")
  log_path = args.log_path or _default_task_log_path()
  config_path = resolve_config_path(args.config)
  config = load_config(config_path)
  audio_config = config.integrations.audio
  duration_seconds = float(
    args.duration
    if args.duration is not None
    else audio_config.get("listen_duration_seconds", 8.0)
  )
  language = str(
    args.language if args.language is not None else audio_config.get("listen_language", "zh")
  )
  vad_input = {
    "threshold": float(audio_config.get("vad_threshold", 0.35)),
    "min_rms": float(audio_config.get("vad_min_rms", 0.025)),
    "min_speech_windows": int(audio_config.get("vad_min_speech_windows", 2)),
    "pre_roll_ms": int(audio_config.get("vad_pre_roll_ms", 120)),
    "post_roll_ms": int(audio_config.get("vad_post_roll_ms", 1800)),
    "tail_padding_ms": int(audio_config.get("vad_tail_padding_ms", 700)),
    "max_utterance_sec": float(audio_config.get("vad_max_utterance_sec", 15.0)),
  }
  bundle = build_agent_from_config(
    config_path,
    log_path=log_path,
    planner_mode=args.planner,
  )
  if args.vad_threshold is not None:
    vad_input["threshold"] = args.vad_threshold
  if args.vad_min_rms is not None:
    vad_input["min_rms"] = args.vad_min_rms
  if args.vad_pre_roll_ms is not None:
    vad_input["pre_roll_ms"] = args.vad_pre_roll_ms
  if args.vad_post_roll_ms is not None:
    vad_input["post_roll_ms"] = args.vad_post_roll_ms
  if args.vad_tail_padding_ms is not None:
    vad_input["tail_padding_ms"] = args.vad_tail_padding_ms

  initial_input = {}
  if args.object_query is not None:
    initial_input["object_query"] = args.object_query
  if args.target is not None:
    initial_input["target"] = args.target

  def stop_robot() -> None:
    try:
      bundle.tool_runtime.invoke("robot.stop", {}, TraceContext())
    except Exception:
      pass

  try:
    for turn_index in range(1, max_turns + 1):
      trace = TraceContext()
      listen_input = {
        "duration_seconds": duration_seconds,
        "language": language,
        "vad": dict(vad_input),
      }
      if args.audio_path is not None:
        audio_path = args.audio_path
        if max_turns > 1:
          audio_path = audio_path.with_stem(f"{audio_path.stem}_{turn_index:03d}")
        listen_input["output_path"] = str(audio_path)
      bundle.logger.log(
        "listen_task_started",
        trace,
        {
          "stage": "listen_task",
          "turn_index": turn_index,
          "config": str(config_path),
          "planner": args.planner,
          "input": listen_input,
        },
      )
      print(
        f"Listening for command {turn_index}/{max_turns} (max {duration_seconds:g}s, "
        f"silence tail {vad_input['post_roll_ms']} ms).",
        file=sys.stderr,
        flush=True,
      )
      transcript = bundle.tool_runtime.invoke(
        "audio.listen_vad_transcribe",
        listen_input,
        trace=trace,
      )
      if not transcript.success or not transcript.output:
        error = transcript.error or "TRANSCRIBE_FAILED"
        bundle.logger.log("listen_task_failed", trace, {"stage": "audio.listen_vad_transcribe", "turn_index": turn_index, "error": error})
        print(json.dumps({"turn_index": turn_index, "success": False, "error": error}, ensure_ascii=False, indent=2))
        print(f"Task log: {log_path}")
        return 1
      text = str(transcript.output.get("text", "")).strip()
      bundle.logger.log("listen_task_transcribed", trace, {"stage": "audio.listen_vad_transcribe", "turn_index": turn_index, "output": transcript.output})
      if not text:
        bundle.logger.log("listen_task_failed", trace, {"stage": "asr.result_filter", "turn_index": turn_index, "error": "EMPTY_TRANSCRIPT"})
        print(json.dumps({"turn_index": turn_index, "success": False, "error": "EMPTY_TRANSCRIPT", "transcript": transcript.output}, ensure_ascii=False, indent=2))
        print(f"Task log: {log_path}")
        return 1
      bundle.logger.log("listen_task_agent_started", trace, {"stage": "agent.run_task", "turn_index": turn_index, "planner": args.planner, "input": {"user_input": text, "initial_input": initial_input}})
      try:
        task = bundle.agent.run_task(text, initial_input)
      except Exception as exc:
        stop_robot()
        bundle.logger.log("listen_task_failed", trace, {"stage": "agent.run_task", "turn_index": turn_index, "error_type": type(exc).__name__, "error": str(exc)})
        print(json.dumps({"turn_index": turn_index, "success": False, "error": str(exc), "error_type": type(exc).__name__, "transcript": transcript.output}, ensure_ascii=False, indent=2))
        print(f"Task log: {log_path}")
        return 1
      bundle.logger.log("listen_task_finished", trace, {"stage": "agent.run_task", "turn_index": turn_index, "success": task.error is None, "task_id": task.task_id, "status": str(task.status), "error": task.error, "plan": task.plan.to_dict() if task.plan is not None else None})
      print(json.dumps({"turn_index": turn_index, "transcript": transcript.output, "task": task.to_dict()}, ensure_ascii=False, indent=2))
      if task.error is not None:
        stop_robot()
        print(f"Task log: {log_path}")
        return 1
  except KeyboardInterrupt:
    stop_robot()
    print(json.dumps({"success": False, "error": "INTERRUPTED"}, ensure_ascii=False, indent=2))
    print(f"Task log: {log_path}")
    return 130
  print(f"Task log: {log_path}")
  return 0


def _run_vision_detect(args: argparse.Namespace) -> int:
  if args.spatial_ordinal < 1:
    raise SystemExit("--spatial-ordinal must be >= 1")
  log_path = args.log_path or _default_task_log_path("vision_detect")
  bundle = build_agent_from_env(args.config, log_path=log_path)
  strict_mask_tool = args.tool in {
    "vision.grounded_sam2",
    "vision.yolo11_seg_detect",
  }
  input_data = {
    "query": args.query,
    "image_path": str(args.image),
    "refine_masks": True if args.tool == "vision.grounded_sam2" else not args.no_refine,
    "require_masks": True if strict_mask_tool else args.require_masks,
  }
  optional = {
    "depth_path": str(args.depth) if args.depth is not None else None,
    "camera_info_path": (
      str(args.camera_info) if args.camera_info is not None else None
    ),
    "device": args.device,
    "box_threshold": args.box_threshold,
    "text_threshold": args.text_threshold,
    "nms_iou_threshold": args.nms_iou_threshold,
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
    args.tool,
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


def _run_competition(args: argparse.Namespace) -> int:
  from sensoragent.evaluation import evaluate_runs
  from sensoragent.evaluation.batch import load_scenarios, run_batch

  scenarios = load_scenarios(args.scenarios)
  out_dir = args.out_dir or (
    Path("logs") / "competition" / datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
  )
  records, baseline = run_batch(
    scenarios, args.config, baseline_success_rate=args.baseline_success_rate
  )
  evaluation = evaluate_runs(
    records, output_dir=out_dir, baseline_success_rate=baseline
  )
  print(
    json.dumps(
      {
        "summary_path": str(out_dir / "summary.json"),
        "results_path": str(out_dir / "results.jsonl"),
        "run_count": len(evaluation.rows),
        "passed": evaluation.passed,
      },
      ensure_ascii=False,
      indent=2,
    )
  )
  return 0


def main(argv: Sequence[str] | None = None) -> int:
  parser = _build_parser()
  args = parser.parse_args(argv)

  if args.command == "mock-pick-place":
    return _run_mock_pick_place(args)
  if args.command == "run-task":
    return _run_task(args)
  if args.command == "run-actionlist":
    return _run_actionlist(args)
  if args.command == "listen-task":
    exit_code = _run_listen_task(args)
    # OpenCV/Ultralytics can leave native worker threads alive after Ctrl+C.
    # robot.stop has already completed in _run_listen_task, so bypass Python's
    # thread teardown to ensure the operator returns to a usable shell.
    if exit_code == 130:
      os._exit(exit_code)
    return exit_code
  if args.command == "vision-detect":
    return _run_vision_detect(args)
  if args.command == "competition":
    return _run_competition(args)

  parser.error(f"Unknown command: {args.command}")
  return 2


if __name__ == "__main__":
  raise SystemExit(main())
