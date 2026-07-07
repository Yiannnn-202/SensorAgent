"""Contract tests for mock tool inputs and outputs."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from unittest import TestCase

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
  sys.path.insert(0, str(SRC))

from sensoragent.schemas import ToolCall, TraceContext
from sensoragent.tools.audio.mock import MockTranscribeTool
from sensoragent.tools.robot.mock import MockPickTool, MockPlaceTool
from sensoragent.tools.vision.mock import MockDetectTool


def load_contract(tool_name: str) -> dict[str, Any]:
  path = ROOT / "contracts" / "tools" / f"{tool_name}.schema.json"
  return json.loads(path.read_text(encoding="utf-8"))


def validate_schema(value: Any, schema: dict[str, Any], path: str = "$") -> None:
  expected_type = schema.get("type")
  if expected_type == "object":
    if not isinstance(value, dict):
      raise AssertionError(f"{path} expected object")
    for field in schema.get("required", []):
      if field not in value:
        raise AssertionError(f"{path}.{field} is required")
    properties = schema.get("properties", {})
    for field, field_value in value.items():
      if field in properties:
        validate_schema(field_value, properties[field], f"{path}.{field}")
    return

  if expected_type == "array":
    if not isinstance(value, list):
      raise AssertionError(f"{path} expected array")
    item_schema = schema.get("items")
    if item_schema:
      for index, item in enumerate(value):
        validate_schema(item, item_schema, f"{path}[{index}]")
    return

  if expected_type == "string":
    if not isinstance(value, str):
      raise AssertionError(f"{path} expected string")
    return

  if expected_type == "boolean":
    if not isinstance(value, bool):
      raise AssertionError(f"{path} expected boolean")
    return

  if expected_type == "number":
    if not isinstance(value, (int, float)) or isinstance(value, bool):
      raise AssertionError(f"{path} expected number")
    return

  if expected_type is not None:
    raise AssertionError(f"{path} unsupported schema type: {expected_type}")


class MockToolContractTest(TestCase):
  def test_vision_mock_detect_contract(self) -> None:
    contract = load_contract("vision.mock_detect")
    input_data = {"query": "silver roller"}
    validate_schema(input_data, contract["input_schema"])

    result = MockDetectTool().run(
      ToolCall(tool="vision.mock_detect", input=input_data, trace=TraceContext())
    )

    self.assertTrue(result.success)
    validate_schema(result.output, contract["output_schema"])

  def test_audio_mock_transcribe_contract(self) -> None:
    contract = load_contract("audio.mock_transcribe")
    input_data = {"text": "put the roller into the third bin cell"}
    validate_schema(input_data, contract["input_schema"])

    result = MockTranscribeTool().run(
      ToolCall(tool="audio.mock_transcribe", input=input_data, trace=TraceContext())
    )

    self.assertTrue(result.success)
    validate_schema(result.output, contract["output_schema"])

  def test_robot_mock_pick_contract(self) -> None:
    contract = load_contract("robot.mock_pick")
    input_data = {"object_id": "mock_object_001", "pose_3d": [0.42, -0.13, 0.08]}
    validate_schema(input_data, contract["input_schema"])

    result = MockPickTool().run(
      ToolCall(tool="robot.mock_pick", input=input_data, trace=TraceContext())
    )

    self.assertTrue(result.success)
    validate_schema(result.output, contract["output_schema"])

  def test_robot_mock_place_contract(self) -> None:
    contract = load_contract("robot.mock_place")
    input_data = {"object_id": "mock_object_001", "target": "third bin cell"}
    validate_schema(input_data, contract["input_schema"])

    result = MockPlaceTool().run(
      ToolCall(tool="robot.mock_place", input=input_data, trace=TraceContext())
    )

    self.assertTrue(result.success)
    validate_schema(result.output, contract["output_schema"])
