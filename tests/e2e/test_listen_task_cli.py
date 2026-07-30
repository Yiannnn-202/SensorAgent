"""End-to-end tests for listen-task CLI."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
  sys.path.insert(0, str(SRC))

from sensoragent.services.cli import main as cli_main


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
      records = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
      events = [record["event"] for record in records]
      self.assertIn("listen_task_started", events)
      self.assertIn("listen_task_transcribed", events)
      self.assertIn("listen_task_agent_started", events)
      self.assertIn("listen_task_finished", events)

  def test_listen_task_cli_rejects_empty_transcript(self) -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
      log_path = Path(temp_dir) / "listen_task.jsonl"
      transcript_result = SimpleNamespace(
        success=True,
        output={
          "audio_path": str(Path(temp_dir) / "listen.wav"),
          "duration_ms": 1200,
          "sample_rate": 16000,
          "text": "",
          "confidence": 0.0,
          "language": "zh",
          "vad": {"enabled": True},
        },
        error=None,
      )
      bundle = SimpleNamespace(
        tool_runtime=SimpleNamespace(invoke=Mock(return_value=transcript_result)),
        agent=SimpleNamespace(run_task=Mock()),
        logger=Mock(),
      )
      args = SimpleNamespace(
        config=ROOT / "configs" / "audio_mock.yaml",
        planner="static",
        duration=None,
        language=None,
        audio_path=None,
        vad_threshold=None,
        vad_min_rms=None,
        vad_post_roll_ms=None,
        vad_tail_padding_ms=None,
        object_query="silver roller",
        target="third bin cell",
        log_path=log_path,
      )

      stdout = StringIO()
      with patch.object(cli_main, "build_agent_from_config", return_value=bundle):
        with redirect_stdout(stdout):
          return_code = cli_main._run_listen_task(args)

      self.assertEqual(return_code, 1)
      response_text, _, log_line = stdout.getvalue().partition("\nTask log:")
      response = json.loads(response_text)

      self.assertFalse(response["success"])
      self.assertEqual(response["error"], "EMPTY_TRANSCRIPT")
      self.assertEqual(response["transcript"]["text"], "")
      self.assertIn(str(log_path), log_line)
      bundle.agent.run_task.assert_not_called()
      bundle.tool_runtime.invoke.assert_called_once()
      listen_input = bundle.tool_runtime.invoke.call_args.args[1]
      self.assertEqual(listen_input["duration_seconds"], 8.0)
      self.assertEqual(listen_input["language"], "zh")
      self.assertEqual(listen_input["vad"]["threshold"], 0.35)
      self.assertGreaterEqual(bundle.logger.log.call_count, 3)

  def test_listen_task_cli_reads_audio_local_defaults(self) -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
      log_path = Path(temp_dir) / "listen_task.jsonl"
      transcript_result = SimpleNamespace(
        success=True,
        output={
          "audio_path": str(Path(temp_dir) / "listen.wav"),
          "duration_ms": 3900,
          "sample_rate": 16000,
          "text": "把滚轮放到三号格子。",
          "confidence": 1.0,
          "language": "zh",
          "vad": {"enabled": True},
        },
        error=None,
      )
      task = SimpleNamespace(
        task_id="task_001",
        error=None,
        plan=None,
        result={},
        status="succeeded",
        to_dict=lambda: {"task_id": "task_001", "status": "succeeded"},
      )
      bundle = SimpleNamespace(
        tool_runtime=SimpleNamespace(invoke=Mock(return_value=transcript_result)),
        agent=SimpleNamespace(run_task=Mock(return_value=task)),
        logger=Mock(),
      )
      args = SimpleNamespace(
        config=ROOT / "configs" / "audio_local.yaml",
        planner="static",
        duration=None,
        language=None,
        audio_path=None,
        vad_threshold=None,
        vad_min_rms=None,
        vad_post_roll_ms=None,
        vad_tail_padding_ms=None,
        object_query="roller",
        target="bin_cell_3",
        log_path=log_path,
      )

      stdout = StringIO()
      with patch.object(cli_main, "build_agent_from_config", return_value=bundle):
        with redirect_stdout(stdout):
          return_code = cli_main._run_listen_task(args)

      self.assertEqual(return_code, 0)
      listen_input = bundle.tool_runtime.invoke.call_args.args[1]
      self.assertEqual(listen_input["duration_seconds"], 8.0)
      self.assertEqual(listen_input["language"], "zh")
      self.assertEqual(listen_input["vad"]["threshold"], 0.35)
      self.assertEqual(listen_input["vad"]["min_rms"], 0.025)
      self.assertEqual(listen_input["vad"]["post_roll_ms"], 2500)
      self.assertEqual(listen_input["vad"]["tail_padding_ms"], 700)
