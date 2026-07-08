"""Unit tests for JSONL log shape."""

from __future__ import annotations

import json
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


class JsonlLogShapeTest(TestCase):
  def test_task_logger_writes_expected_jsonl_shape(self) -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
      log_path = Path(temp_dir) / "task.jsonl"
      logger = TaskLogger(log_path)
      trace = TraceContext(task_id="task_shape", trace_id="trace_shape")

      logger.log("shape_event", trace, {"value": 1})

      line = log_path.read_text(encoding="utf-8").strip()
      payload = json.loads(line)

      self.assertEqual(
        sorted(payload.keys()),
        ["event", "payload", "task_id", "timestamp", "trace_id"],
      )
      self.assertEqual(payload["event"], "shape_event")
      self.assertEqual(payload["task_id"], "task_shape")
      self.assertEqual(payload["trace_id"], "trace_shape")
      self.assertEqual(payload["payload"], {"value": 1})
      self.assertIsInstance(payload["timestamp"], str)
