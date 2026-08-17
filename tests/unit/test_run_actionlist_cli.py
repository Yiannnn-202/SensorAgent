"""Tests for the run-actionlist CLI argument plumbing."""

from __future__ import annotations

import io
import sys
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
  sys.path.insert(0, str(SRC))

from sensoragent.services.cli.main import _build_parser, _run_actionlist


class _RecordingAgent:
  def __init__(self) -> None:
    self.requests = []

  def handle(self, request):
    self.requests.append(request)
    return SimpleNamespace(success=True, result={"ok": True}, error=None)


def _parse(argv: list[str]):
  return _build_parser().parse_args(["run-actionlist", *argv])


class RunActionListCliArgsTest(TestCase):
  def test_actionlist_input_is_forwarded(self) -> None:
    args = _parse([
      "hardware.pick_object_actionlist",
      "--object-query",
      "silver bolt",
      "--pick-profile",
      "short_bolt",
      "--spatial-relation",
      "left",
      "--spatial-ordinal",
      "2",
      "--log-path",
      str(ROOT / "logs" / "tasks" / "unused.jsonl"),
    ])
    agent = _RecordingAgent()
    bundle = SimpleNamespace(agent=agent, tool_runtime=SimpleNamespace(invoke=lambda *a, **k: None))

    with patch("sensoragent.services.cli.main.build_agent_from_env", return_value=bundle):
      with redirect_stdout(io.StringIO()):
        exit_code = _run_actionlist(args)

    self.assertEqual(exit_code, 0)
    self.assertEqual(len(agent.requests), 1)
    request = agent.requests[0]
    self.assertEqual(request.actionlist, "hardware.pick_object_actionlist")
    self.assertEqual(request.input["object_query"], "silver bolt")
    self.assertEqual(request.input["pick_profile"], "short_bolt")
    self.assertEqual(request.input["spatial_constraint"], {"relation": "left", "ordinal": 2})
