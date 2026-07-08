"""End-to-end tests for the SensorAgent CLI."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest import TestCase

ROOT = Path(__file__).resolve().parents[2]


class CliTest(TestCase):
  def test_mock_pick_place_cli(self) -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
      log_path = Path(temp_dir) / "cli_task.jsonl"
      env = os.environ.copy()
      env["PYTHONPATH"] = str(ROOT / "src")

      result = subprocess.run(
        [
          sys.executable,
          "-m",
          "sensoragent.services.cli.main",
          "mock-pick-place",
          "--config",
          str(ROOT / "configs" / "mock.yaml"),
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

      self.assertTrue(response["success"])
      self.assertEqual(response["result"]["object"]["label"], "silver roller")
      self.assertEqual(response["result"]["place"]["target"], "third bin cell")
      self.assertIn(str(log_path), log_line)
      self.assertTrue(log_path.exists())
      self.assertGreater(log_path.stat().st_size, 0)
