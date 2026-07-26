"""Tests for the open-vocabulary vision tool contract."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest import TestCase, skipUnless

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
  sys.path.insert(0, str(SRC))

from sensoragent.agent import build_agent_from_config
from sensoragent.contracts import ContractValidator
from sensoragent.schemas import ToolCall, TraceContext
from sensoragent.tools.vision import (
  VisionDetection,
  VisionInferenceOptions,
  VisionOpenVocabularyDetectTool,
)


PIL_AVAILABLE = importlib.util.find_spec("PIL") is not None


class _FakeVisionBackend:
  def detect(
    self,
    *,
    query: str,
    image_path: str | None,
    depth_path: str | None,
    options: VisionInferenceOptions,
  ) -> VisionDetection:
    del image_path, depth_path, options
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
  def detect(
    self,
    *,
    query: str,
    image_path: str | None,
    depth_path: str | None,
    options: VisionInferenceOptions,
  ) -> VisionDetection:
    del image_path, depth_path, options
    return VisionDetection(
      found=True,
      label=query,
      confidence=0.77,
      object_id=f"{query}_001",
      bbox_2d=[1.0, 1.0, 3.0, 3.0],
      source="fake_yoloe",
    )


class _FakeWrongBoxBackend:
  def detect(
    self,
    *,
    query: str,
    image_path: str | None,
    depth_path: str | None,
    options: VisionInferenceOptions,
  ) -> VisionDetection:
    del image_path, depth_path, options
    return VisionDetection(
      found=True,
      label=query,
      confidence=0.9,
      object_id=f"{query}_wrong",
      bbox_2d=[0.0, 0.0, 1.0, 1.0],
      source="fake_yoloe",
    )


class _FakeMaskRefiner:
  def segment(
    self,
    *,
    image_path: str,
    bbox_2d: list[float],
    device: str | None,
  ) -> list[list[list[float]]]:
    del image_path, bbox_2d, device
    return [
      [[0.0, 0.0], [2.0, 0.0], [2.0, 2.0], [0.0, 2.0]],
    ]


class _FailingMaskRefiner:
  def segment(
    self,
    *,
    image_path: str,
    bbox_2d: list[float],
    device: str | None,
  ) -> list[list[list[float]]]:
    del image_path, bbox_2d, device
    raise RuntimeError("test SAM failure")


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

  def test_missing_depth_file_is_reported_as_input_error(self) -> None:
    result = VisionOpenVocabularyDetectTool(
      detector=_FakeBoxOnlyBackend(),
    ).run(
      ToolCall(
        tool="vision.open_vocab_detect",
        input={
          "query": "roller",
          "image_path": "rgb.npy",
          "depth_path": "missing-depth.npy",
          "camera_info": {
            "fx": 100.0,
            "fy": 100.0,
            "cx": 2.0,
            "cy": 2.0,
          },
        },
        trace=TraceContext(),
      )
    )

    self.assertFalse(result.success)
    self.assertIn("VISION_INPUT_ERROR", result.error or "")
    self.assertNotIn("VISION_MODEL_NOT_READY", result.error or "")

  def test_depth_projection_applies_position_base_offset(self) -> None:
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
        position_base_offset=[0.01, -0.02, 0.03],
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
    self.assertEqual(result.output["position_base"], [0.11, 0.18000000000000002, 1.33])
    self.assertEqual(result.output["pose_3d"], [0.11, 0.18000000000000002, 1.33, 0.0, 0.0, 0.0])

  def test_red_query_uses_largest_red_component(self) -> None:
    import json
    import tempfile
    import numpy as np

    with tempfile.TemporaryDirectory() as temp_dir:
      root = Path(temp_dir)
      image_path = root / "rgb.npy"
      depth_path = root / "depth.npy"
      camera_info_path = root / "camera_info.json"
      image = np.zeros((16, 16, 3), dtype=np.uint8)
      image[1:3, 1:3] = [220, 20, 20]
      image[8:14, 7:13] = [230, 30, 30]
      np.save(image_path, image)
      np.save(depth_path, np.ones((16, 16), dtype=np.float32))
      camera_info_path.write_text(
        json.dumps({"k": [100.0, 0.0, 0.0, 0.0, 100.0, 0.0, 0.0, 0.0, 1.0]}),
        encoding="utf-8",
      )

      result = VisionOpenVocabularyDetectTool(
        detector=_FakeWrongBoxBackend(),
        t_base_camera=[
          [1.0, 0.0, 0.0, 0.0],
          [0.0, 1.0, 0.0, 0.0],
          [0.0, 0.0, 1.0, 0.0],
          [0.0, 0.0, 0.0, 1.0],
        ],
      ).run(
        ToolCall(
          tool="vision.open_vocab_detect",
          input={
            "query": "red roller",
            "image_path": str(image_path),
            "depth_path": str(depth_path),
            "camera_info_path": str(camera_info_path),
          },
          trace=TraceContext(),
        )
      )

    self.assertTrue(result.success)
    self.assertEqual(result.output["source"], "red_color_filter")
    self.assertEqual(result.output["bbox_2d"], [7.0, 8.0, 12.0, 13.0])

  def test_mask_refinement_drives_centroid_and_depth_sampling(self) -> None:
    import json
    import tempfile
    import numpy as np

    with tempfile.TemporaryDirectory() as temp_dir:
      root = Path(temp_dir)
      image_path = root / "rgb.jpg"
      depth_path = root / "depth.npy"
      camera_info_path = root / "camera_info.json"
      image_path.write_bytes(b"fake image bytes")
      depth = np.full((5, 5), 10.0, dtype=np.float32)
      depth[0:2, 0:2] = 2.0
      np.save(depth_path, depth)
      camera_info_path.write_text(
        json.dumps({"fx": 100.0, "fy": 100.0, "cx": 0.0, "cy": 0.0}),
        encoding="utf-8",
      )

      result = VisionOpenVocabularyDetectTool(
        detector=_FakeBoxOnlyBackend(),
        mask_refiner=_FakeMaskRefiner(),
        refine_masks=True,
        t_base_camera=[
          [1.0, 0.0, 0.0, 0.0],
          [0.0, 1.0, 0.0, 0.0],
          [0.0, 0.0, 1.0, 0.0],
          [0.0, 0.0, 0.0, 1.0],
        ],
      ).run(
        ToolCall(
          tool="vision.open_vocab_detect",
          input={
            "query": "roller",
            "image_path": str(image_path),
            "depth_path": str(depth_path),
            "camera_info_path": str(camera_info_path),
          },
          trace=TraceContext(),
        )
      )

    self.assertTrue(result.success)
    self.assertEqual(result.output["source"], "fake_yoloe_sam2")
    self.assertEqual(result.output["mask_area_px"], 4.0)
    self.assertEqual(result.output["center_px"], [1.0, 1.0])
    self.assertEqual(result.output["depth_m"], 2.0)
    self.assertEqual(result.output["position_camera"], [0.02, 0.02, 2.0])
    self.assertEqual(result.output["position_base"], [0.02, 0.02, 2.0])
    ContractValidator(ROOT / "contracts").validate_tool_output(
      "vision.open_vocab_detect",
      result.output,
    )

  def test_mask_failure_falls_back_to_box_by_default(self) -> None:
    result = VisionOpenVocabularyDetectTool(
      detector=_FakeBoxOnlyBackend(),
      mask_refiner=_FailingMaskRefiner(),
      refine_masks=True,
    ).run(
      ToolCall(
        tool="vision.open_vocab_detect",
        input={"query": "roller", "image_path": "frame.jpg"},
        trace=TraceContext(),
      )
    )

    self.assertTrue(result.success)
    self.assertEqual(result.output["source"], "fake_yoloe_sam2_fallback_box")
    self.assertIn("test SAM failure", result.output["warnings"][0])

  def test_require_masks_rejects_sam_failure(self) -> None:
    result = VisionOpenVocabularyDetectTool(
      detector=_FakeBoxOnlyBackend(),
      mask_refiner=_FailingMaskRefiner(),
      refine_masks=True,
    ).run(
      ToolCall(
        tool="vision.open_vocab_detect",
        input={
          "query": "roller",
          "image_path": "frame.jpg",
          "require_masks": True,
        },
        trace=TraceContext(),
      )
    )

    self.assertFalse(result.success)
    self.assertIn("VISION_BACKEND_ERROR", result.error or "")
    self.assertIn("test SAM failure", result.error or "")

  @skipUnless(PIL_AVAILABLE, "Pillow is an optional vision dependency")
  def test_overlay_writes_box_mask_center_and_output_path(self) -> None:
    import tempfile
    from PIL import Image

    with tempfile.TemporaryDirectory() as temp_dir:
      root = Path(temp_dir)
      image_path = root / "frame.png"
      overlay_path = root / "outputs" / "frame_overlay.png"
      Image.new("RGB", (8, 8), (255, 255, 255)).save(image_path)

      result = VisionOpenVocabularyDetectTool(
        detector=_FakeBoxOnlyBackend(),
        mask_refiner=_FakeMaskRefiner(),
        refine_masks=True,
      ).run(
        ToolCall(
          tool="vision.open_vocab_detect",
          input={
            "query": "roller",
            "image_path": str(image_path),
            "overlay_path": str(overlay_path),
          },
          trace=TraceContext(),
        )
      )

      self.assertTrue(result.success)
      self.assertEqual(result.output["overlay_path"], str(overlay_path))
      self.assertGreater(result.output["timing_ms"]["overlay"], 0.0)
      self.assertTrue(overlay_path.is_file())
      self.assertNotEqual(
        Image.open(overlay_path).getpixel((1, 1)),
        (255, 255, 255),
      )
      ContractValidator(ROOT / "contracts").validate_tool_input(
        "vision.open_vocab_detect",
        {
          "query": "roller",
          "image_path": str(image_path),
          "overlay_path": str(overlay_path),
        },
      )
      ContractValidator(ROOT / "contracts").validate_tool_output(
        "vision.open_vocab_detect",
        result.output,
      )

  def test_robot_sim_config_registers_open_vocab_tool(self) -> None:
    config = build_agent_from_config(ROOT / "configs" / "robot_sim.yaml")

    self.assertIn("vision.open_vocab_detect", config.tool_registry.names())

  def test_grounding_dino_config_registers_without_loading_models(self) -> None:
    config = build_agent_from_config(
      ROOT / "configs" / "vision_grounding_dino.yaml"
    )

    self.assertEqual(config.tool_registry.names(), ["vision.open_vocab_detect"])
