"""Tests for the open-vocabulary vision tool contract."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest import TestCase

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
  sys.path.insert(0, str(SRC))

from sensoragent.agent import build_agent_from_config
from sensoragent.contracts import ContractValidator
from sensoragent.schemas import ToolCall, TraceContext
from sensoragent.tools.vision import VisionDetection, VisionOpenVocabularyDetectTool


class _FakeVisionBackend:
  def detect(self, *, query: str, image_path: str | None, depth_path: str | None) -> VisionDetection:
    return VisionDetection(
      found=True,
      label=query,
      confidence=0.88,
      object_id=f"{query}_001",
      bbox_2d=[10.0, 20.0, 50.0, 80.0],
      position_base=[0.24, 0.23, 0.142],
      pose_3d=[0.24, 0.23, 0.142, 0.0, 0.0, 0.0],
      source="fake_yoloe",
    )


class _FakeBoxOnlyBackend:
  def detect(self, *, query: str, image_path: str | None, depth_path: str | None) -> VisionDetection:
    return VisionDetection(
      found=True,
      label=query,
      confidence=0.77,
      object_id=f"{query}_001",
      bbox_2d=[1.0, 1.0, 3.0, 3.0],
      source="fake_yoloe",
    )


class VisionOpenVocabularyToolTest(TestCase):
  def test_placeholder_reports_model_not_ready(self) -> None:
    result = VisionOpenVocabularyDetectTool(
      model_path="models/vision/missing-yoloe.pt",
      backend="yoloe",
    ).run(
      ToolCall(
        tool="vision.open_vocab_detect",
        input={"query": "roller", "image_path": "frame.png"},
        trace=TraceContext(),
      )
    )

    self.assertFalse(result.success)
    self.assertIn("VISION_MODEL_NOT_READY", result.error or "")
    self.assertEqual(result.output["model_path"], "models/vision/missing-yoloe.pt")

  def test_injected_backend_returns_stable_detection_shape(self) -> None:
    result = VisionOpenVocabularyDetectTool(
      detector=_FakeVisionBackend(),
    ).run(
      ToolCall(
        tool="vision.open_vocab_detect",
        input={"query": "roller", "image_path": "frame.png", "depth_path": "depth.npy"},
        trace=TraceContext(),
      )
    )

    self.assertTrue(result.success)
    self.assertEqual(result.output["label"], "roller")
    self.assertEqual(result.output["bbox_2d"], [10.0, 20.0, 50.0, 80.0])
    self.assertEqual(result.output["pose_3d"], [0.24, 0.23, 0.142, 0.0, 0.0, 0.0])

  def test_contract_accepts_successful_detection_output(self) -> None:
    validator = ContractValidator(ROOT / "contracts")
    input_data = {"query": "roller", "image_path": "frame.png", "depth_path": "depth.npy"}
    validator.validate_tool_input("vision.open_vocab_detect", input_data)

    result = VisionOpenVocabularyDetectTool(detector=_FakeVisionBackend()).run(
      ToolCall(tool="vision.open_vocab_detect", input=input_data, trace=TraceContext())
    )

    self.assertTrue(result.success)
    validator.validate_tool_output("vision.open_vocab_detect", result.output)

  def test_depth_projection_adds_pose_3d_to_bbox_detection(self) -> None:
    import json
    import tempfile
    import numpy as np

    with tempfile.TemporaryDirectory() as temp_dir:
      root = Path(temp_dir)
      depth_path = root / "depth.npy"
      camera_info_path = root / "camera_info.json"
      np.save(depth_path, np.ones((5, 5), dtype=np.float32))
      camera_info_path.write_text(
        json.dumps({"k": [100.0, 0.0, 2.0, 0.0, 100.0, 2.0, 0.0, 0.0, 1.0]}),
        encoding="utf-8",
      )

      result = VisionOpenVocabularyDetectTool(
        detector=_FakeBoxOnlyBackend(),
        t_base_camera=[
          [1.0, 0.0, 0.0, 0.1],
          [0.0, 1.0, 0.0, 0.2],
          [0.0, 0.0, 1.0, 0.3],
          [0.0, 0.0, 0.0, 1.0],
        ],
      ).run(
        ToolCall(
          tool="vision.open_vocab_detect",
          input={
            "query": "roller",
            "image_path": "rgb.npy",
            "depth_path": str(depth_path),
            "camera_info_path": str(camera_info_path),
          },
          trace=TraceContext(),
        )
      )

    self.assertTrue(result.success)
    self.assertEqual(result.output["position_camera"], [0.0, 0.0, 1.0])
    self.assertEqual(result.output["position_base"], [0.1, 0.2, 1.3])
    self.assertEqual(result.output["pose_3d"], [0.1, 0.2, 1.3, 0.0, 0.0, 0.0])

  def test_robot_sim_config_registers_open_vocab_tool(self) -> None:
    config = build_agent_from_config(ROOT / "configs" / "robot_sim.yaml")

    self.assertIn("vision.open_vocab_detect", config.tool_registry.names())
