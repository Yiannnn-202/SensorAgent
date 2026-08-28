"""Contract tests for submission-facing tool inputs and outputs."""

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
from sensoragent.tools.vision.config_detect import VisionConfigDetectTool


def load_contract(tool_name: str) -> dict:
  path = ROOT / "contracts" / "tools" / f"{tool_name}.schema.json"
  return json.loads(path.read_text(encoding="utf-8"))


class ToolContractTest(TestCase):
  def test_vision_config_detect_contract(self) -> None:
    contract = load_contract("vision.config_detect")
    validator = ContractValidator(ROOT / "contracts")
    input_data = {"query": "roller"}
    validator.validate_tool_input("vision.config_detect", input_data)

    result = VisionConfigDetectTool({"roller": [0.1, 0.2, 0.3]}).run(
      ToolCall(tool="vision.config_detect", input=input_data, trace=TraceContext())
    )

    self.assertTrue(result.success)
    self.assertEqual(contract["name"], "vision.config_detect")
    validator.validate_tool_output("vision.config_detect", result.output)

  def test_dual_branch_contract_accepts_pipeline_metadata(self) -> None:
    validator = ContractValidator(ROOT / "contracts")
    output = {
      "found": True,
      "label": "roller",
      "confidence": 0.9,
      "source": "yolo11_seg",
      "vision_pipeline": {
        "name": "dual_branch",
        "selected_branch": "yolo11_seg",
        "route_order": ["yolo11_seg", "grounding_dino"],
        "fallback_used": False,
        "attempts": [{"branch": "yolo11_seg", "tool": "vision.yolo11_seg_detect", "success": True}],
      },
    }

    validator.validate_tool_output("vision.dual_branch_detect", output)
