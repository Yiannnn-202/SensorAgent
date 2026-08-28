#!/usr/bin/env python3
"""Run the competition multi-instance sorting loop with text or real voice."""

from __future__ import annotations

import argparse
from dataclasses import asdict, replace
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import TextIO


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
  sys.path.insert(0, str(SRC))

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
  sys.path.insert(0, str(SCRIPT_DIR))

from agent_bridge_support import (  # noqa: E402
  check_bridge,
  wait_for_bridge,
  wait_for_ready,
)

from sensoragent.agent import AgentBundle, build_agent  # noqa: E402
from sensoragent.config import SensorAgentConfig, load_config  # noqa: E402
from sensoragent.integrations import OpenAICompatibleClient, load_llm_config_from_env  # noqa: E402
from sensoragent.grounding import (  # noqa: E402
  GroundingStatus,
  LlmAssistedSortingCommandGrounder,
  ObjectOntology,
  SortingCommandGrounder,
)
from sensoragent.schemas import TraceContext  # noqa: E402
from sensoragent.state import CompetitionWorldState  # noqa: E402


SIM_DECISION_TREE = "industrial.recovery_pick_place_tree"
HARDWARE_ACTIONLIST = "hardware.pick_place_actionlist"
EXIT_COMMANDS = {"退出", "结束", "exit", "quit", "q"}
STATUS_COMMANDS = {"状态", "status"}


def _default_jsonl_path() -> Path:
  timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
  return ROOT / "logs" / "tasks" / f"competition_sorting_{timestamp}.jsonl"


def prepare_config(
  config: SensorAgentConfig,
  *,
  execute: bool,
  voice_enabled: bool,
) -> SensorAgentConfig:
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


class CompetitionSortingSession:
  """Ground commands, select instances, execute, and recover within a budget."""

  def __init__(
    self,
    config: SensorAgentConfig,
    bundle: AgentBundle,
    *,
    backend: str = "sim",
    llm_grounding: bool = False,
    max_recovery_attempts: int = 1,
  ) -> None:
    self.config = config
    self.bundle = bundle
    self.backend = backend
    if self.backend not in {"sim", "hardware"}:
      raise ValueError("backend must be sim or hardware")
    self.actionlist_name = HARDWARE_ACTIONLIST if self.backend == "hardware" else None
    self.decision_tree_name = SIM_DECISION_TREE if self.backend == "sim" else None
    self.ontology = ObjectOntology.from_mapping(config.scene.object_ontology)
    base_grounder = SortingCommandGrounder(
      self.ontology,
      config.scene.place_targets,
    )
    self.grounder = (
      LlmAssistedSortingCommandGrounder(
        base_grounder,
        self.ontology,
        config.scene.place_targets,
        OpenAICompatibleClient(load_llm_config_from_env()),
      )
      if llm_grounding
      else base_grounder
    )
    self.resolver = None
    self.world = CompetitionWorldState(
      tuple(config.scene.place_targets),
    )
    self.max_recovery_attempts = max(0, int(max_recovery_attempts))

  def handle_text(self, text: str, *, turn_index: int) -> dict:
    normalized = "".join(text.strip().casefold().split())
    if normalized in EXIT_COMMANDS:
      return {
        "type": "exit",
        "success": True,
        "turn_index": turn_index,
        "transcript": text.strip(),
      }
    if normalized in STATUS_COMMANDS:
      return {
        "type": "status",
        "success": True,
        "turn_index": turn_index,
        "world_state": self.world.to_dict(),
      }

    intent = self.grounder.ground(text)
    base_result = {
      "type": "command",
      "turn_index": turn_index,
      "transcript": text.strip(),
      "intent": intent.to_dict(),
      "grounding_source": intent.grounding_source,
      "backend": self.backend,
      "perception_backend": (
        "hardware_rgbd" if self.backend == "hardware" else "gazebo_rgbd"
      ),
      "agent_loop": [
        "idle",
        "understand",
        "check_world",
        "observe",
        "perceive",
        "select",
        "plan",
        "act",
        "verify",
        "recover_if_needed",
        "complete",
      ],
    }
    if intent.status != GroundingStatus.READY:
      return {
        **base_result,
        "success": False,
        "status": intent.status,
        "error": intent.reason,
        "clarification": intent.clarification,
      }
    if intent.quantity == "all":
      return self._handle_batch(intent, base_result)
    if intent.target is None:
      return {
        **base_result,
        "success": False,
        "status": GroundingStatus.NEEDS_CLARIFICATION,
        "error": "TARGET_REQUIRED",
        "clarification": "当前完整流程需要指定目标格。",
      }
    if not self.world.target_available(intent.target):
      occupied_by = self.world.bins[intent.target].occupied_by
      return {
        **base_result,
        "success": False,
        "status": GroundingStatus.NEEDS_CLARIFICATION,
        "error": "TARGET_OCCUPIED",
        "clarification": (
          f"{intent.target} 已被 {occupied_by} 占用，请选择其他空格。"
        ),
      }
    if self.backend == "sim" and intent.selector is None and intent.object_class is not None:
      object_class = self.ontology.get(intent.object_class)
      if len(object_class.instance_ids) > 1:
        return {
          **base_result,
          "success": False,
          "status": GroundingStatus.NEEDS_CLARIFICATION,
          "error": "INSTANCE_AMBIGUOUS",
          "clarification": (
            f"检测到多个{object_class.display_name}，"
            "请说明左、右、前、后、最近、最远或第几个。"
          ),
        }

    if self.backend == "hardware":
      execution = self._execute_with_recovery(
        intent.raw_text,
        intent.target,
        pick_profile=intent.object_class or "",
        spatial_constraint=(
          asdict(intent.selector) if intent.selector is not None else {}
        ),
      )
      if execution["success"]:
        self.world.record(
          "hardware_task_completed",
          object_class=intent.object_class,
          target=intent.target,
        )
      else:
        self.world.record(
          "hardware_task_failed",
          object_class=intent.object_class,
          target=intent.target,
          error=execution.get("error"),
        )
      return {
        **base_result,
        "success": execution["success"],
        "status": "completed" if execution["success"] else "failed",
        "selected_instance": None,
        "execution": execution,
        "world_state": self.world.to_dict(),
      }

    object_query = self._vision_query(intent.object_class)
    execution = self._execute_with_recovery(
      object_query,
      intent.target,
      spatial_constraint=(
        asdict(intent.selector) if intent.selector is not None else {}
      ),
    )
    if execution["success"]:
      self.world.record(
        "sim_visual_task_completed",
        object_class=intent.object_class,
        object_query=object_query,
        target=intent.target,
      )
    else:
      self.world.record(
        "sim_visual_task_failed",
        object_class=intent.object_class,
        object_query=object_query,
        target=intent.target,
        error=execution.get("error"),
      )
    return {
      **base_result,
      "success": execution["success"],
      "status": "completed" if execution["success"] else "failed",
      "selected_instance": None,
      "execution": execution,
      "world_state": self.world.to_dict(),
    }

  def _vision_query(self, object_class: str | None) -> str:
    if object_class is None:
      return ""
    item = self.ontology.get(object_class)
    return item.vision_queries[0] if item.vision_queries else item.class_id

  def _handle_batch(self, intent, base_result: dict) -> dict:
    """Queue every remaining instance of the class, one cell per instance.

    Cells fill from the named target onwards; a subtask failure stops the
    batch so the remaining queue and the failed object stay on record.
    """

    if self.resolver is None:
      return {
        **base_result,
        "success": False,
        "status": GroundingStatus.UNSUPPORTED,
        "error": "BATCH_UNSUPPORTED",
        "clarification": "视觉模式当前不支持批量全类分拣，请逐条指定目标零件和目标格。",
      }
    queue = self.resolver.candidates(
      intent.object_class,
      excluded=self.world.unavailable_instances,
    )
    if not queue:
      return {
        **base_result,
        "success": False,
        "status": GroundingStatus.NEEDS_CLARIFICATION,
        "error": "NO_REMAINING_INSTANCES",
        "clarification": "当前场景中没有剩余的该类零件。",
      }
    remaining_cells = sum(
      1 for cell in self.world.bins.values() if cell.status == "empty"
    )
    if remaining_cells < len(queue):
      return {
        **base_result,
        "success": False,
        "status": GroundingStatus.NEEDS_CLARIFICATION,
        "error": "NOT_ENOUGH_EMPTY_CELLS",
        "clarification": (
          f"剩余 {len(queue)} 个实例但只有 {remaining_cells} 个空格。"
        ),
      }

    self.world.record(
      "batch_task_started",
      object_class=intent.object_class,
      start_target=intent.target,
      queue=[instance.instance_id for instance in queue],
    )
    subtasks: list[dict] = []
    for position, instance in enumerate(queue):
      target = self.world.next_empty_cell(start_from=intent.target)
      if target is None:
        break
      self.world.observe(instance)
      self.world.select(instance.instance_id, target)
      execution = self._execute_with_recovery(instance.instance_id, target)
      subtask = {
        "position": position + 1,
        "instance_id": instance.instance_id,
        "target": target,
        "success": execution["success"],
        "execution": execution,
      }
      subtasks.append(subtask)
      if execution["success"]:
        self.world.mark_placed(instance.instance_id, target)
        self.world.record(
          "batch_subtask_completed",
          instance_id=instance.instance_id,
          target=target,
          position=position + 1,
        )
      else:
        self.world.mark_failed(
          instance.instance_id,
          str(execution.get("error") or "workflow failed"),
        )
        remaining = [item.instance_id for item in queue[position + 1:]]
        self.world.record(
          "batch_task_interrupted",
          failed_instance=instance.instance_id,
          error=execution.get("error"),
          remaining_queue=remaining,
        )
        return {
          **base_result,
          "success": False,
          "status": "failed",
          "type": "batch_command",
          "subtasks": subtasks,
          "failed_instance": instance.instance_id,
          "remaining_queue": remaining,
          "world_state": self.world.to_dict(),
        }

    self.world.record(
      "batch_task_finished",
      placed=[subtask["instance_id"] for subtask in subtasks],
    )
    return {
      **base_result,
      "success": True,
      "status": "completed",
      "type": "batch_command",
      "subtasks": subtasks,
      "world_state": self.world.to_dict(),
    }

  def _execute_with_recovery(
    self,
    object_query: str,
    target: str,
    *,
    pick_profile: str = "",
    spatial_constraint: dict | None = None,
  ) -> dict:
    attempts: list[dict] = []
    input_data = {
      "object_query": object_query,
      "target": target,
    }
    if self.actionlist_name is not None:
      actionlist = self.bundle.actionlists[self.actionlist_name]
      if "pick_profile" in actionlist.inputs:
        input_data["pick_profile"] = pick_profile
      if "spatial_constraint" in actionlist.inputs:
        input_data["spatial_constraint"] = spatial_constraint or {}
    elif self.decision_tree_name is not None:
      input_data["spatial_constraint"] = spatial_constraint or {}
      input_data["max_recovery_attempts"] = self.max_recovery_attempts
      actionlist = None
    else:
      raise RuntimeError("No executable workflow is configured for this session")
    for attempt in range(1, self.max_recovery_attempts + 2):
      trace = TraceContext()
      if actionlist is not None:
        result = self.bundle.actionlist_runtime.run(actionlist, input_data, trace)
        step_records = [asdict(step) for step in result.steps]
        workflow_name = self.actionlist_name
      else:
        tree = self.bundle.decision_trees[self.decision_tree_name or ""]
        result = self.bundle.decision_tree_runtime.run(tree, input_data, trace)
        step_records = [asdict(node) for node in result.nodes]
        workflow_name = self.decision_tree_name
      if isinstance(result.output, dict) and isinstance(result.output.get("world_state"), dict):
        self.world.merge_runtime_state(result.output["world_state"])
      attempt_result = {
        "attempt": attempt,
        "success": result.success,
        "error": result.error,
        "trace": trace.to_dict(),
        "steps": step_records,
      }
      attempts.append(attempt_result)
      if result.success:
        return {
          "success": True,
          "workflow": workflow_name,
          "attempts": attempts,
          "recovery_attempts": attempt - 1,
        }
      if actionlist is None:
        break
      if attempt > self.max_recovery_attempts:
        break

      failed_step = next(
        (step for step in reversed(result.steps) if not step.success),
        None,
      )
      evidence = {
        "failed_step": failed_step.step if failed_step else "unknown",
        "error": result.error,
        "output": failed_step.output if failed_step else None,
      }
      classification = self.bundle.tool_runtime.invoke(
        "recovery.classify_failure",
        {"evidence": evidence},
        trace,
      )
      attempt_result["classification"] = (
        classification.output if classification.success else None
      )
      attempt_result["classification_error"] = classification.error
      if not classification.success or not classification.output:
        break
      recovery = self.bundle.tool_runtime.invoke(
        "recovery.plan",
        {
          "classification": classification.output,
          "context": {"max_recovery_attempts": self.max_recovery_attempts},
        },
        trace,
      )
      attempt_result["recovery_plan"] = (
        recovery.output if recovery.success else None
      )
      attempt_result["recovery_error"] = recovery.error
      if (
        not recovery.success
        or not recovery.output
        or not recovery.output.get("retryable")
      ):
        break
      self.world.increment_recovery()
      stopped = self.bundle.tool_runtime.invoke("robot.stop", {}, trace)
      attempt_result["stop_before_retry"] = {
        "success": stopped.success,
        "error": stopped.error,
      }
      if not stopped.success:
        break

    return {
      "success": False,
      "workflow": self.actionlist_name or self.decision_tree_name,
      "error": attempts[-1]["error"] if attempts else "workflow failed",
      "attempts": attempts,
      "recovery_attempts": max(0, len(attempts) - 1),
    }


def _append_jsonl(path: Path, value: dict) -> None:
  path.parent.mkdir(parents=True, exist_ok=True)
  with path.open("a", encoding="utf-8") as stream:
    stream.write(json.dumps(value, ensure_ascii=False, default=str) + "\n")


def _print_json(value: dict, stream: TextIO) -> None:
  print(json.dumps(value, ensure_ascii=False, indent=2, default=str), file=stream)
  stream.flush()


def _listen(bundle: AgentBundle, config: SensorAgentConfig, duration: float) -> dict:
  trace = TraceContext()
  result = bundle.tool_runtime.invoke(
    "audio.listen_vad_transcribe",
    {
      "duration_seconds": duration,
      "language": config.integrations.audio.get("listen_language", "zh"),
      "vad": {
        "threshold": config.integrations.audio.get("vad_threshold", 0.35),
        "min_rms": config.integrations.audio.get("vad_min_rms", 0.0),
        "min_speech_windows": config.integrations.audio.get(
          "vad_min_speech_windows",
          2,
        ),
        "pre_roll_ms": config.integrations.audio.get("vad_pre_roll_ms", 120),
        "post_roll_ms": config.integrations.audio.get(
          "vad_post_roll_ms",
          2500,
        ),
        "tail_padding_ms": config.integrations.audio.get(
          "vad_tail_padding_ms",
          700,
        ),
        "max_utterance_sec": config.integrations.audio.get(
          "vad_max_utterance_sec",
          15,
        ),
      },
    },
    trace,
  )
  return {
    "success": result.success,
    "error": result.error,
    "output": result.output,
  }


def _parser() -> argparse.ArgumentParser:
  parser = argparse.ArgumentParser(
    description="Run the competition multi-instance sorting session.",
  )
  parser.add_argument(
    "--config",
    type=Path,
    default=ROOT / "configs" / "robot_sorting_sim.yaml",
  )
  parser.add_argument("--backend", choices=("sim", "hardware"), default="sim")
  parser.add_argument("--mode", choices=("text", "voice"), default="text")
  parser.add_argument("--command", help="Run one text command and exit.")
  parser.add_argument("--execute", action="store_true")
  parser.add_argument("--duration", type=float, default=15.0)
  parser.add_argument(
    "--llm-grounding",
    action="store_true",
    help=(
      "Use constrained LLM fallback only when deterministic industrial "
      "grounding cannot map the command."
    ),
  )
  parser.add_argument("--max-turns", type=int, default=None)
  parser.add_argument("--max-recovery-attempts", type=int, default=1)
  parser.add_argument("--jsonl-out", type=Path, default=None)
  return parser


def main(argv: list[str] | None = None) -> int:
  args = _parser().parse_args(argv)
  if args.max_turns is not None and args.max_turns < 1:
    raise ValueError("--max-turns must be >= 1")
  if args.max_recovery_attempts < 0:
    raise ValueError("--max-recovery-attempts must be >= 0")

  config = load_config(args.config)
  endpoint = str(
    config.integrations.robot.get("endpoint", "http://127.0.0.1:8765")
  )
  if args.execute:
    wait_for_bridge(endpoint, 30.0)
    check_bridge(endpoint)
    wait_for_ready(
      endpoint,
      60.0,
      ("move_action", "execute_trajectory", "cartesian_path", "gripper_cmd"),
    )
  active_config = prepare_config(
    config,
    execute=args.execute,
    voice_enabled=args.mode == "voice",
  )
  jsonl_path = args.jsonl_out or _default_jsonl_path()
  bundle = build_agent(active_config, log_path=jsonl_path.with_suffix(".trace.jsonl"))
  session = CompetitionSortingSession(
    active_config,
    bundle,
    backend=args.backend,
    llm_grounding=args.llm_grounding,
    max_recovery_attempts=args.max_recovery_attempts,
  )

  if args.command is not None:
    result = session.handle_text(args.command, turn_index=0)
    _append_jsonl(jsonl_path, result)
    _print_json(result, sys.stdout)
    return 0 if result["success"] else 2

  turn_index = 0
  while args.max_turns is None or turn_index < args.max_turns:
    if args.mode == "text":
      print("> ", end="", file=sys.stderr, flush=True)
      line = sys.stdin.readline()
      if line == "":
        return 0
      transcript = line.strip()
    else:
      listen = _listen(bundle, active_config, args.duration)
      if not listen["success"] or not listen["output"]:
        result = {
          "type": "listen",
          "success": False,
          "turn_index": turn_index,
          "error": listen["error"],
        }
        _append_jsonl(jsonl_path, result)
        _print_json(result, sys.stdout)
        turn_index += 1
        continue
      transcript = str(listen["output"].get("text", "")).strip()

    result = session.handle_text(transcript, turn_index=turn_index)
    _append_jsonl(jsonl_path, result)
    _print_json(result, sys.stdout)
    turn_index += 1
    if result["type"] == "exit":
      return 0
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
