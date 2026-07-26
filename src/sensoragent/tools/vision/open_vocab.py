"""Open-vocabulary detection, optional mask refinement, and RGB-D geometry."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
import json
import os
from pathlib import Path
import re
import time
from typing import Protocol, Sequence

import numpy as np

from sensoragent.schemas import ToolCall, ToolResult, ToolSpec


Polygon = list[list[float]]


@dataclass(frozen=True)
class VisionInferenceOptions:
  """Per-call controls shared by open-vocabulary detector backends."""

  box_threshold: float = 0.35
  text_threshold: float = 0.25
  device: str | None = None


@dataclass(frozen=True)
class VisionDetection:
  """A single 2D/3D object detection result."""

  found: bool
  label: str
  confidence: float
  object_id: str | None = None
  bbox_2d: list[float] | None = None
  mask_path: str | None = None
  mask_polygons: list[Polygon] | None = None
  mask_area_px: float | None = None
  center_px: list[float] | None = None
  depth_m: float | None = None
  position_camera: list[float] | None = None
  position_base: list[float] | None = None
  pose_3d: list[float] | None = None
  position_3d: dict[str, object] | None = None
  camera_frame: str | None = None
  base_frame: str | None = None
  model: str | None = None
  timing_ms: dict[str, float] = field(default_factory=dict)
  warnings: list[str] = field(default_factory=list)
  source: str = "open_vocab"

  def to_output(self) -> dict[str, object]:
    """Convert the detection to the stable Tool output shape."""

    output: dict[str, object] = {
      "found": self.found,
      "label": self.label,
      "confidence": self.confidence,
      "source": self.source,
    }
    optional = {
      "object_id": self.object_id,
      "bbox_2d": self.bbox_2d,
      "mask_path": self.mask_path,
      "mask_polygons": self.mask_polygons,
      "mask_area_px": self.mask_area_px,
      "center_px": self.center_px,
      "depth_m": self.depth_m,
      "position_camera": self.position_camera,
      "position_base": self.position_base,
      "pose_3d": self.pose_3d,
      "position_3d": self.position_3d,
      "camera_frame": self.camera_frame,
      "base_frame": self.base_frame,
      "model": self.model,
      "timing_ms": self.timing_ms or None,
      "warnings": self.warnings or None,
    }
    output.update({key: value for key, value in optional.items() if value is not None})
    return output


class OpenVocabularyVisionBackend(Protocol):
  """Backend interface implemented by YOLOE and Grounding DINO adapters."""

  def detect(
    self,
    *,
    query: str,
    image_path: str | None,
    depth_path: str | None,
    options: VisionInferenceOptions,
  ) -> VisionDetection:
    """Detect the highest-confidence object matching the text query."""


class MaskRefinementBackend(Protocol):
  """Backend interface for box-prompted segmentation models."""

  def segment(
    self,
    *,
    image_path: str,
    bbox_2d: Sequence[float],
    device: str | None,
  ) -> list[Polygon]:
    """Refine one bounding box into zero or more mask polygons."""


class VisionModelNotReadyError(FileNotFoundError):
  """Raised when a configured local detector model has not been installed."""


class PlaceholderOpenVocabularyBackend:
  """Backend used until configured local YOLOE weights are installed."""

  def __init__(self, *, model_path: Path, backend: str) -> None:
    self._model_path = model_path
    self._backend = backend

  def detect(
    self,
    *,
    query: str,
    image_path: str | None,
    depth_path: str | None,
    options: VisionInferenceOptions,
  ) -> VisionDetection:
    """Raise a structured model-not-ready error."""

    del query, image_path, depth_path, options
    raise VisionModelNotReadyError(
      f"Vision model weights are not available yet: {self._model_path} "
      f"(backend={self._backend}). Put the model file in models/vision or update "
      "integrations.vision.model_path."
    )


class UnavailableOpenVocabularyBackend:
  """Backend used when an optional detector dependency is missing."""

  def __init__(self, *, error: ImportError) -> None:
    self._error = error

  def detect(
    self,
    *,
    query: str,
    image_path: str | None,
    depth_path: str | None,
    options: VisionInferenceOptions,
  ) -> VisionDetection:
    """Raise the dependency error captured during backend construction."""

    del query, image_path, depth_path, options
    raise self._error


def _mask_area_and_centroid(
  polygons: Sequence[Polygon],
  bbox_2d: Sequence[float],
) -> tuple[float | None, list[float]]:
  """Compute polygon area and centroid, with the box center as a fallback."""

  x1, y1, x2, y2 = (float(value) for value in bbox_2d)
  fallback = [(x1 + x2) / 2.0, (y1 + y2) / 2.0]
  total_area = 0.0
  weighted_x = 0.0
  weighted_y = 0.0
  for polygon in polygons:
    if len(polygon) < 3:
      continue
    signed_twice_area = 0.0
    centroid_x_numerator = 0.0
    centroid_y_numerator = 0.0
    for index, point in enumerate(polygon):
      next_point = polygon[(index + 1) % len(polygon)]
      cross = point[0] * next_point[1] - next_point[0] * point[1]
      signed_twice_area += cross
      centroid_x_numerator += (point[0] + next_point[0]) * cross
      centroid_y_numerator += (point[1] + next_point[1]) * cross
    if abs(signed_twice_area) < 1e-9:
      continue
    area = abs(signed_twice_area) / 2.0
    centroid_x = centroid_x_numerator / (3.0 * signed_twice_area)
    centroid_y = centroid_y_numerator / (3.0 * signed_twice_area)
    total_area += area
    weighted_x += centroid_x * area
    weighted_y += centroid_y * area
  if total_area <= 0.0:
    return None, fallback
  return total_area, [weighted_x / total_area, weighted_y / total_area]


def _resolve_torch_device(device: str | None) -> str | None:
  if device is None or not str(device).strip():
    return None
  value = str(device).strip()
  if value.isdigit():
    return f"cuda:{value}"
  return value


def _grounding_prompt(query: str) -> str:
  aliases = {
    "螺丝刀": "screwdriver",
    "螺丝": "screw",
    "扳手": "wrench",
    "螺母": "nut",
    "滚柱": "roller",
    "滚筒": "roller",
    "齿轮": "gear",
    "法兰": "flange",
    "红色": "red ",
  }
  prompt = query.strip()
  for source in sorted(aliases, key=len, reverse=True):
    prompt = prompt.replace(source, aliases[source])
  return " ".join(prompt.split())


class UltralyticsOpenVocabularyBackend:
  """YOLOE/Ultralytics backend that preserves the existing detector path."""

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
    if path.suffix.casefold() == ".npy":
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
  def _best_detection(result, source: str, model: str) -> VisionDetection | None:
    boxes = getattr(result, "boxes", None)
    if boxes is None or len(boxes) == 0:
      return None
    xyxy = boxes.xyxy.cpu().numpy()
    confidence = boxes.conf.cpu().numpy()
    classes = (
      boxes.cls.cpu().numpy().astype(int)
      if boxes.cls is not None
      else np.zeros(len(confidence), dtype=int)
    )
    index = int(np.argmax(confidence))
    names = getattr(result, "names", {}) or {}
    label = str(names.get(int(classes[index]), int(classes[index])))
    polygons = None
    masks = getattr(result, "masks", None)
    raw_polygons = getattr(masks, "xy", None) if masks is not None else None
    if raw_polygons is not None and index < len(raw_polygons):
      polygon = [[float(x), float(y)] for x, y in raw_polygons[index].tolist()]
      if polygon:
        polygons = [polygon]
    bbox = [float(value) for value in xyxy[index]]
    area, center = _mask_area_and_centroid(polygons or [], bbox)
    return VisionDetection(
      found=True,
      label=label,
      confidence=float(confidence[index]),
      object_id=f"{label}_001",
      bbox_2d=bbox,
      mask_polygons=polygons,
      mask_area_px=area,
      center_px=center,
      model=model,
      source=source,
    )

  def detect(
    self,
    *,
    query: str,
    image_path: str | None,
    depth_path: str | None,
    options: VisionInferenceOptions,
  ) -> VisionDetection:
    """Run YOLOE and return the highest-confidence matching detection."""

    del depth_path
    self._set_classes_if_supported(query)
    image = self._load_image(image_path)
    arguments: dict[str, object] = {
      "source": image,
      "verbose": False,
      "conf": options.box_threshold,
    }
    if options.device is not None:
      arguments["device"] = options.device
    started = time.perf_counter()
    results = self._model.predict(**arguments)
    elapsed_ms = round((time.perf_counter() - started) * 1000.0, 3)
    if not results:
      return VisionDetection(
        found=False,
        label=query,
        confidence=0.0,
        model=self._model_path.as_posix(),
        timing_ms={"detector": elapsed_ms},
        source=self._backend,
      )
    detection = self._best_detection(
      results[0],
      self._backend,
      self._model_path.as_posix(),
    )
    if detection is None:
      return VisionDetection(
        found=False,
        label=query,
        confidence=0.0,
        model=self._model_path.as_posix(),
        timing_ms={"detector": elapsed_ms},
        source=self._backend,
      )
    return replace(detection, timing_ms={"detector": elapsed_ms})


class GroundingDinoBackend:
  """Lazy Hugging Face Grounding DINO detector backend."""

  def __init__(self, model_id: str | None = None) -> None:
    self.model_id = model_id or os.getenv(
      "SENSORAGENT_GROUNDING_DINO_MODEL",
      "IDEA-Research/grounding-dino-tiny",
    )
    self._processor = None
    self._model = None
    self._torch = None

  def _load_model(self):
    if self._model is not None:
      return self._processor, self._model, self._torch
    try:
      import torch
      from transformers import AutoModelForZeroShotObjectDetection, AutoProcessor
    except ImportError as exc:
      raise ImportError(
        "transformers, torch, and Pillow are required for Grounding DINO. "
        "Install requirements-vision.txt first."
      ) from exc
    self._processor = AutoProcessor.from_pretrained(self.model_id)
    self._model = AutoModelForZeroShotObjectDetection.from_pretrained(self.model_id)
    self._torch = torch
    return self._processor, self._model, self._torch

  @staticmethod
  def _as_list(value) -> list:
    if isinstance(value, str):
      return [value]
    if hasattr(value, "detach"):
      value = value.detach()
    if hasattr(value, "cpu"):
      value = value.cpu()
    if hasattr(value, "tolist"):
      value = value.tolist()
    return list(value)

  def detect(
    self,
    *,
    query: str,
    image_path: str | None,
    depth_path: str | None,
    options: VisionInferenceOptions,
  ) -> VisionDetection:
    """Run text-grounded detection and return the best matching box."""

    del depth_path
    if image_path is None:
      raise ValueError("image_path is required for Grounding DINO detection")
    path = Path(image_path)
    if not path.is_file():
      raise ValueError(f"image_path does not exist: {path}")
    if path.suffix.casefold() == ".npy":
      raise ValueError("Grounding DINO requires a standard RGB image, not .npy")
    prompt = _grounding_prompt(query)
    if not prompt:
      raise ValueError("query must be a non-empty string")
    try:
      from PIL import Image
    except ImportError as exc:
      raise ImportError(
        "Pillow is required for Grounding DINO. Install requirements-vision.txt."
      ) from exc

    processor, model, torch = self._load_model()
    selected_device = _resolve_torch_device(options.device)
    if selected_device is None:
      selected_device = "cuda:0" if torch.cuda.is_available() else "cpu"
    model = model.to(selected_device)
    image = Image.open(path).convert("RGB")
    inputs = processor(images=image, text=[prompt], return_tensors="pt")
    inputs = {
      key: value.to(selected_device) if hasattr(value, "to") else value
      for key, value in inputs.items()
    }
    started = time.perf_counter()
    with torch.no_grad():
      outputs = model(**inputs)
    try:
      results = processor.post_process_grounded_object_detection(
        outputs,
        inputs["input_ids"],
        threshold=options.box_threshold,
        text_threshold=options.text_threshold,
        target_sizes=[image.size[::-1]],
      )
    except TypeError:
      results = processor.post_process_grounded_object_detection(
        outputs,
        inputs["input_ids"],
        box_threshold=options.box_threshold,
        text_threshold=options.text_threshold,
        target_sizes=[image.size[::-1]],
      )
    elapsed_ms = round((time.perf_counter() - started) * 1000.0, 3)
    result = results[0]
    boxes = self._as_list(result.get("boxes", []))
    scores = self._as_list(result.get("scores", []))
    raw_labels = result.get("text_labels")
    labels = self._as_list(raw_labels) if raw_labels is not None else [prompt] * len(boxes)
    count = min(len(boxes), len(scores), len(labels))
    if count == 0:
      return VisionDetection(
        found=False,
        label=query,
        confidence=0.0,
        model=self.model_id,
        timing_ms={"grounding_dino": elapsed_ms},
        source="grounding_dino",
      )
    index = int(np.argmax(np.asarray(scores[:count], dtype=np.float64)))
    bbox = [float(value) for value in boxes[index]]
    label = labels[index] if isinstance(labels[index], str) else prompt
    _, center = _mask_area_and_centroid([], bbox)
    return VisionDetection(
      found=True,
      label=str(label),
      confidence=float(scores[index]),
      object_id=f"{prompt.replace(' ', '_')}_001",
      bbox_2d=bbox,
      center_px=center,
      model=self.model_id,
      timing_ms={"grounding_dino": elapsed_ms},
      source="grounding_dino",
    )


class UltralyticsSam2Backend:
  """Lazy SAM 2 adapter using the Ultralytics box-prompt API."""

  def __init__(self, weights_path: str | Path | None = None) -> None:
    configured = os.getenv("SENSORAGENT_SAM2_WEIGHTS")
    self.weights_path = str(weights_path or configured or "sam2_t.pt")
    self._model = None

  def _load_model(self):
    if self._model is not None:
      return self._model
    try:
      from ultralytics import SAM
    except ImportError as exc:
      raise ImportError(
        "ultralytics is required for SAM 2 mask refinement. "
        "Install requirements-vision.txt first."
      ) from exc
    self._model = SAM(self.weights_path)
    return self._model

  def segment(
    self,
    *,
    image_path: str,
    bbox_2d: Sequence[float],
    device: str | None,
  ) -> list[Polygon]:
    """Refine one detector box into SAM 2 polygons."""

    model = self._load_model()
    arguments: dict[str, object] = {
      "source": image_path,
      "bboxes": [[float(value) for value in bbox_2d]],
      "verbose": False,
    }
    if device is not None:
      arguments["device"] = device
    results = model.predict(**arguments)
    if not results:
      return []
    masks = getattr(results[0], "masks", None)
    raw_polygons = getattr(masks, "xy", None) if masks is not None else None
    if raw_polygons is None:
      return []
    return [
      [[float(x), float(y)] for x, y in polygon.tolist()]
      for polygon in raw_polygons
      if len(polygon) >= 3
    ]


def _load_camera_info(path: str | None, inline: dict | None) -> dict | None:
  if inline is not None:
    return inline
  if path is None:
    return None
  return json.loads(Path(path).read_text(encoding="utf-8"))


def _load_depth(path: str | None) -> np.ndarray | None:
  if path is None:
    return None
  depth_path = Path(path)
  if depth_path.suffix.casefold() != ".npy":
    raise ValueError("Only .npy depth files are supported")
  depth = np.load(depth_path)
  if depth.ndim != 2:
    raise ValueError("depth map must be a single-channel 2D array")
  return depth


def _polygon_mask(shape: tuple[int, int], polygons: Sequence[Polygon]) -> np.ndarray:
  """Rasterize polygons with a dependency-free vectorized ray-casting test."""

  height, width = shape
  mask = np.zeros((height, width), dtype=bool)
  for polygon in polygons:
    if len(polygon) < 3:
      continue
    points = np.asarray(polygon, dtype=np.float64)
    left = max(0, int(np.floor(np.min(points[:, 0]))))
    right = min(width - 1, int(np.ceil(np.max(points[:, 0]))))
    top = max(0, int(np.floor(np.min(points[:, 1]))))
    bottom = min(height - 1, int(np.ceil(np.max(points[:, 1]))))
    if right < left or bottom < top:
      continue
    x_grid, y_grid = np.meshgrid(
      np.arange(left, right + 1, dtype=np.float64) + 0.5,
      np.arange(top, bottom + 1, dtype=np.float64) + 0.5,
    )
    inside = np.zeros(x_grid.shape, dtype=bool)
    previous = points[-1]
    for current in points:
      crosses = (current[1] > y_grid) != (previous[1] > y_grid)
      denominator = previous[1] - current[1]
      if abs(denominator) > 1e-12:
        intersection_x = (
          (previous[0] - current[0])
          * (y_grid - current[1])
          / denominator
          + current[0]
        )
        inside ^= crosses & (x_grid < intersection_x)
      previous = current
    mask[top : bottom + 1, left : right + 1] |= inside
  return mask


def _median_depth(
  depth: np.ndarray,
  bbox_2d: Sequence[float],
  polygons: Sequence[Polygon],
  center_px: Sequence[float],
  window: int,
  depth_scale: float,
) -> tuple[float, float, float] | None:
  if depth_scale <= 0.0:
    raise ValueError("depth_scale must be greater than zero")
  if polygons:
    values = depth[_polygon_mask(depth.shape, polygons)].astype(np.float64)
    u, v = float(center_px[0]), float(center_px[1])
  else:
    x1, y1, x2, y2 = (float(value) for value in bbox_2d)
    u = (x1 + x2) / 2.0
    v = (y1 + y2) / 2.0
    half = max(1, int(window) // 2)
    center_x = int(round(u))
    center_y = int(round(v))
    y_start = max(0, center_y - half)
    y_end = min(depth.shape[0], center_y + half + 1)
    x_start = max(0, center_x - half)
    x_end = min(depth.shape[1], center_x + half + 1)
    values = depth[y_start:y_end, x_start:x_end].astype(np.float64).reshape(-1)
  values = values[np.isfinite(values) & (values > 0.0)] * depth_scale
  if values.size == 0:
    return None
  return u, v, float(np.median(values))


def _camera_intrinsics(camera_info: dict) -> tuple[float, float, float, float]:
  explicit = tuple(camera_info.get(name) for name in ("fx", "fy", "cx", "cy"))
  if all(isinstance(value, (int, float)) for value in explicit):
    fx, fy, cx, cy = (float(value) for value in explicit)
  else:
    matrix = camera_info.get("k") or camera_info.get("K")
    if not isinstance(matrix, list) or len(matrix) < 6:
      raise ValueError("camera_info must contain fx/fy/cx/cy or k/K")
    fx, fy, cx, cy = (
      float(matrix[0]),
      float(matrix[4]),
      float(matrix[2]),
      float(matrix[5]),
    )
  if fx == 0.0 or fy == 0.0:
    raise ValueError("camera_info focal lengths must be non-zero")
  return fx, fy, cx, cy


def _project_to_camera(
  u: float,
  v: float,
  depth_m: float,
  camera_info: dict,
) -> list[float]:
  fx, fy, cx, cy = _camera_intrinsics(camera_info)
  return [
    float((u - cx) * depth_m / fx),
    float((v - cy) * depth_m / fy),
    float(depth_m),
  ]


def _transform_to_base(
  point_camera: Sequence[float],
  transform: Sequence[Sequence[float]] | None,
) -> list[float] | None:
  if transform is None:
    return None
  matrix = np.asarray(transform, dtype=np.float64)
  if matrix.shape != (4, 4):
    raise ValueError("T_base_camera must be a 4x4 matrix")
  point = np.asarray([*point_camera, 1.0], dtype=np.float64)
  transformed = matrix @ point
  if abs(transformed[3]) < 1e-12:
    raise ValueError("T_base_camera produced an invalid homogeneous coordinate")
  return [float(value / transformed[3]) for value in transformed[:3]]


class VisionOpenVocabularyDetectTool:
  """Open-vocabulary detection with optional SAM 2 and RGB-D localization."""

  spec = ToolSpec(
    name="vision.open_vocab_detect",
    description=(
      "Detect a text-query object with YOLOE or Grounding DINO, optionally "
      "refine a mask with SAM 2, and estimate its 3D position."
    ),
    tags=("vision", "open-vocabulary", "detector", "segmentation", "rgbd"),
    timeout_seconds=120.0,
  )

  def __init__(
    self,
    *,
    model_path: str = "models/vision/yoloe.pt",
    backend: str = "yoloe",
    grounding_dino_model: str | None = None,
    sam2_model_path: str | None = None,
    camera_info_path: str | None = None,
    camera_info: dict | None = None,
    t_base_camera: list[list[float]] | None = None,
    position_base_offset: list[float] | None = None,
    depth_window: int = 7,
    depth_scale: float = 1.0,
    box_threshold: float = 0.35,
    text_threshold: float = 0.25,
    device: str | None = None,
    refine_masks: bool | None = None,
    require_masks: bool = False,
    red_color_shortcut: bool = False,
    camera_frame: str = "camera_color_optical_frame",
    base_frame: str = "base_link",
    detector: OpenVocabularyVisionBackend | None = None,
    mask_refiner: MaskRefinementBackend | None = None,
  ) -> None:
    self._model_path = Path(model_path)
    self._backend = backend
    self._camera_info_path = camera_info_path
    self._camera_info = camera_info
    self._t_base_camera = t_base_camera
    self._position_base_offset = position_base_offset
    self._depth_window = depth_window
    self._depth_scale = depth_scale
    self._box_threshold = box_threshold
    self._text_threshold = text_threshold
    self._device = device
    self._require_masks = require_masks
    self._red_color_shortcut = red_color_shortcut
    self._camera_frame = camera_frame
    self._base_frame = base_frame
    normalized_backend = backend.casefold().replace("-", "_")
    is_grounding_dino = normalized_backend in {
      "grounding_dino",
      "groundingdino",
      "dino",
    }
    self._refine_masks = is_grounding_dino if refine_masks is None else refine_masks
    if detector is not None:
      self._detector = detector
      self._model_reference = grounding_dino_model or self._model_path.as_posix()
    elif is_grounding_dino:
      self._detector = GroundingDinoBackend(grounding_dino_model)
      self._model_reference = self._detector.model_id
    elif self._model_path.exists():
      self._model_reference = self._model_path.as_posix()
      try:
        self._detector = UltralyticsOpenVocabularyBackend(
          model_path=self._model_path,
          backend=self._backend,
        )
      except ImportError as exc:
        self._detector = UnavailableOpenVocabularyBackend(error=exc)
    else:
      self._model_reference = self._model_path.as_posix()
      self._detector = PlaceholderOpenVocabularyBackend(
        model_path=self._model_path,
        backend=self._backend,
      )
    if mask_refiner is not None:
      self._mask_refiner = mask_refiner
    elif is_grounding_dino:
      self._mask_refiner = UltralyticsSam2Backend(sam2_model_path)
    else:
      self._mask_refiner = None

  @staticmethod
  def _largest_red_component(
    query: str,
    image_path: str | None,
  ) -> VisionDetection | None:
    if image_path is None or not re.search(r"\bred\b", _grounding_prompt(query).casefold()):
      return None
    path = Path(image_path)
    if path.suffix.casefold() != ".npy":
      return None
    image = np.load(path)
    if image.ndim != 3 or image.shape[2] < 3:
      return None
    red = image[:, :, 0].astype(np.float32)
    green = image[:, :, 1].astype(np.float32)
    blue = image[:, :, 2].astype(np.float32)
    mask = (
      (red > 150.0)
      & (green < 120.0)
      & (blue < 120.0)
      & (red > green * 1.5)
      & (red > blue * 1.5)
    )
    height, width = mask.shape
    seen = np.zeros(mask.shape, dtype=bool)
    best: tuple[int, int, int, int, int] | None = None
    for start_y, start_x in zip(*np.where(mask)):
      if seen[start_y, start_x]:
        continue
      stack = [(int(start_y), int(start_x))]
      seen[start_y, start_x] = True
      xs: list[int] = []
      ys: list[int] = []
      while stack:
        y, x = stack.pop()
        xs.append(x)
        ys.append(y)
        for delta_y, delta_x in ((1, 0), (-1, 0), (0, 1), (0, -1)):
          next_y = y + delta_y
          next_x = x + delta_x
          if (
            0 <= next_y < height
            and 0 <= next_x < width
            and mask[next_y, next_x]
            and not seen[next_y, next_x]
          ):
            seen[next_y, next_x] = True
            stack.append((next_y, next_x))
      area = len(xs)
      if area < 25:
        continue
      candidate = (area, min(xs), min(ys), max(xs), max(ys))
      if best is None or candidate[0] > best[0]:
        best = candidate
    if best is None:
      return None
    _, x1, y1, x2, y2 = best
    bbox = [float(x1), float(y1), float(x2), float(y2)]
    _, center = _mask_area_and_centroid([], bbox)
    return VisionDetection(
      found=True,
      label=query,
      confidence=1.0,
      object_id=f"{query}_red_component",
      bbox_2d=bbox,
      center_px=center,
      source="red_color_filter",
    )

  @staticmethod
  def _validate_options(call: ToolCall, defaults: VisionInferenceOptions) -> VisionInferenceOptions:
    box_threshold = float(call.input.get("box_threshold", defaults.box_threshold))
    text_threshold = float(call.input.get("text_threshold", defaults.text_threshold))
    if not 0.0 <= box_threshold <= 1.0:
      raise ValueError("box_threshold must be between 0 and 1")
    if not 0.0 <= text_threshold <= 1.0:
      raise ValueError("text_threshold must be between 0 and 1")
    device_value = call.input.get("device", defaults.device)
    device = str(device_value) if device_value not in (None, "") else None
    return VisionInferenceOptions(
      box_threshold=box_threshold,
      text_threshold=text_threshold,
      device=device,
    )

  def _refine_detection(
    self,
    detection: VisionDetection,
    *,
    image_path: str | None,
    options: VisionInferenceOptions,
    refine_masks: bool,
    require_masks: bool,
  ) -> VisionDetection:
    if not detection.found or detection.bbox_2d is None:
      return detection
    area, center = _mask_area_and_centroid(
      detection.mask_polygons or [],
      detection.bbox_2d,
    )
    detection = replace(
      detection,
      mask_area_px=detection.mask_area_px or area,
      center_px=detection.center_px or center,
    )
    if not refine_masks:
      if require_masks and not detection.mask_polygons:
        raise ValueError("require_masks=true requires refine_masks=true or detector masks")
      return detection
    if detection.mask_polygons and self._mask_refiner is None:
      return detection
    warnings = list(detection.warnings)
    if self._mask_refiner is None:
      message = "SAM 2 mask refiner is not configured; using the detector box"
      if require_masks:
        raise RuntimeError(message)
      warnings.append(message)
      return replace(
        detection,
        source=f"{detection.source}_sam2_fallback_box",
        warnings=warnings,
      )
    if image_path is None:
      raise ValueError("image_path is required for SAM 2 mask refinement")
    started = time.perf_counter()
    try:
      polygons = self._mask_refiner.segment(
        image_path=image_path,
        bbox_2d=detection.bbox_2d,
        device=options.device,
      )
      if not polygons:
        raise RuntimeError("SAM 2 returned no mask for the selected detection")
    except ImportError as exc:
      if require_masks:
        raise
      warnings.append(f"SAM 2 is unavailable; using detector box: {exc}")
      timing = dict(detection.timing_ms)
      timing["sam2"] = round((time.perf_counter() - started) * 1000.0, 3)
      return replace(
        detection,
        source=f"{detection.source}_sam2_fallback_box",
        timing_ms=timing,
        warnings=warnings,
      )
    except Exception as exc:
      if require_masks:
        raise RuntimeError(f"SAM 2 mask refinement failed: {exc}") from exc
      warnings.append(f"SAM 2 mask refinement failed; using detector box: {exc}")
      timing = dict(detection.timing_ms)
      timing["sam2"] = round((time.perf_counter() - started) * 1000.0, 3)
      return replace(
        detection,
        source=f"{detection.source}_sam2_fallback_box",
        timing_ms=timing,
        warnings=warnings,
      )
    area, center = _mask_area_and_centroid(polygons, detection.bbox_2d)
    timing = dict(detection.timing_ms)
    timing["sam2"] = round((time.perf_counter() - started) * 1000.0, 3)
    return replace(
      detection,
      mask_polygons=polygons,
      mask_area_px=area,
      center_px=center,
      source=f"{detection.source}_sam2",
      timing_ms=timing,
      warnings=warnings,
    )

  def _localize_detection(
    self,
    detection: VisionDetection,
    *,
    depth_path: str | None,
    camera_info_path: str | None,
    camera_info_inline: dict | None,
    t_base_camera: list[list[float]] | None,
    position_base_offset: list[float] | None,
    depth_window: int,
    depth_scale: float,
    camera_frame: str,
    base_frame: str,
  ) -> VisionDetection:
    if (
      not detection.found
      or detection.bbox_2d is None
      or detection.pose_3d is not None
    ):
      return detection
    started = time.perf_counter()
    warnings = list(detection.warnings)
    depth = _load_depth(depth_path)
    camera_info = _load_camera_info(camera_info_path, camera_info_inline)
    if depth is None and camera_info is None:
      return detection
    if depth is None:
      warnings.append("camera_info was provided without a depth map")
      return replace(detection, warnings=warnings)
    if camera_info is None:
      warnings.append("depth map was provided without camera_info")
      return replace(detection, warnings=warnings)
    center = detection.center_px
    if center is None:
      _, center = _mask_area_and_centroid([], detection.bbox_2d)
    sample = _median_depth(
      depth,
      detection.bbox_2d,
      detection.mask_polygons or [],
      center,
      depth_window,
      depth_scale,
    )
    if sample is None:
      warnings.append("no valid depth was found inside the selected object")
      return replace(detection, warnings=warnings)
    u, v, depth_m = sample
    position_camera = _project_to_camera(u, v, depth_m, camera_info)
    position_base = _transform_to_base(position_camera, t_base_camera)
    if position_base is None:
      warnings.append("T_base_camera is missing; only camera-frame position is available")
    elif position_base_offset is not None:
      if (
        not isinstance(position_base_offset, list)
        or len(position_base_offset) != 3
        or not all(isinstance(value, (int, float)) for value in position_base_offset)
      ):
        raise ValueError("position_base_offset must be a 3-number list")
      position_base = [
        position_base[index] + float(position_base_offset[index])
        for index in range(3)
      ]
    pose_3d = None
    position_3d = None
    if position_base is not None:
      pose_3d = [*position_base, 0.0, 0.0, 0.0]
      position_3d = {
        "x": position_base[0],
        "y": position_base[1],
        "z": position_base[2],
        "frame_id": base_frame,
        "unit": "m",
      }
    timing = dict(detection.timing_ms)
    timing["geometry"] = round((time.perf_counter() - started) * 1000.0, 3)
    return replace(
      detection,
      center_px=[u, v],
      depth_m=depth_m,
      position_camera=position_camera,
      position_base=position_base,
      pose_3d=pose_3d,
      position_3d=position_3d,
      camera_frame=camera_frame,
      base_frame=base_frame if position_base is not None else None,
      timing_ms=timing,
      warnings=warnings,
    )

  def run(self, call: ToolCall) -> ToolResult:
    """Run detection, optional mask refinement, and optional RGB-D geometry."""

    query = call.input.get("query")
    if not isinstance(query, str) or not query.strip():
      return ToolResult(
        tool=self.spec.name,
        success=False,
        error="query must be a non-empty string",
      )
    query = query.strip()
    image_path = call.input.get("image_path")
    depth_path = call.input.get("depth_path")
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
    defaults = VisionInferenceOptions(
      box_threshold=self._box_threshold,
      text_threshold=self._text_threshold,
      device=self._device,
    )
    try:
      options = self._validate_options(call, defaults)
      refine_masks = bool(call.input.get("refine_masks", self._refine_masks))
      require_masks = bool(call.input.get("require_masks", self._require_masks))
      red_detection = (
        self._largest_red_component(query, image_path)
        if self._red_color_shortcut
        else None
      )
      if red_detection is not None:
        detection = red_detection
      else:
        detection = self._detector.detect(
          query=query,
          image_path=image_path,
          depth_path=depth_path,
          options=options,
        )
      detection = self._refine_detection(
        detection,
        image_path=image_path,
        options=options,
        refine_masks=refine_masks,
        require_masks=require_masks,
      )
      detection = self._localize_detection(
        detection,
        depth_path=depth_path,
        camera_info_path=call.input.get(
          "camera_info_path",
          self._camera_info_path,
        ),
        camera_info_inline=call.input.get("camera_info", self._camera_info),
        t_base_camera=call.input.get("T_base_camera", self._t_base_camera),
        position_base_offset=call.input.get(
          "position_base_offset",
          self._position_base_offset,
        ),
        depth_window=int(call.input.get("depth_window", self._depth_window)),
        depth_scale=float(call.input.get("depth_scale", self._depth_scale)),
        camera_frame=str(call.input.get("camera_frame", self._camera_frame)),
        base_frame=str(call.input.get("base_frame", self._base_frame)),
      )
    except VisionModelNotReadyError as exc:
      return ToolResult(
        tool=self.spec.name,
        success=False,
        output={
          "found": False,
          "label": query,
          "confidence": 0.0,
          "source": self._backend,
          "model_path": self._model_reference,
        },
        error=f"VISION_MODEL_NOT_READY: {exc}",
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
        },
        error=f"VISION_INPUT_ERROR: {exc}",
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
          "model_path": self._model_reference,
        },
        error=f"VISION_BACKEND_UNAVAILABLE: {exc}",
      )
    except ValueError as exc:
      return ToolResult(
        tool=self.spec.name,
        success=False,
        output={
          "found": False,
          "label": query,
          "confidence": 0.0,
          "source": self._backend,
        },
        error=f"VISION_INPUT_ERROR: {exc}",
      )
    except RuntimeError as exc:
      return ToolResult(
        tool=self.spec.name,
        success=False,
        output={
          "found": False,
          "label": query,
          "confidence": 0.0,
          "source": self._backend,
        },
        error=f"VISION_BACKEND_ERROR: {exc}",
      )
    return ToolResult(
      tool=self.spec.name,
      success=detection.found,
      output=detection.to_output(),
      error=None if detection.found else "OBJECT_NOT_FOUND",
    )
