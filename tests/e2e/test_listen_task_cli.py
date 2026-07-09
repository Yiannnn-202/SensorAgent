"""End-to-end tests for listen-task CLI."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest import TestCase

ROOT = Path(__file__).resolve().parents[2]


class ListenTaskCliTest(TestCase):
  def test_listen_task_cli_with_fake_recorder_and_static_planner(self) -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
      log_path = Path(temp_dir) / "listen_task.jsonl"
      audio_path = Path(temp_dir) / "listen.wav"
      env = os.environ.copy()
      env["PYTHONPATH"] = str(ROOT / "src")

      result = subprocess.run(
        [
          sys.executable,
          "-m",
          "sensoragent.services.cli.main",
          "listen-task",
          "--config",
          str(ROOT / "configs" / "audio_mock.yaml"),
          "--planner",
          "static",
          "--duration",
          "1",
          "--audio-path",
          str(audio_path),
          "--object-query",
          "silver roller",
          "--target",
          "third bin cell",
          "--log-path",
          str(log_path),
        ],
        cwd=ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
      )

      self.assertEqual(result.returncode, 0, msg=result.stderr)
      response_text, _, log_line = result.stdout.partition("\nTask log:")
      response = json.loads(response_text)

      self.assertIn("transcript", response)
      self.assertIn("task", response)
      self.assertEqual(response["task"]["status"], "succeeded")
      self.assertIn("银色滚柱", response["transcript"]["text"])
      self.assertTrue(audio_path.exists())
      self.assertIn(str(log_path), log_line)
      self.assertTrue(log_path.exists())
