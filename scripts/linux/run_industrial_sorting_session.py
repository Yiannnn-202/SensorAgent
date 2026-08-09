#!/usr/bin/env python3
"""Run a persistent command loop for the industrial sorting scene."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import TextIO


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
  sys.path.insert(0, str(SRC))

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
  sys.path.insert(0, str(SCRIPT_DIR))

from run_industrial_sorting_voice_sim import ACTIONLIST, parse_sorting_command  # noqa: E402
from test_gazebo_pick_pipeline import _check_bridge, _wait_for_bridge, _wait_for_ready  # noqa: E402

from sensoragent.agent import AgentBundle, build_agent  # noqa: E402
from sensoragent.config import SensorAgentConfig, load_config  # noqa: E402
from sensoragent.schemas import AgentRequest, TraceContext  # noqa: E402


EXIT_COMMANDS = {"退出", "结束", "停止会话", "exit", "quit", "q"}
STATUS_COMMANDS = {"状态", "status"}


def _default_session_log_path() -> Path:
  timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
  return Path("logs") / "tasks" / f"sorting_session_{timestamp}.jsonl"


def _normalized_control_text(text: str) -> str:
  return "".join(text.strip().lower().split())


def is_exit_command(text: str) -> bool:
  """Return True when a user utterance should end the persistent session."""

  return _normalized_control_text(text) in EXIT_COMMANDS


def is_status_command(text: str) -> bool:
  """Return True when a user utterance requests the session status."""

  return _normalized_control_text(text) in STATUS_COMMANDS


def prepare_session_config(
  config: SensorAgentConfig,
  *,
  execute: bool,
  voice_enabled: bool,
) -> SensorAgentConfig:
  """Prepare a config for a persistent loop.

  Text sessions do not need microphone or ASR objects, so audio tools are
  removed before building the runtime. This keeps text dry-runs usable on
  machines that do not have local VAD/ASR model assets installed.
  """

  robot = dict(config.integrations.robot)
  if not execute:
    robot["backend"] = "fake"

  tools = config.tools
  skills = config.skills
  if not voice_enabled:
    tools = replace(
      tools,
      enabled=[name for name in tools.enabled if not name.startswith("audio.")],
    )
    skills = replace(
      skills,
      enabled=[name for name in skills.enabled if not name.startswith("audio.")],
    )

  return replace(
    config,
    tools=tools,
    skills=skills,
    integrations=replace(config.integrations, robot=robot),
  )


def run_sorting_turn(bundle: AgentBundle, transcript: str, *, turn_index: int) -> dict:
  """Parse and execute one sorting instruction without ending the process."""

  text = transcript.strip()
  if not text:
    return {
      "type": "empty",
      "success": False,
      "turn_index": turn_index,
      "transcript": transcript,
      "error": "EMPTY_COMMAND",
    }
  if is_exit_command(text):
    return {
      "type": "exit",
      "success": True,
      "turn_index": turn_index,
      "transcript": transcript,
      "message": "Session exit requested.",
    }
  if is_status_command(text):
    status: dict = {
      "registered_tools": bundle.tool_registry.names(),
      "registered_actionlists": sorted(bundle.actionlists),
    }
    if "robot.get_state" in bundle.tool_registry.names():
      state = bundle.tool_runtime.invoke("robot.get_state", {}, TraceContext())
      status["robot_state"] = {
        "success": state.success,
        "output": state.output,
        "error": state.error,
      }
    return {
      "type": "status",
      "success": True,
      "turn_index": turn_index,
      "transcript": transcript,
      "status": status,
    }

  trace = TraceContext()
  try:
    command = parse_sorting_command(text)
  except ValueError as exc:
    return {
      "type": "command",
      "success": False,
      "turn_index": turn_index,
      "transcript": transcript,
      "error": str(exc),
    }

  response = bundle.agent.handle(
    AgentRequest(actionlist=ACTIONLIST, input=command, trace=trace)
  )
  return {
    "type": "command",
    "success": response.success,
    "turn_index": turn_index,
    "trace": trace.to_dict(),
    "transcript": transcript,
    "command": command,
    "error": response.error,
    "result": response.result,
  }


def _print_json(value: dict, stream: TextIO) -> None:
  print(json.dumps(value, ensure_ascii=False, indent=2, default=str), file=stream)
  stream.flush()


def build_vad_input(config: SensorAgentConfig) -> dict:
  """Return explicit VAD settings for the listen tool."""

  audio_config = config.integrations.audio
  return {
    "threshold": float(audio_config.get("vad_threshold", 0.35)),
    "min_rms": float(audio_config.get("vad_min_rms", 0.0)),
    "min_speech_windows": int(audio_config.get("vad_min_speech_windows", 2)),
    "pre_roll_ms": int(audio_config.get("vad_pre_roll_ms", 120)),
    "post_roll_ms": int(audio_config.get("vad_post_roll_ms", 1800)),
    "tail_padding_ms": int(audio_config.get("vad_tail_padding_ms", 700)),
    "max_utterance_sec": float(audio_config.get("vad_max_utterance_sec", 15.0)),
  }


def run_text_loop(
  bundle: AgentBundle,
  *,
  input_stream: TextIO = sys.stdin,
  output_stream: TextIO = sys.stdout,
  prompt_stream: TextIO = sys.stderr,
  max_turns: int | None = None,
) -> int:
  """Run a persistent stdin command loop."""

  turn_index = 0
  print(
    "Sorting session ready. 输入中文分拣指令；输入 退出/exit 结束。",
    file=prompt_stream,
    flush=True,
  )
  while max_turns is None or turn_index < max_turns:
    print("> ", end="", file=prompt_stream, flush=True)
    line = input_stream.readline()
    if line == "":
      _print_json({"type": "exit", "success": True, "reason": "EOF"}, output_stream)
      return 0
    result = run_sorting_turn(bundle, line, turn_index=turn_index)
    if result["type"] != "empty":
      turn_index += 1
    _print_json(result, output_stream)
    if result["type"] == "exit":
      return 0
  _print_json(
    {
      "type": "exit",
      "success": True,
      "reason": f"Reached max_turns={max_turns}",
      "turn_count": turn_index,
    },
    output_stream,
  )
  return 0


def run_voice_loop(
  bundle: AgentBundle,
  *,
  duration_seconds: float,
  language: str,
  vad: dict | None = None,
  output_stream: TextIO = sys.stdout,
  prompt_stream: TextIO = sys.stderr,
  max_turns: int | None = None,
) -> int:
  """Run a persistent listen-transcribe-execute loop."""

  turn_index = 0
  print(
    "Voice sorting session ready. 说出分拣指令；说 退出/exit 结束。",
    file=prompt_stream,
    flush=True,
  )
  while max_turns is None or turn_index < max_turns:
    print(
      f"Listening for command {turn_index + 1} (max {duration_seconds:g}s)...",
      file=prompt_stream,
      flush=True,
    )
    trace = TraceContext()
    listen_input = {"duration_seconds": duration_seconds, "language": language}
    if vad is not None:
      listen_input["vad"] = dict(vad)
    transcript = bundle.tool_runtime.invoke(
      "audio.listen_vad_transcribe",
      listen_input,
      trace,
    )
    if not transcript.success or not transcript.output:
      _print_json(
        {
          "type": "listen",
          "success": False,
          "turn_index": turn_index,
          "error": transcript.error,
        },
        output_stream,
      )
      turn_index += 1
      continue

    text = str(transcript.output.get("text", "")).strip()
    result = run_sorting_turn(bundle, text, turn_index=turn_index)
    result["listen"] = {
      "audio_path": transcript.output.get("audio_path"),
      "duration_ms": transcript.output.get("duration_ms"),
      "confidence": transcript.output.get("confidence"),
      "language": transcript.output.get("language"),
    }
    turn_index += 1
    _print_json(result, output_stream)
    if result["type"] == "exit":
      return 0
  _print_json(
    {
      "type": "exit",
      "success": True,
      "reason": f"Reached max_turns={max_turns}",
      "turn_count": turn_index,
    },
    output_stream,
  )
  return 0


def _build_parser() -> argparse.ArgumentParser:
  parser = argparse.ArgumentParser(
    description="Run a persistent industrial sorting Agent session."
  )
  parser.add_argument(
    "--config",
    type=Path,
    default=ROOT / "configs" / "robot_sorting_sim.yaml",
  )
  parser.add_argument(
    "--mode",
    choices=("text", "voice"),
    default="text",
    help="Input loop mode. Text mode reads stdin; voice mode records one utterance per turn.",
  )
  parser.add_argument(
    "--execute",
    action="store_true",
    help="Send robot commands to the Gazebo bridge. Without it, use the fake robot backend.",
  )
  parser.add_argument("--duration", type=float, default=15.0)
  parser.add_argument("--language", default=None)
  parser.add_argument("--log-path", type=Path, default=None)
  parser.add_argument(
    "--vad-threshold",
    type=float,
    default=None,
    help="Optional VAD speech threshold override for voice mode.",
  )
  parser.add_argument(
    "--vad-min-rms",
    type=float,
    default=None,
    help="Optional VAD minimum RMS gate override for voice mode.",
  )
  parser.add_argument(
    "--vad-pre-roll-ms",
    type=int,
    default=None,
    help="Optional VAD pre-speech audio buffer override in milliseconds.",
  )
  parser.add_argument(
    "--vad-post-roll-ms",
    type=int,
    default=None,
    help="Optional VAD silence tail wait override in milliseconds.",
  )
  parser.add_argument(
    "--vad-tail-padding-ms",
    type=int,
    default=None,
    help="Optional VAD trailing silence padding override in milliseconds.",
  )
  parser.add_argument(
    "--max-turns",
    type=int,
    default=None,
    help="Optional turn limit for smoke tests or scripted sessions.",
  )
  return parser


def main() -> int:
  parser = _build_parser()
  args = parser.parse_args()
  if args.max_turns is not None and args.max_turns < 1:
    parser.error("--max-turns must be >= 1")

  config = load_config(args.config)
  endpoint = str(config.integrations.robot.get("endpoint", "http://127.0.0.1:8765"))
  if args.execute:
    _wait_for_bridge(endpoint, 30.0)
    _check_bridge(endpoint)
    _wait_for_ready(
      endpoint,
      60.0,
      ("move_action", "execute_trajectory", "cartesian_path", "gripper_cmd"),
    )

  active_config = prepare_session_config(
    config,
    execute=args.execute,
    voice_enabled=args.mode == "voice",
  )
  bundle = build_agent(active_config, log_path=args.log_path or _default_session_log_path())
  if args.mode == "voice":
    language = str(
      args.language
      if args.language is not None
      else config.integrations.audio.get("listen_language", "zh")
    )
    vad_input = build_vad_input(config)
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
    return run_voice_loop(
      bundle,
      duration_seconds=args.duration,
      language=language,
      vad=vad_input,
      max_turns=args.max_turns,
    )
  return run_text_loop(bundle, max_turns=args.max_turns)


if __name__ == "__main__":
  raise SystemExit(main())
