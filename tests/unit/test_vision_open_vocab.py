"""Tests for the open-vocabulary vision tool contract."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase, skipUnless

import numpy as np

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
from sensoragent.tools.vision.open_vocab import (
  UltralyticsOpenVocabularyBackend,
  UltralyticsSam2Backend,
)


PIL_AVAILABLE = importlib.util.find_spec("PIL") is not None


class _FakeTensor:
  def __init__(self, values) -> None:
    self._values = np.asarray(values)

  def cpu(self):
    return self

  def numpy(self):
    return self._values


class _FakeBoxes:
  def __init__(self) -> None:
    self.xyxy = _FakeTensor([[0, 0, 20, 20], [30, 0, 50, 20]])
    self.conf = _FakeTensor([0.99, 0.75])
    self.cls = _FakeTensor([0, 1])

  def __len__(self) -> int:
    return 2


class _FakeFixedClassModel:
  def predict(self, **kwargs):
    del kwargs
    return [
      SimpleNamespace(
        boxes=_FakeBoxes(),
        masks=None,
        names={0: "gear", 1: "roller"},
      )
    ]


class _RecordingFixedClassModel(_FakeFixedClassModel):
  def __init__(self) -> None:
    self.predict_arguments: dict[str, object] | None = None

  def predict(self, **kwargs):
    self.predict_arguments = dict(kwargs)
    return super().predict(**kwargs)


def test_fixed_class_model_filters_predictions_by_query() -> None:
  backend = object.__new__(UltralyticsOpenVocabularyBackend)
  backend._model_path = Path("models/vision/industrial_student_best.pt")
  backend._backend = "yolo_seg"
  backend._model = _FakeFixedClassModel()

  detections = backend.detect_all(
    query="silver roller",
    image_path="frame.jpg",
    depth_path=None,
    options=VisionInferenceOptions(),
  )

  assert len(detections) == 1
  assert detections[0].found
  assert detections[0].label == "roller"
  assert detections[0].confidence == 0.75


def test_yoloe_backend_forwards_configured_nms_iou() -> None:
  backend = object.__new__(UltralyticsOpenVocabularyBackend)
  backend._model_path = Path("models/vision/industrial_student_best.pt")
  backend._backend = "yoloe"
  backend._model = _RecordingFixedClassModel()

  detections = backend.detect_all(
    query="roller",
    image_path="frame.jpg",
    depth_path=None,
    options=VisionInferenceOptions(
      box_threshold=0.25,
      nms_iou_threshold=0.55,
      device="0",
    ),
  )

  assert detections[0].found
  assert backend._model.predict_arguments == {
    "source": "frame.jpg",
    "verbose": False,
    "conf": 0.25,
    "iou": 0.55,
    "device": "0",
  }


def test_fixed_class_model_reports_not_found_for_absent_query() -> None:
  backend = object.__new__(UltralyticsOpenVocabularyBackend)
  backend._model_path = Path("models/vision/industrial_student_best.pt")
  backend._backend = "yolo_seg"
  backend._model = _FakeFixedClassModel()

  detections = backend.detect_all(
    query="flange",
    image_path="frame.jpg",
    depth_path=None,
    options=VisionInferenceOptions(),
  )

  assert len(detections) == 1
  assert not detections[0].found
  assert detections[0].label == "flange"


def test_fixed_class_match_supports_competition_chinese_aliases() -> None:
  matches = UltralyticsOpenVocabularyBackend._fixed_class_matches_query

  assert matches("hex_nut", "六角螺母")
  assert matches("short_bolt", "螺栓")
  assert matches("stepped_shaft", "阶梯轴")
  assert matches("roller", "滚轮")


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


class _FakeMultiBoxBackend:
  """Backend that returns several boxes for spatial-selection tests."""

  def __init__(self, boxes: list[tuple[str, float, list[float]]]) -> None:
    self._boxes = boxes

  def _detections(self, query: str) -> list[VisionDetection]:
    detections: list[VisionDetection] = []
    for index, (label, confidence, bbox) in enumerate(self._boxes):
      x1, y1, x2, y2 = bbox
      detections.append(
        VisionDetection(
          found=True,
          label=label,
          confidence=confidence,
          object_id=f"{label}_{index + 1:03d}",
          bbox_2d=list(bbox),
          center_px=[(x1 + x2) / 2.0, (y1 + y2) / 2.0],
          mask_area_px=abs((x2 - x1) * (y2 - y1)),
          source="fake_multi",
        )
      )
    return detections

  def detect(
    self,
    *,
    query: str,
    image_path: str | None,
    depth_path: str | None,
    options: VisionInferenceOptions,
  ) -> VisionDetection:
    del image_path, depth_path, options
    detections = self._detections(query)
    if not detections:
      return VisionDetection(
        found=False, label=query, confidence=0.0, source="fake_multi"
      )
    return max(detections, key=lambda item: item.confidence)

  def detect_all(
    self,
    *,
    query: str,
    image_path: str | None,
    depth_path: str | None,
    options: VisionInferenceOptions,
  ) -> list[VisionDetection]:
    del image_path, depth_path, options
    return self._detections(query)


class _FakeRaisingBackend:
  """Backend that raises a configured exception (for error-mapping tests)."""

  def __init__(self, error: Exception) -> None:
    self._error = error

  def detect(self, *, query, image_path, depth_path, options):
    del query, image_path, depth_path, options
    raise self._error

  def detect_all(self, *, query, image_path, depth_path, options):
    del query, image_path, depth_path, options
    raise self._error


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
  def test_yoloe_can_enable_sam2_refinement_from_configuration(self) -> None:
    tool = VisionOpenVocabularyDetectTool(
      backend="yoloe",
      detector=_FakeBoxOnlyBackend(),
      refine_masks=True,
    )

    self.assertTrue(tool._refine_masks)
    self.assertIsInstance(tool._mask_refiner, UltralyticsSam2Backend)

  def test_yoloe_nms_iou_threshold_is_accepted(self) -> None:
    result = VisionOpenVocabularyDetectTool(
      backend="yoloe",
      detector=_FakeBoxOnlyBackend(),
      nms_iou_threshold=0.60,
    ).run(
      ToolCall(
        tool="vision.open_vocab_detect",
        input={
          "query": "roller",
          "image_path": "frame.jpg",
          "nms_iou_threshold": 0.55,
        },
        trace=TraceContext(),
      )
    )

    self.assertTrue(result.success)

  def test_yoloe_rejects_invalid_nms_iou_threshold(self) -> None:
    result = VisionOpenVocabularyDetectTool(
      backend="yoloe",
      detector=_FakeBoxOnlyBackend(),
    ).run(
      ToolCall(
        tool="vision.open_vocab_detect",
        input={
          "query": "roller",
          "image_path": "frame.jpg",
          "nms_iou_threshold": 1.1,
        },
        trace=TraceContext(),
      )
    )

    self.assertFalse(result.success)
    self.assertIn("nms_iou_threshold must be between 0 and 1", result.error or "")

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
    self.assertEqual(
      result.output["position_3d"],
      {"x": 0.1, "y": 0.2, "z": 1.3, "frame_id": "base_link", "unit": "m"},
    )

  def test_depth_projection_outputs_world_position(self) -> None:
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
        t_world_camera=[
          [1.0, 0.0, 0.0, 1.0],
          [0.0, 1.0, 0.0, 2.0],
          [0.0, 0.0, 1.0, 3.0],
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
    self.assertEqual(result.output["position_world"], [1.0, 2.0, 4.0])
    self.assertEqual(result.output["world_frame"], "world")

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
        red_color_shortcut=True,
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

  def test_red_shortcut_disabled_by_default(self) -> None:
    import tempfile
    import numpy as np

    with tempfile.TemporaryDirectory() as temp_dir:
      image_path = Path(temp_dir) / "rgb.npy"
      image = np.zeros((16, 16, 3), dtype=np.uint8)
      image[8:14, 7:13] = [230, 30, 30]
      np.save(image_path, image)

      result = VisionOpenVocabularyDetectTool(
        detector=_FakeWrongBoxBackend(),
      ).run(
        ToolCall(
          tool="vision.open_vocab_detect",
          input={
            "query": "red roller",
            "image_path": str(image_path),
          },
          trace=TraceContext(),
        )
      )

    self.assertTrue(result.success)
    self.assertNotEqual(result.output["source"], "red_color_filter")
    self.assertEqual(result.output["source"], "fake_yoloe")
    self.assertEqual(result.output["object_id"], "red roller_wrong")

  def test_spatial_left_picks_min_image_x(self) -> None:
    backend = _FakeMultiBoxBackend(
      [
        ("wrench", 0.8, [10.0, 10.0, 30.0, 30.0]),
        ("wrench", 0.7, [100.0, 10.0, 130.0, 40.0]),
        ("wrench", 0.6, [200.0, 10.0, 230.0, 35.0]),
      ]
    )
    result = VisionOpenVocabularyDetectTool(detector=backend).run(
      ToolCall(
        tool="vision.open_vocab_detect",
        input={"query": "wrench", "spatial_constraint": {"relation": "left"}},
        trace=TraceContext(),
      )
    )
    self.assertTrue(result.success)
    self.assertEqual(result.output["bbox_2d"], [10.0, 10.0, 30.0, 30.0])
    self.assertEqual(len(result.output["candidates"]), 2)
    ContractValidator(ROOT / "contracts").validate_tool_output(
      "vision.open_vocab_detect", result.output
    )

  def test_spatial_right_and_largest_pick_extremes(self) -> None:
    backend = _FakeMultiBoxBackend(
      [
        ("wrench", 0.8, [10.0, 10.0, 30.0, 30.0]),
        ("wrench", 0.7, [100.0, 10.0, 130.0, 40.0]),
        ("wrench", 0.6, [200.0, 10.0, 230.0, 35.0]),
      ]
    )
    tool = VisionOpenVocabularyDetectTool(detector=backend)
    right = tool.run(
      ToolCall(
        tool="vision.open_vocab_detect",
        input={"query": "wrench", "spatial_constraint": {"relation": "right"}},
        trace=TraceContext(),
      )
    )
    self.assertEqual(right.output["bbox_2d"], [200.0, 10.0, 230.0, 35.0])
    largest = tool.run(
      ToolCall(
        tool="vision.open_vocab_detect",
        input={"query": "wrench", "spatial_constraint": {"relation": "largest"}},
        trace=TraceContext(),
      )
    )
    self.assertEqual(largest.output["bbox_2d"], [100.0, 10.0, 130.0, 40.0])

  def test_spatial_middle_picks_median_image_x(self) -> None:
    backend = _FakeMultiBoxBackend(
      [
        ("wrench", 0.8, [10.0, 10.0, 30.0, 30.0]),
        ("wrench", 0.7, [100.0, 10.0, 130.0, 40.0]),
        ("wrench", 0.6, [200.0, 10.0, 230.0, 35.0]),
      ]
    )
    result = VisionOpenVocabularyDetectTool(detector=backend).run(
      ToolCall(
        tool="vision.open_vocab_detect",
        input={"query": "wrench", "spatial_constraint": {"relation": "middle"}},
        trace=TraceContext(),
      )
    )
    self.assertTrue(result.success)
    self.assertEqual(result.output["bbox_2d"], [100.0, 10.0, 130.0, 40.0])

  def test_spatial_middle_even_count_picks_second_from_left(self) -> None:
    backend = _FakeMultiBoxBackend(
      [
        ("wrench", 0.8, [10.0, 10.0, 30.0, 30.0]),
        ("wrench", 0.7, [100.0, 10.0, 130.0, 40.0]),
        ("wrench", 0.6, [200.0, 10.0, 230.0, 35.0]),
        ("wrench", 0.5, [300.0, 10.0, 330.0, 35.0]),
      ]
    )
    result = VisionOpenVocabularyDetectTool(detector=backend).run(
      ToolCall(
        tool="vision.open_vocab_detect",
        input={"query": "wrench", "spatial_constraint": {"relation": "middle"}},
        trace=TraceContext(),
      )
    )
    self.assertTrue(result.success)
    self.assertEqual(result.output["bbox_2d"], [100.0, 10.0, 130.0, 40.0])

  def test_spatial_tie_returns_ambiguous(self) -> None:
    backend = _FakeMultiBoxBackend(
      [
        ("wrench", 0.8, [10.0, 10.0, 30.0, 30.0]),
        ("wrench", 0.7, [12.0, 10.0, 32.0, 30.0]),
      ]
    )
    result = VisionOpenVocabularyDetectTool(detector=backend).run(
      ToolCall(
        tool="vision.open_vocab_detect",
        input={"query": "wrench", "spatial_constraint": {"relation": "left"}},
        trace=TraceContext(),
      )
    )
    self.assertFalse(result.success)
    self.assertIn("OBJECT_AMBIGUOUS", result.error or "")
    self.assertEqual(len(result.output["candidates"]), 2)

  def test_spatial_empty_candidates_returns_not_found(self) -> None:
    backend = _FakeMultiBoxBackend([])
    result = VisionOpenVocabularyDetectTool(detector=backend).run(
      ToolCall(
        tool="vision.open_vocab_detect",
        input={"query": "wrench", "spatial_constraint": {"relation": "left"}},
        trace=TraceContext(),
      )
    )
    self.assertFalse(result.success)
    self.assertIn("OBJECT_NOT_FOUND", result.error or "")
    self.assertEqual(result.output["candidates"], [])

  def test_spatial_ordinal_two_picks_second_from_left(self) -> None:
    backend = _FakeMultiBoxBackend(
      [
        ("wrench", 0.8, [10.0, 10.0, 30.0, 30.0]),
        ("wrench", 0.7, [100.0, 10.0, 130.0, 40.0]),
        ("wrench", 0.6, [200.0, 10.0, 230.0, 35.0]),
      ]
    )
    result = VisionOpenVocabularyDetectTool(detector=backend).run(
      ToolCall(
        tool="vision.open_vocab_detect",
        input={
          "query": "wrench",
          "spatial_constraint": {"relation": "left", "ordinal": 2},
        },
        trace=TraceContext(),
      )
    )
    self.assertTrue(result.success)
    self.assertEqual(result.output["bbox_2d"], [100.0, 10.0, 130.0, 40.0])

  def test_spatial_absent_falls_back_to_single_detect(self) -> None:
    result = VisionOpenVocabularyDetectTool(detector=_FakeBoxOnlyBackend()).run(
      ToolCall(
        tool="vision.open_vocab_detect",
        input={"query": "wrench", "image_path": "frame.png"},
        trace=TraceContext(),
      )
    )
    self.assertTrue(result.success)
    self.assertNotIn("candidates", result.output)

  def test_workspace_filters_out_of_reach_candidates(self) -> None:
    # Identity T_base_camera + fx=fy=100, cx=cy=0, table_z=0.12 back-projects
    # pixel (u,v) to base XY (0.12*u/100, 0.12*v/100).
    backend = _FakeMultiBoxBackend(
      [
        ("wrench", 0.7, [190.0, -10.0, 210.0, 10.0]),  # center (200,0) -> base (0.24,0): in reach
        ("wrench", 0.8, [-10.0, -10.0, 10.0, 10.0]),  # center (0,0)   -> base (0,0):   out of reach
      ]
    )
    result = VisionOpenVocabularyDetectTool(
      detector=backend,
      camera_info={"fx": 100.0, "fy": 100.0, "cx": 0.0, "cy": 0.0},
      t_base_camera=[
        [1.0, 0.0, 0.0, 0.0],
        [0.0, 1.0, 0.0, 0.0],
        [0.0, 0.0, 1.0, 0.0],
        [0.0, 0.0, 0.0, 1.0],
      ],
      workspace={"x": [0.15, 0.60], "y": [-0.35, 0.35], "table_z": 0.12},
    ).run(
      ToolCall(
        tool="vision.open_vocab_detect",
        input={"query": "wrench", "spatial_constraint": {"relation": "left"}},
        trace=TraceContext(),
      )
    )
    self.assertTrue(result.success)
    # Without filtering, left would pick the (0,0) box. Workspace filtering
    # drops it (base x=0 < 0.15), leaving the in-reach box at center (200,0).
    self.assertEqual(result.output["bbox_2d"], [190.0, -10.0, 210.0, 10.0])

  def test_source_region_excludes_bin_candidates_before_spatial_selection(self) -> None:
    # Identity T_base_camera + the table-plane estimator maps x pixels to
    # base-frame metres at 0.12 * u / 100. The highest-confidence candidate
    # is outside the source polygon, representing an already placed bin part.
    backend = _FakeMultiBoxBackend(
      [
        ("bolt", 0.99, [390.0, -10.0, 410.0, 10.0]),  # base x=0.48: outside
        ("bolt", 0.80, [140.0, -10.0, 160.0, 10.0]),  # base x=0.18: inside
        ("bolt", 0.70, [240.0, -10.0, 260.0, 10.0]),  # base x=0.30: inside
      ]
    )
    tool = VisionOpenVocabularyDetectTool(
      detector=backend,
      camera_info={"fx": 100.0, "fy": 100.0, "cx": 0.0, "cy": 0.0},
      t_base_camera=[
        [1.0, 0.0, 0.0, 0.0],
        [0.0, 1.0, 0.0, 0.0],
        [0.0, 0.0, 1.0, 0.0],
        [0.0, 0.0, 0.0, 1.0],
      ],
      workspace={"table_z": 0.12},
      allowed_xy_polygon=[[0.15, -0.10], [0.35, -0.10], [0.35, 0.10], [0.15, 0.10]],
      allowed_xy_margin_m=0.01,
    )

    unconstrained = tool.run(
      ToolCall(tool="vision.open_vocab_detect", input={"query": "bolt"}, trace=TraceContext())
    )
    right = tool.run(
      ToolCall(
        tool="vision.open_vocab_detect",
        input={"query": "bolt", "spatial_constraint": {"relation": "right"}},
        trace=TraceContext(),
      )
    )

    self.assertTrue(unconstrained.success)
    self.assertEqual(unconstrained.output["bbox_2d"], [140.0, -10.0, 160.0, 10.0])
    self.assertTrue(right.success)
    self.assertEqual(right.output["bbox_2d"], [240.0, -10.0, 260.0, 10.0])

  def test_source_region_prefers_hardware_cloud_over_plane_projection(self) -> None:
    import tempfile

    backend = _FakeMultiBoxBackend(
      [
        ("bolt", 0.99, [390.0, -10.0, 410.0, 10.0]),
        ("bolt", 0.80, [140.0, -10.0, 160.0, 10.0]),
      ]
    )
    with tempfile.TemporaryDirectory() as temp_dir:
      cloud_path = Path(temp_dir) / "cloud_xyzuv.npy"
      np.save(cloud_path, np.asarray([
        [0.48, 0.0, 0.08, 400.0, 0.0],  # bin candidate: outside
        [0.18, 0.0, 0.08, 150.0, 0.0],  # foam candidate: inside
      ], dtype=np.float32))
      result = VisionOpenVocabularyDetectTool(
        detector=backend,
        allowed_xy_polygon=[[0.15, -0.10], [0.35, -0.10], [0.35, 0.10], [0.15, 0.10]],
        allowed_xy_margin_m=0.01,
      ).run(
        ToolCall(
          tool="vision.open_vocab_detect",
          input={
            "query": "bolt",
            "cloud_path": str(cloud_path),
            "T_base_camera": [
              [1.0, 0.0, 0.0, 0.0],
              [0.0, 1.0, 0.0, 0.0],
              [0.0, 0.0, 1.0, 0.0],
              [0.0, 0.0, 0.0, 1.0],
            ],
          },
          trace=TraceContext(),
        )
      )

    self.assertTrue(result.success)
    self.assertEqual(result.output["bbox_2d"], [140.0, -10.0, 160.0, 10.0])

  def test_spatial_nearest_and_farthest_use_base_xy(self) -> None:
    backend = _FakeMultiBoxBackend(
      [
        ("wrench", 0.7, [190.0, -10.0, 210.0, 10.0]),  # base (0.24,0): dist 0.24
        ("wrench", 0.8, [90.0, -10.0, 110.0, 10.0]),  # base (0.12,0): dist 0.12
      ]
    )
    tool = VisionOpenVocabularyDetectTool(
      detector=backend,
      camera_info={"fx": 100.0, "fy": 100.0, "cx": 0.0, "cy": 0.0},
      t_base_camera=[
        [1.0, 0.0, 0.0, 0.0],
        [0.0, 1.0, 0.0, 0.0],
        [0.0, 0.0, 1.0, 0.0],
        [0.0, 0.0, 0.0, 1.0],
      ],
      workspace={"x": [0.10, 0.60], "y": [-0.35, 0.35], "table_z": 0.12},
    )
    nearest = tool.run(
      ToolCall(
        tool="vision.open_vocab_detect",
        input={"query": "wrench", "spatial_constraint": {"relation": "nearest"}},
        trace=TraceContext(),
      )
    )
    self.assertEqual(nearest.output["bbox_2d"], [90.0, -10.0, 110.0, 10.0])
    farthest = tool.run(
      ToolCall(
        tool="vision.open_vocab_detect",
        input={"query": "wrench", "spatial_constraint": {"relation": "farthest"}},
        trace=TraceContext(),
      )
    )
    self.assertEqual(farthest.output["bbox_2d"], [190.0, -10.0, 210.0, 10.0])

  def test_robot_sim_config_exposes_workspace(self) -> None:
    from sensoragent.config import load_config

    workspace = load_config(ROOT / "configs" / "robot_sim.yaml").scene.workspace
    self.assertEqual(workspace.get("frame"), "base_link")
    self.assertEqual(workspace.get("x"), [-0.59, -0.09])
    self.assertEqual(workspace.get("y"), [-0.375, 0.375])
    self.assertEqual(workspace.get("table_z"), 0.12)

  def test_grounding_prompt_strips_spatial_modifiers(self) -> None:
    from sensoragent.tools.vision.open_vocab import _grounding_prompt

    self.assertEqual(_grounding_prompt("左侧的扳手"), "wrench")
    self.assertEqual(_grounding_prompt("left wrench"), "wrench")
    self.assertEqual(_grounding_prompt("第二个滚柱"), "roller")
    self.assertEqual(_grounding_prompt("扳手"), "wrench")

  def test_scene_aware_policy_reranks_into_tabletop_roi(self) -> None:
    backend = _FakeMultiBoxBackend(
      [
        ("wrench", 0.95, [160.0, 20.0, 190.0, 50.0]),
        ("wrench", 0.62, [20.0, 20.0, 50.0, 50.0]),
      ]
    )
    result = VisionOpenVocabularyDetectTool(detector=backend).run(
      ToolCall(
        tool="vision.open_vocab_detect",
        input={
          "query": "wrench",
          "candidate_policy": "scene_aware",
          "scene_profile": {
            "name": "competition_tabletop_test",
            "workspace_roi": [0.0, 0.0, 120.0, 100.0],
            "image_size": [200.0, 100.0],
            "min_scene_score": 0.05,
          },
        },
        trace=TraceContext(),
      )
    )

    self.assertTrue(result.success)
    self.assertEqual(result.output["bbox_2d"], [20.0, 20.0, 50.0, 50.0])
    self.assertEqual(result.output["candidate_policy"], "scene_aware")
    self.assertEqual(result.output["scene_profile"], "competition_tabletop_test")
    self.assertGreater(result.output["scene_score"], 0.0)
    self.assertTrue(
      result.output["candidates"][0]["rejection_reason"].startswith(
        "outside_workspace_roi"
      )
    )
    ContractValidator(ROOT / "contracts").validate_tool_output(
      "vision.open_vocab_detect", result.output
    )

  def test_scene_aware_policy_rejects_forbidden_region(self) -> None:
    backend = _FakeMultiBoxBackend(
      [
        ("gear", 0.96, [5.0, 5.0, 35.0, 35.0]),
        ("gear", 0.61, [70.0, 50.0, 100.0, 80.0]),
      ]
    )
    result = VisionOpenVocabularyDetectTool(detector=backend).run(
      ToolCall(
        tool="vision.open_vocab_detect",
        input={
          "query": "gear",
          "candidate_policy": "scene_aware",
          "scene_profile": {
            "workspace_roi": [0.0, 0.0, 120.0, 100.0],
            "forbidden_rois": [[0.0, 0.0, 45.0, 45.0]],
          },
        },
        trace=TraceContext(),
      )
    )

    self.assertTrue(result.success)
    self.assertEqual(result.output["bbox_2d"], [70.0, 50.0, 100.0, 80.0])
    self.assertEqual(
      result.output["candidates"][0]["rejection_reason"],
      "forbidden_roi_overlap",
    )

  def test_scene_aware_policy_penalizes_boundary_clipping(self) -> None:
    backend = _FakeMultiBoxBackend(
      [
        ("gear", 0.95, [-20.0, 20.0, 20.0, 60.0]),
        ("gear", 0.65, [50.0, 20.0, 80.0, 50.0]),
      ]
    )
    result = VisionOpenVocabularyDetectTool(detector=backend).run(
      ToolCall(
        tool="vision.open_vocab_detect",
        input={
          "query": "gear",
          "candidate_policy": "scene_aware",
          "scene_profile": {
            "image_size": [100.0, 100.0],
            "min_boundary_coverage": 0.90,
          },
        },
        trace=TraceContext(),
      )
    )

    self.assertTrue(result.success)
    self.assertEqual(result.output["bbox_2d"], [50.0, 20.0, 80.0, 50.0])
    self.assertIn(
      "boundary_clipped",
      result.output["candidates"][0]["rejection_reason"],
    )

  def test_scene_aware_policy_rejects_duplicate_overlapping_candidates(self) -> None:
    backend = _FakeMultiBoxBackend(
      [
        ("gear", 0.90, [20.0, 20.0, 60.0, 60.0]),
        ("gear", 0.88, [22.0, 22.0, 62.0, 62.0]),
      ]
    )
    result = VisionOpenVocabularyDetectTool(detector=backend).run(
      ToolCall(
        tool="vision.open_vocab_detect",
        input={
          "query": "gear",
          "candidate_policy": "scene_aware",
          "scene_profile": {"max_candidate_iou": 0.50},
        },
        trace=TraceContext(),
      )
    )

    self.assertFalse(result.success)
    self.assertIn("OBJECT_NOT_FOUND", result.error or "")
    self.assertEqual(len(result.output["candidates"]), 2)
    self.assertTrue(
      all(
        "duplicate_candidate_overlap" in candidate["rejection_reason"]
        for candidate in result.output["candidates"]
      )
    )

  def test_scene_aware_policy_rejects_ambiguous_score_margin(self) -> None:
    backend = _FakeMultiBoxBackend(
      [
        ("roller", 0.72, [20.0, 20.0, 50.0, 50.0]),
        ("roller", 0.70, [80.0, 20.0, 110.0, 50.0]),
      ]
    )
    result = VisionOpenVocabularyDetectTool(detector=backend).run(
      ToolCall(
        tool="vision.open_vocab_detect",
        input={
          "query": "roller",
          "candidate_policy": "scene_aware",
          "scene_profile": {
            "workspace_roi": [0.0, 0.0, 140.0, 100.0],
            "ambiguity_margin": 0.10,
          },
        },
        trace=TraceContext(),
      )
    )

    self.assertFalse(result.success)
    self.assertIn("OBJECT_AMBIGUOUS", result.error or "")
    self.assertTrue(result.output["ambiguity"]["is_ambiguous"])
    self.assertEqual(len(result.output["candidates"]), 2)

  def test_baseline_policy_keeps_highest_detector_confidence(self) -> None:
    backend = _FakeMultiBoxBackend(
      [
        ("bolt", 0.95, [160.0, 20.0, 190.0, 50.0]),
        ("bolt", 0.62, [20.0, 20.0, 50.0, 50.0]),
      ]
    )
    result = VisionOpenVocabularyDetectTool(detector=backend).run(
      ToolCall(
        tool="vision.open_vocab_detect",
        input={
          "query": "bolt",
          "candidate_policy": "baseline",
          "scene_profile": {
            "workspace_roi": [0.0, 0.0, 120.0, 100.0],
          },
        },
        trace=TraceContext(),
      )
    )

    self.assertTrue(result.success)
    self.assertEqual(result.output["bbox_2d"], [160.0, 20.0, 190.0, 50.0])
    self.assertNotIn("scene_score", result.output)
    self.assertNotIn("candidates", result.output)

  def test_oserror_from_detector_maps_to_backend_error(self) -> None:
    result = VisionOpenVocabularyDetectTool(
      detector=_FakeRaisingBackend(OSError("connection timed out"))
    ).run(
      ToolCall(
        tool="vision.open_vocab_detect",
        input={"query": "wrench", "image_path": "frame.png"},
        trace=TraceContext(),
      )
    )
    self.assertFalse(result.success)
    self.assertIn("VISION_BACKEND_ERROR", result.error or "")

  def test_permission_error_maps_to_input_error(self) -> None:
    result = VisionOpenVocabularyDetectTool(
      detector=_FakeRaisingBackend(PermissionError("permission denied"))
    ).run(
      ToolCall(
        tool="vision.open_vocab_detect",
        input={"query": "wrench", "image_path": "frame.png"},
        trace=TraceContext(),
      )
    )
    self.assertFalse(result.success)
    self.assertIn("VISION_INPUT_ERROR", result.error or "")
    self.assertNotIn("VISION_BACKEND_ERROR", result.error or "")

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
