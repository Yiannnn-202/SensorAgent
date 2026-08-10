#!/usr/bin/env python3
"""Transcribe one sorting command and run the deterministic sorting ActionList."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import replace
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
_OBJECT_ALIASES = {
  "方块": "方块", "金属方块": "方块", "阶梯轴": "阶梯轴", "中空圆套": "中空圆套",
  "圆套": "中空圆套", "滚轮": "滚轮", "滚柱": "滚轮", "六角螺母": "六角螺母",
  "螺母": "六角螺母", "短螺栓": "短螺栓", "螺栓": "短螺栓", "法兰套": "法兰套",
  "法兰衬套": "法兰套",
}
_CHINESE_DIGITS = str.maketrans("一二三四五六七八", "12345678")


def parse_sorting_command(text: str) -> dict[str, str]:
  """Translate a constrained Chinese sorting command into ActionList input."""
  normalized = re.sub(r"\s+", "", text).translate(_CHINESE_DIGITS)
  object_query = next(
    (canonical for alias, canonical in sorted(_OBJECT_ALIASES.items(), key=lambda item: len(item[0]), reverse=True) if alias in normalized),
    None,
  )
  target_match = re.search(r"(?:第)?([1-8])(?:号)?(?:格|格子|格位)", normalized)
  if object_query is None or target_match is None:
    raise ValueError("无法识别分拣指令；请说例如：把方块放到1号格")
  return {"object_query": object_query, "target": f"bin_cell_{target_match.group(1)}"}


def _text_mode_config(config):
  tool_names = [
    name
    for name in config.tools.enabled
    if not str(name).startswith("audio.listen")
  ]
  return replace(config, tools=replace(config.tools, enabled=tool_names))


def main() -> int:
  parser = argparse.ArgumentParser(description="Listen for one Chinese industrial sorting command.")
  parser.add_argument("--config", type=Path, default=ROOT / "configs" / "robot_sorting_sim.yaml")
  parser.add_argument("--duration", type=float, default=15.0)
  parser.add_argument("--text", help="Use text instead of recording from the microphone.")
  parser.add_argument("--execute", action="store_true", help="Send robot commands to the Gazebo bridge.")
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
    active_config = replace(config, integrations=replace(config.integrations, robot=robot))
  if args.text is not None:
    active_config = _text_mode_config(active_config)

  bundle = build_agent(active_config)
  trace = TraceContext()
  transcript = args.text
  if transcript is None:
    result = bundle.tool_runtime.invoke(
      "audio.listen_vad_transcribe",
      {"duration_seconds": args.duration, "language": config.integrations.audio.get("listen_language", "zh")},
      trace,
    )
    if not result.success or not result.output:
      print(json.dumps({"success": False, "error": result.error}, ensure_ascii=False, indent=2))
      return 1
    transcript = str(result.output.get("text", "")).strip()

  try:
    command = parse_sorting_command(transcript)
  except ValueError as exc:
    print(json.dumps({"success": False, "transcript": transcript, "error": str(exc)}, ensure_ascii=False, indent=2))
    return 1

  response = bundle.agent.handle(AgentRequest(actionlist=ACTIONLIST, input=command, trace=trace))
  print(json.dumps({"success": response.success, "transcript": transcript, "command": command, "error": response.error, "result": response.result}, ensure_ascii=False, indent=2, default=str))
  return 0 if response.success else 1


if __name__ == "__main__":
  raise SystemExit(main())
