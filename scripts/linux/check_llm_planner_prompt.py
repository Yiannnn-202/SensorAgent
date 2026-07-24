"""Offline sanity check for the DeepSeek-backed LLM planner.

Feeds a handful of Chinese / English / colloquial utterances through
LLMPlanner + OpenAICompatibleClient (no sim required) and prints:

- the raw JSON DeepSeek returned
- the resulting AgentPlan
- whether the planner's object_query resolves against the scene catalog in
  configs/robot_sim.yaml via vision.config_detect

Run:

  PYTHONPATH=src .venv/bin/python scripts/linux/check_llm_planner_prompt.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
  sys.path.insert(0, str(SRC))

from sensoragent.agent import LLMPlanner
from sensoragent.config import load_config
from sensoragent.integrations import OpenAICompatibleClient, load_llm_config_from_env
from sensoragent.schemas import ToolCall, TraceContext
from sensoragent.tools.vision.config_detect import VisionConfigDetectTool


UTTERANCES = [
  "把滚柱放到 bin_cell_3",
  "pick the roller and place into bin_cell_3",
  "put the silver roller into cell 3",
  "把那个银色的滚柱拿过去放到第三个格子",
  # pick-only cases
  "just grab the roller",
  "先把滚柱抓起来",
  # place-only cases
  "release what you are holding into bin_cell_3",
  "把手里的东西放到 3 号格子",
]

ALLOWED_TARGETS = (
  "industrial.pick_place_actionlist",
  "industrial.pick_only_actionlist",
  "industrial.place_only_actionlist",
  "mock.pick_place_actionlist",
  "audio.voice_command_ack_actionlist",
)


class _CapturingClient:
  """Wrap the real client so we can also see the raw JSON."""

  def __init__(self, inner: OpenAICompatibleClient) -> None:
    self._inner = inner
    self.last_raw: dict | None = None

  def complete_json(self, system_prompt: str, user_prompt: str) -> dict:
    result = self._inner.complete_json(system_prompt, user_prompt)
    self.last_raw = result
    return result


def _fmt(value) -> str:
  return json.dumps(value, ensure_ascii=False, indent=2)


def main() -> int:
  config = load_config(ROOT / "configs" / "robot_sim.yaml")
  detector = VisionConfigDetectTool(config.scene.objects)

  llm_config = load_llm_config_from_env()
  print(f"# DeepSeek endpoint: {llm_config.base_url}")
  print(f"# Model: {llm_config.model}")
  print(f"# Allowed targets: {ALLOWED_TARGETS}")
  print()

  client = _CapturingClient(OpenAICompatibleClient(llm_config))
  planner = LLMPlanner(
    client,
    allowed_targets=ALLOWED_TARGETS,
    allowed_place_targets=tuple(config.scene.place_targets.keys()),
  )

  for index, utterance in enumerate(UTTERANCES, start=1):
    print(f"=== case {index}: {utterance!r} ===")
    try:
      plan = planner.plan(utterance, {})
    except Exception as exc:
      print(f"planner FAILED: {exc}")
      if client.last_raw is not None:
        print(f"raw JSON: {_fmt(client.last_raw)}")
      print()
      continue

    print(f"raw JSON: {_fmt(client.last_raw)}")
    print(f"AgentPlan.target       = {plan.target}")
    print(f"AgentPlan.input        = {_fmt(plan.input)}")
    print(f"AgentPlan.intent       = {_fmt(plan.intent)}")
    print(f"AgentPlan.reason       = {plan.reason}")

    object_query = plan.input.get("object_query", "")
    detect = detector.run(
      ToolCall(
        tool="vision.config_detect",
        input={"query": object_query},
        trace=TraceContext(),
      )
    )
    if detect.success:
      hit = detect.output.get("label")
      pose = detect.output.get("pose_3d")
      print(f"catalog match          = {hit}  pose={pose}")
    else:
      print(f"catalog match          = MISS ({detect.error})")
    print()

  return 0


if __name__ == "__main__":
  sys.exit(main())
