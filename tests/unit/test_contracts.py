"""Contract tests for mock tool inputs and outputs."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest import TestCase

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
  sys.path.insert(0, str(SRC))

from sensoragent.contracts import ContractValidator
from sensoragent.schemas import ToolCall, TraceContext
from sensoragent.tools.audio.mock import MockTranscribeTool
from sensoragent.tools.robot.mock import MockPickTool, MockPlaceTool
from sensoragent.tools.vision.mock import MockDetectTool


def load_contract(tool_name: str) -> dict[str, Any]:
  path = ROOT / "contracts" / "tools" / f"{tool_name}.schema.json"
  return json.loads(path.read_text(encoding="utf-8"))


class MockToolContractTest(TestCase):
  def test_vision_mock_detect_contract(self) -> None:
    contract = load_contract("vision.mock_detect")
    validator = ContractValidator(ROOT / "contracts")
    input_data = {"query": "silver roller"}
    validator.validate_tool_input("vision.mock_detect", input_data)

    result = MockDetectTool().run(
      ToolCall(tool="vision.mock_detect", input=input_data, trace=TraceContext())
    )

    self.assertTrue(result.success)
    self.assertEqual(contract["name"], "vision.mock_detect")
    validator.validate_tool_output("vision.mock_detect", result.output)

  def test_audio_mock_transcribe_contract(self) -> None:
    contract = load_contract("audio.mock_transcribe")
    validator = ContractValidator(ROOT / "contracts")
    input_data = {"text": "put the roller into the third bin cell"}
    validator.validate_tool_input("audio.mock_transcribe", input_data)

    result = MockTranscribeTool().run(
      ToolCall(tool="audio.mock_transcribe", input=input_data, trace=TraceContext())
    )

    self.assertTrue(result.success)
    self.assertEqual(contract["name"], "audio.mock_transcribe")
    validator.validate_tool_output("audio.mock_transcribe", result.output)

  def test_robot_mock_pick_contract(self) -> None:
    contract = load_contract("robot.mock_pick")
    validator = ContractValidator(ROOT / "contracts")
    input_data = {"object_id": "mock_object_001", "pose_3d": [0.42, -0.13, 0.08]}
    validator.validate_tool_input("robot.mock_pick", input_data)

    result = MockPickTool().run(
      ToolCall(tool="robot.mock_pick", input=input_data, trace=TraceContext())
    )

    self.assertTrue(result.success)
    self.assertEqual(contract["name"], "robot.mock_pick")
    validator.validate_tool_output("robot.mock_pick", result.output)

  def test_robot_mock_place_contract(self) -> None:
    contract = load_contract("robot.mock_place")
    validator = ContractValidator(ROOT / "contracts")
    input_data = {"object_id": "mock_object_001", "target": "third bin cell"}
    validator.validate_tool_input("robot.mock_place", input_data)

    result = MockPlaceTool().run(
      ToolCall(tool="robot.mock_place", input=input_data, trace=TraceContext())
    )

    self.assertTrue(result.success)
    self.assertEqual(contract["name"], "robot.mock_place")
    validator.validate_tool_output("robot.mock_place", result.output)
