"""Tests for the vision-detect CLI argument plumbing.

These stay in-process and stub the tool runtime, so no model weights are
downloaded and no image is read. They only pin down how CLI flags become the
`vision.open_vocab_detect` tool input.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
  sys.path.insert(0, str(SRC))

from sensoragent.schemas import ToolResult
from sensoragent.services.cli.main import _build_parser, _run_vision_detect
from sensoragent.tools.vision import SPATIAL_RELATIONS, SpatialConstraint


class _RecordingToolRuntime:
  def __init__(self) -> None:
    self.calls: list[tuple[str, dict]] = []

  def invoke(self, name, input_data, trace=None):
    del trace
    self.calls.append((name, dict(input_data)))
    return ToolResult(tool=name, success=True, output={"found": True})


def _parse(argv: list[str]):
  return _build_parser().parse_args(["vision-detect", *argv])


class VisionDetectCliArgsTest(TestCase):
  def _run(self, argv: list[str], tmp_log: Path) -> dict:
    args = _parse([*argv, "--log-path", str(tmp_log)])
    runtime = _RecordingToolRuntime()
    bundle = SimpleNamespace(tool_runtime=runtime)
    with patch(
      "sensoragent.services.cli.main.build_agent_from_env",
      return_value=bundle,
    ):
      exit_code = _run_vision_detect(args)
    self.assertEqual(exit_code, 0)
    self.assertEqual(len(runtime.calls), 1)
    name, input_data = runtime.calls[0]
    self.assertEqual(name, "vision.open_vocab_detect")
    return input_data

  def test_spatial_constraint_absent_by_default(self) -> None:
    with self.subTest("no flag"):
      input_data = self._run(
        ["--image", "scene.jpg", "--query", "roller"],
        Path("logs") / "tasks" / "unused.jsonl",
      )
      self.assertNotIn("spatial_constraint", input_data)

  def test_spatial_relation_becomes_tool_input(self) -> None:
    input_data = self._run(
      ["--image", "scene.jpg", "--query", "roller", "--spatial-relation", "left"],
      Path("logs") / "tasks" / "unused.jsonl",
    )
    self.assertEqual(
      input_data["spatial_constraint"],
      {"relation": "left", "ordinal": 1},
    )

  def test_spatial_ordinal_is_forwarded(self) -> None:
    input_data = self._run(
      [
        "--image",
        "scene.jpg",
        "--query",
        "roller",
        "--spatial-relation",
        "right",
        "--spatial-ordinal",
        "2",
      ],
      Path("logs") / "tasks" / "unused.jsonl",
    )
    self.assertEqual(
      input_data["spatial_constraint"],
      {"relation": "right", "ordinal": 2},
    )

  def test_cli_relations_match_the_tool(self) -> None:
    """The CLI choices must not drift from what the tool actually accepts."""

    for relation in sorted(SPATIAL_RELATIONS):
      with self.subTest(relation=relation):
        args = _parse(
          ["--image", "scene.jpg", "--query", "roller", "--spatial-relation", relation]
        )
        self.assertEqual(args.spatial_relation, relation)

  def test_every_cli_relation_survives_from_call(self) -> None:
    for relation in sorted(SPATIAL_RELATIONS):
      with self.subTest(relation=relation):
        constraint = SpatialConstraint.from_call({"relation": relation, "ordinal": 1})
        self.assertIsNotNone(constraint)
        self.assertEqual(constraint.relation, relation)

  def test_invalid_relation_is_rejected_by_the_parser(self) -> None:
    with self.assertRaises(SystemExit):
      _parse(["--image", "scene.jpg", "--query", "roller", "--spatial-relation", "up"])

  def test_non_positive_ordinal_is_rejected(self) -> None:
    args = _parse(
      [
        "--image",
        "scene.jpg",
        "--query",
        "roller",
        "--spatial-relation",
        "left",
        "--spatial-ordinal",
        "0",
      ]
    )
    with self.assertRaises(SystemExit):
      _run_vision_detect(args)
