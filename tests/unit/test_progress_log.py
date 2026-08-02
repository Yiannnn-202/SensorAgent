"""Unit tests for human-readable progress-log persistence and runtime events."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest import TestCase

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
  sys.path.insert(0, str(SRC))

from sensoragent.logger import TaskLogger
from sensoragent.schemas import TraceContext


class ProgressLogTest(TestCase):
  def test_task_logger_writes_progress_file(self) -> None:
    with tempfile.TemporaryDirectory() as tmp:
      tmp_path = Path(tmp)
      jsonl_path = tmp_path / "run.jsonl"
      progress_path = tmp_path / "run.log"
      logger = TaskLogger(
        jsonl_path=jsonl_path,
        progress_path=progress_path,
        console=False,
      )
      trace = TraceContext(task_id="task_test", trace_id="trace_test")

      logger.log("tool_call_started", trace, {"tool": "vision.mock_detect"})

      # Both the structured JSONL and the human-readable progress file exist.
      self.assertTrue(jsonl_path.exists())
      self.assertTrue(progress_path.exists())
      content = progress_path.read_text(encoding="utf-8")
      self.assertIn("[tool] start vision.mock_detect", content)
      # Each progress line is prefixed with "YYYY-MM-DD HH:MM:SS ".
      self.assertRegex(
        content.splitlines()[-1], r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} "
      )

  def test_task_logger_progress_optional(self) -> None:
    trace = TraceContext(task_id="task_test", trace_id="trace_test")

    # No progress_path supplied: formatting/persistence is skipped cleanly.
    plain = TaskLogger()
    plain.log("tool_call_started", trace, {"tool": "vision.mock_detect"})
    self.assertEqual(list(plain.events()), ["tool_call_started"])

    # console=True without progress_path still works (stderr only) and must not
    # raise or require a progress file path.
    console_only = TaskLogger(console=True)
    console_only.log("tool_call_started", trace, {"tool": "vision.mock_detect"})
    self.assertEqual(list(console_only.events()), ["tool_call_started"])

  def test_runtime_spine_events_render_to_progress_file(self) -> None:
    with tempfile.TemporaryDirectory() as tmp:
      progress_path = Path(tmp) / "run.log"
      logger = TaskLogger(progress_path=progress_path, console=False)
      trace = TraceContext(task_id="task_abc", trace_id="trace_xyz")

      logger.log(
        "task_started",
        trace,
        {"user_input": "把红色方块放到第三个格子", "task_id": "task_abc"},
      )
      logger.log(
        "llm_plan_started", trace, {"user_input": "把红色方块放到第三个格子"}
      )
      logger.log(
        "llm_plan_finished",
        trace,
        {
          "target": "industrial.recovery_pick_place_tree",
          "target_kind": "DECISION_TREE",
        },
      )
      logger.log(
        "task_planned",
        trace,
        {
          "plan": {"target": "industrial.recovery_pick_place_tree"},
          "task_id": "task_abc",
        },
      )
      logger.log(
        "task_succeeded", trace, {"result": None, "task_id": "task_abc"}
      )

      content = progress_path.read_text(encoding="utf-8")
      self.assertIn('[agent] task start input="把红色方块放到第三个格子"', content)
      self.assertIn('[llm] request input="把红色方块放到第三个格子"', content)
      self.assertIn(
        "[llm] plan target=industrial.recovery_pick_place_tree kind=DECISION_TREE",
        content,
      )
      self.assertIn(
        "[agent] task plan target=industrial.recovery_pick_place_tree", content
      )
      self.assertIn("[agent] task ok task_id=task_abc", content)
