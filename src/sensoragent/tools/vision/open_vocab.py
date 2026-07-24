"""Open-vocabulary vision detection tool skeleton.

The implementation intentionally keeps model loading isolated behind a small
adapter so model weights can be dropped into ``models/vision`` later without
changing the SensorAgent Tool contract.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Protocol

import numpy as np

from sensoragent.schemas import ToolCall, ToolResult, ToolSpec


@dataclass(frozen=True)
class VisionDetection:
  """A single 2D/3D object detection result."""

  found: bool
  label: str
  confidence: float
  object_id: str | None = None
  bbox_2d: list[float] | None = None
  mask_path: str | None = None
  position_camera: list[float] | None = None
  position_base: list[float] | None = None
  pose_3d: list[float] | None = None
  source: str = "open_vocab"

  def to_output(self) -> dict:
    output = {
      "found": self.found,
      "label": self.label,
      "confidence": self.confidence,
      "source": self.source,
    }
    optional = {
      "object_id": self.object_id,
      "bbox_2d": self.bbox_2d,
      "mask_path": self.mask_path,
      "position_camera": self.position_camera,
      "position_base": self.position_base,
      "pose_3d": self.pose_3d,
    }
    output.update({key: value for key, value in optional.items() if value is not None})
    return output


class OpenVocabularyVisionBackend(Protocol):
  """Backend interface implemented by YOLOE/YOLO-seg adapters."""

  def detect(self, *, query: str, image_path: str | None, depth_path: str | None) -> VisionDetection:
    """Detect the queried object and optionally estimate its 3D pose."""


class PlaceholderOpenVocabularyBackend:
  """Placeholder backend used until model weights and an adapter are installed."""

  def __init__(self, *, model_path: Path, backend: str) -> None:
    self._model_path = model_path
    self._backend = backend

  def detect(self, *, query: str, image_path: str | None, depth_path: str | None) -> VisionDetection:
    del query, image_path, depth_path
    raise FileNotFoundError(
      f"Vision model weights are not available yet: {self._model_path} "
      f"(backend={self._backend}). Put the model file in models/vision or update "
      "integrations.vision.model_path."
    )


class UnavailableOpenVocabularyBackend:
  """Backend used when optional vision dependencies are missing."""

  def __init__(self, *, error: ImportError) -> None:
    self._error = error

  def detect(self, *, query: str, image_path: str | None, depth_path: str | None) -> VisionDetection:
    del query, image_path, depth_path
    raise self._error


class UltralyticsOpenVocabularyBackend:
  """YOLOE/Ultralytics backend with optional RGB-D 3D projection."""

  def __init__(self, *, model_path: Path, backend: str = "yoloe") -> None:
    self._model_path = model_path
    self._backend = backend
    try:
      from ultralytics import YOLO
    except ImportError as exc:
      raise ImportError(
        "ultralytics is required for vision.open_vocab_detect. "
        "Install optional vision dependencies first."
      ) from exc
    self._model = YOLO(str(model_path))

  def _load_image(self, image_path: str | None):
    if image_path is None:
      raise ValueError("image_path is required for open-vocabulary detection")
    path = Path(image_path)
    if path.suffix == ".npy":
      return np.load(path)
    return str(path)

  def _set_classes_if_supported(self, query: str) -> None:
    classes = [query]
    try:
      text_embeddings = self._model.get_text_pe(classes)
      self._model.set_classes(classes, text_embeddings)
    except AttributeError:
      return

  @staticmethod
  def _best_box(result) -> tuple[list[float], float, str] | None:
    boxes = getattr(result, "boxes", None)
    if boxes is None or len(boxes) == 0:
      return None
    xyxy = boxes.xyxy.cpu().numpy()
    conf = boxes.conf.cpu().numpy()
    cls = boxes.cls.cpu().numpy().astype(int) if boxes.cls is not None else np.zeros(len(conf), dtype=int)
    index = int(np.argmax(conf))
    names = getattr(result, "names", {}) or {}
    label = str(names.get(int(cls[index]), int(cls[index])))
    return [float(value) for value in xyxy[index]], float(conf[index]), label

  @staticmethod
  def _load_camera_info(path: str | None, inline: dict | None) -> dict | None:
    if inline is not None:
      return inline
    if path is None:
      return None
    return json.loads(Path(path).read_text(encoding="utf-8"))

  @staticmethod
  def _load_depth(path: str | None) -> np.ndarray | None:
    if path is None:
      return None
    depth_path = Path(path)
    if depth_path.suffix == ".npy":
      return np.load(depth_path)
    raise ValueError("Only .npy depth files are supported by the initial backend")

  @staticmethod
  def _median_depth(depth: np.ndarray, bbox: list[float], window: int) -> tuple[float, float, float] | None:
    x1, y1, x2, y2 = bbox
    u = int(round((x1 + x2) / 2.0))
    v = int(round((y1 + y2) / 2.0))
    half = max(1, int(window) // 2)
    y_start = max(0, v - half)
    y_end = min(depth.shape[0], v + half + 1)
    x_start = max(0, u - half)
    x_end = min(depth.shape[1], u + half + 1)
    patch = depth[y_start:y_end, x_start:x_end].astype(np.float64)
    valid = patch[np.isfinite(patch) & (patch > 0.0)]
    if len(valid) == 0:
      return None
    return float(u), float(v), float(np.median(valid))

  @staticmethod
  def _camera_intrinsics(camera_info: dict) -> tuple[float, float, float, float]:
    k = camera_info.get("k") or camera_info.get("K")
    if not isinstance(k, list) or len(k) < 6:
      raise ValueError("camera_info must contain k/K with at least 6 values")
    return float(k[0]), float(k[4]), float(k[2]), float(k[5])

  @staticmethod
  def _project_to_camera(u: float, v: float, depth: float, camera_info: dict) -> list[float]:
    fx, fy, cx, cy = UltralyticsOpenVocabularyBackend._camera_intrinsics(camera_info)
    x = (u - cx) * depth / fx
    y = (v - cy) * depth / fy
    return [float(x), float(y), float(depth)]

  @staticmethod
  def _transform_to_base(point_camera: list[float], transform: list[list[float]] | None) -> list[float] | None:
    if transform is None:
      return None
    matrix = np.asarray(transform, dtype=np.float64)
    if matrix.shape != (4, 4):
      raise ValueError("T_base_camera must be a 4x4 matrix")
    point = np.asarray([point_camera[0], point_camera[1], point_camera[2], 1.0], dtype=np.float64)
    transformed = matrix @ point
    return [float(value) for value in transformed[:3]]

  def detect(self, *, query: str, image_path: str | None, depth_path: str | None) -> VisionDetection:
    self._set_classes_if_supported(query)
    image = self._load_image(image_path)
    results = self._model.predict(image, verbose=False)
    if not results:
      return VisionDetection(found=False, label=query, confidence=0.0, source=self._backend)
    best = self._best_box(results[0])
    if best is None:
      return VisionDetection(found=False, label=query, confidence=0.0, source=self._backend)
    bbox, confidence, label = best
    return VisionDetection(
      found=True,
      label=label,
      confidence=confidence,
      object_id=f"{label}_001",
      bbox_2d=bbox,
      source=self._backend,
    )


class VisionOpenVocabularyDetectTool:
  """Open-vocabulary object detector contract for future YOLOE/YOLO-seg integration."""

  spec = ToolSpec(
    name="vision.open_vocab_detect",
    description="Detect an object from a text query using an open-vocabulary vision backend.",
    tags=("vision", "open-vocabulary", "detector"),
  )

  def __init__(
    self,
    *,
    model_path: str = "models/vision/yoloe.pt",
    backend: str = "yoloe",
    camera_info_path: str | None = None,
    camera_info: dict | None = None,
    t_base_camera: list[list[float]] | None = None,
    depth_window: int = 7,
    detector: OpenVocabularyVisionBackend | None = None,
  ) -> None:
    self._model_path = Path(model_path)
    self._backend = backend
    self._camera_info_path = camera_info_path
    self._camera_info = camera_info
    self._t_base_camera = t_base_camera
    self._depth_window = depth_window
    if detector is not None:
      self._detector = detector
    elif self._model_path.exists():
      try:
        self._detector = UltralyticsOpenVocabularyBackend(
          model_path=self._model_path,
          backend=self._backend,
        )
      except ImportError as exc:
        self._detector = UnavailableOpenVocabularyBackend(error=exc)
    else:
      self._detector = PlaceholderOpenVocabularyBackend(
        model_path=self._model_path,
        backend=self._backend,
      )

  def run(self, call: ToolCall) -> ToolResult:
    query = call.input.get("query")
    if not isinstance(query, str) or not query:
      return ToolResult(
        tool=self.spec.name,
        success=False,
        error="query must be a non-empty string",
      )
    image_path = call.input.get("image_path")
    depth_path = call.input.get("depth_path")
    camera_info_path = call.input.get("camera_info_path", self._camera_info_path)
    camera_info_inline = call.input.get("camera_info", self._camera_info)
    t_base_camera = call.input.get("T_base_camera", self._t_base_camera)
    depth_window = int(call.input.get("depth_window", self._depth_window))
    if image_path is not None and not isinstance(image_path, str):
      return ToolResult(
        tool=self.spec.name,
        success=False,
        error="image_path must be a string when provided",
      )
    if depth_path is not None and not isinstance(depth_path, str):
      return ToolResult(
        tool=self.spec.name,
        success=False,
        error="depth_path must be a string when provided",
      )
    try:
      detection = self._detector.detect(
        query=query,
        image_path=image_path,
        depth_path=depth_path,
      )
    except FileNotFoundError as exc:
      return ToolResult(
        tool=self.spec.name,
        success=False,
        output={
          "found": False,
          "label": query,
          "confidence": 0.0,
          "source": self._backend,
          "model_path": self._model_path.as_posix(),
        },
        error=f"VISION_MODEL_NOT_READY: {exc}",
      )
    except ImportError as exc:
      return ToolResult(
        tool=self.spec.name,
        success=False,
        output={
          "found": False,
          "label": query,
          "confidence": 0.0,
          "source": self._backend,
          "model_path": self._model_path.as_posix(),
        },
        error=f"VISION_BACKEND_UNAVAILABLE: {exc}",
      )
    except ValueError as exc:
      return ToolResult(
        tool=self.spec.name,
        success=False,
        output={"found": False, "label": query, "confidence": 0.0, "source": self._backend},
        error=f"VISION_INPUT_ERROR: {exc}",
      )
    if detection.found and detection.bbox_2d and detection.pose_3d is None:
      try:
        depth = UltralyticsOpenVocabularyBackend._load_depth(depth_path)
        camera_info = UltralyticsOpenVocabularyBackend._load_camera_info(
          camera_info_path,
          camera_info_inline,
        )
        if depth is not None and camera_info is not None:
          sample = UltralyticsOpenVocabularyBackend._median_depth(
            depth,
            detection.bbox_2d,
            depth_window,
          )
          if sample is not None:
            u, v, z = sample
            position_camera = UltralyticsOpenVocabularyBackend._project_to_camera(
              u,
              v,
              z,
              camera_info,
            )
            position_base = UltralyticsOpenVocabularyBackend._transform_to_base(
              position_camera,
              t_base_camera,
            )
            pose_3d = None
            if position_base is not None:
              pose_3d = [position_base[0], position_base[1], position_base[2], 0.0, 0.0, 0.0]
            detection = VisionDetection(
              found=detection.found,
              label=detection.label,
              confidence=detection.confidence,
              object_id=detection.object_id,
              bbox_2d=detection.bbox_2d,
              mask_path=detection.mask_path,
              position_camera=position_camera,
              position_base=position_base,
              pose_3d=pose_3d,
              source=detection.source,
            )
      except ValueError as exc:
        return ToolResult(
          tool=self.spec.name,
          success=False,
          output=detection.to_output(),
          error=f"VISION_DEPTH_ERROR: {exc}",
        )
    return ToolResult(
      tool=self.spec.name,
      success=detection.found,
      output=detection.to_output(),
      error=None if detection.found else "OBJECT_NOT_FOUND",
    )
