"""Command-line entry point for SensorAgent."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Sequence

from sensoragent.agent import build_agent_from_env
from sensoragent.mcp import MockMcpEndpoint


def _default_task_log_path() -> Path:
  timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
  return Path("logs") / "tasks" / f"mock_pick_place_{timestamp}.jsonl"


def _build_parser() -> argparse.ArgumentParser:
  parser = argparse.ArgumentParser(
    prog="sensoragent",
    description="SensorAgent command-line tools.",
  )
  subparsers = parser.add_subparsers(dest="command", required=True)

  mock_pick = subparsers.add_parser(
    "mock-pick-place",
    help="Run the local mock pick-and-place Agent chain.",
  )
  mock_pick.add_argument(
    "--config",
    type=Path,
    default=None,
    help="Path to a SensorAgent config file. Defaults to env resolution.",
  )
  mock_pick.add_argument(
    "--object-query",
    default="silver roller",
    help="Object query passed to the mock vision tool.",
  )
  mock_pick.add_argument(
    "--target",
    default="third bin cell",
    help="Target location passed to the mock robot place tool.",
  )
  mock_pick.add_argument(
    "--log-path",
    type=Path,
    default=None,
    help="Path to the JSONL task log. Defaults to logs/tasks/*.jsonl.",
  )

  return parser


def _run_mock_pick_place(args: argparse.Namespace) -> int:
  log_path = args.log_path or _default_task_log_path()
  bundle = build_agent_from_env(args.config, log_path=log_path)
  endpoint = MockMcpEndpoint(bundle.agent)

  response = endpoint.call_skill(
    "mock.pick_and_place",
    {
      "object_query": args.object_query,
      "target": args.target,
    },
  )

  print(json.dumps(response.to_dict(), ensure_ascii=False, indent=2))
  print(f"Task log: {log_path}")
  return 0 if response.success else 1


def main(argv: Sequence[str] | None = None) -> int:
  parser = _build_parser()
  args = parser.parse_args(argv)

  if args.command == "mock-pick-place":
    return _run_mock_pick_place(args)

  parser.error(f"Unknown command: {args.command}")
  return 2


if __name__ == "__main__":
  raise SystemExit(main())
