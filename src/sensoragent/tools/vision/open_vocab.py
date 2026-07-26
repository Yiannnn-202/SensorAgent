"""Open-vocabulary detection, optional mask refinement, and RGB-D geometry."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
import json
import os
from pathlib import Path
import re
import time
from typing import Callable, Protocol, Sequence

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


_SPATIAL_IMAGE_X_RELATIONS = frozenset({"left", "right"})
_SPATIAL_IMAGE_Y_RELATIONS = frozenset({"front", "back"})
_SPATIAL_IMAGE_AREA_RELATIONS = frozenset({"largest", "smallest"})
_SPATIAL_BASE_RELATIONS = frozenset({"nearest", "farthest"})
_SPATIAL_VALID_RELATIONS = (
    _SPATIAL_IMAGE_X_RELATIONS
    | _SPATIAL_IMAGE_Y_RELATIONS
    | _SPATIAL_IMAGE_AREA_RELATIONS
    | _SPATIAL_BASE_RELATIONS
)


@dataclass(frozen=True)
class SpatialConstraint:
  """Spatial selection rule applied across multiple detection candidates."""

  relation: str
  ordinal: int = 1
  reference: str = "arm_base"
  tolerance_px: float = 8.0

  @classmethod
  def from_call(cls, value: object) -> "SpatialConstraint | None":
    """Build a constraint from a tool-call value; None means no constraint."""

    if not isinstance(value, dict):
      return None
    relation = str(value.get("relation", "")).strip().casefold()
    if relation not in _SPATIAL_VALID_RELATIONS:
      return None
    try:
      ordinal = int(value.get("ordinal", 1) or 1)
    except (TypeError, ValueError):
      ordinal = 1
    return cls(relation=relation, ordinal=max(1, ordinal))


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

  def detect_all(
    self,
    *,
    query: str,
    image_path: str | None,
    depth_path: str | None,
    options: VisionInferenceOptions,
  ) -> list[VisionDetection]:
    """Detect every object matching the text query above threshold."""


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

  def detect_all(
    self,
    *,
    query: str,
    image_path: str | None,
    depth_path: str | None,
    options: VisionInferenceOptions,
  ) -> list[VisionDetection]:
    """Raise the model-not-ready error via the single-detect path."""

    self.detect(
      query=query,
      image_path=image_path,
      depth_path=depth_path,
      options=options,
    )
    return []


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

  def detect_all(
    self,
    *,
    query: str,
    image_path: str | None,
    depth_path: str | None,
    options: VisionInferenceOptions,
  ) -> list[VisionDetection]:
    """Raise the dependency error via the single-detect path."""

    self.detect(
      query=query,
      image_path=image_path,
      depth_path=depth_path,
      options=options,
    )
    return []


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


_SPATIAL_MODIFIERS_CN = [
  "左侧的", "左边的", "左侧", "左边", "左面",
  "右侧的", "右边的", "右侧", "右边", "右面",
  "前面的", "前边的", "前面", "前边",
  "后面的", "后边的", "后面", "后边",
  "最近的", "最近", "最远的", "最远",
  "最大的", "最大", "最小的", "最小",
]
_SPATIAL_MODIFIERS_EN = re.compile(
  r"\b(?:left|right|front|back|leftmost|rightmost|nearest|closest|"
  r"farthest|largest|biggest|smallest)\b",
  re.IGNORECASE,
)
_SPATIAL_ORDINAL_CN = re.compile(r"第\s*[一二三四五六七八九十0-9]+\s*(?:个|号)?")


def _strip_spatial_modifiers(prompt: str) -> str:
  """Remove spatial modifiers so they never reach Grounding DINO as text."""

  for modifier in _SPATIAL_MODIFIERS_CN:
    prompt = prompt.replace(modifier, " ")
  prompt = _SPATIAL_ORDINAL_CN.sub(" ", prompt)
  return _SPATIAL_MODIFIERS_EN.sub(" ", prompt)


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
  prompt = _strip_spatial_modifiers(prompt)
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
  def _all_detections(result, source: str, model: str) -> list[VisionDetection]:
    boxes = getattr(result, "boxes", None)
    if boxes is None or len(boxes) == 0:
      return []
    xyxy = boxes.xyxy.cpu().numpy()
    confidence = boxes.conf.cpu().numpy()
    classes = (
      boxes.cls.cpu().numpy().astype(int)
      if boxes.cls is not None
      else np.zeros(len(confidence), dtype=int)
    )
    names = getattr(result, "names", {}) or {}
    masks = getattr(result, "masks", None)
    raw_polygons = getattr(masks, "xy", None) if masks is not None else None
    detections: list[VisionDetection] = []
    for index in range(len(confidence)):
      label = str(names.get(int(classes[index]), int(classes[index])))
      polygons = None
      if raw_polygons is not None and index < len(raw_polygons):
        polygon = [[float(x), float(y)] for x, y in raw_polygons[index].tolist()]
        if polygon:
          polygons = [polygon]
      bbox = [float(value) for value in xyxy[index]]
      area, center = _mask_area_and_centroid(polygons or [], bbox)
      detections.append(
        VisionDetection(
          found=True,
          label=label,
          confidence=float(confidence[index]),
          object_id=f"{label}_{index + 1:03d}",
          bbox_2d=bbox,
          mask_polygons=polygons,
          mask_area_px=area,
          center_px=center,
          model=model,
          source=source,
        )
      )
    return detections

  def _not_found(self, query: str, elapsed_ms: float) -> VisionDetection:
    return VisionDetection(
      found=False,
      label=query,
      confidence=0.0,
      model=self._model_path.as_posix(),
      timing_ms={"detector": elapsed_ms},
      source=self._backend,
    )

  def _detect_candidates(
    self,
    *,
    query: str,
    image_path: str | None,
    options: VisionInferenceOptions,
  ) -> list[VisionDetection]:
    """Run YOLOE once and return every above-threshold detection with timing."""

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
      return [self._not_found(query, elapsed_ms)]
    detections = self._all_detections(
      results[0],
      self._backend,
      self._model_path.as_posix(),
    )
    if not detections:
      return [self._not_found(query, elapsed_ms)]
    return [replace(detection, timing_ms={"detector": elapsed_ms}) for detection in detections]

  def detect_all(
    self,
    *,
    query: str,
    image_path: str | None,
    depth_path: str | None,
    options: VisionInferenceOptions,
  ) -> list[VisionDetection]:
    """Run YOLOE and return every matching detection above threshold."""

    del depth_path
    return self._detect_candidates(query=query, image_path=image_path, options=options)

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
    candidates = self._detect_candidates(
      query=query, image_path=image_path, options=options
    )
    found = [candidate for candidate in candidates if candidate.found]
    if not found:
      return candidates[0]
    return max(found, key=lambda detection: detection.confidence)


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

  def _run_grounding(
    self,
    *,
    query: str,
    image_path: str | None,
    options: VisionInferenceOptions,
  ) -> tuple[dict, str, float]:
    """Run Grounding DINO inference and return (result, prompt, elapsed_ms)."""

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
    return results[0], prompt, elapsed_ms

  def _boxes_to_detections(
    self,
    result: dict,
    prompt: str,
    query: str,
    elapsed_ms: float,
  ) -> list[VisionDetection]:
    """Turn Grounding DINO result boxes into a list of detections."""

    del query
    boxes = self._as_list(result.get("boxes", []))
    scores = self._as_list(result.get("scores", []))
    raw_labels = result.get("text_labels")
    labels = self._as_list(raw_labels) if raw_labels is not None else [prompt] * len(boxes)
    count = min(len(boxes), len(scores), len(labels))
    detections: list[VisionDetection] = []
    for index in range(count):
      bbox = [float(value) for value in boxes[index]]
      label = labels[index] if isinstance(labels[index], str) else prompt
      _, center = _mask_area_and_centroid([], bbox)
      detections.append(
        VisionDetection(
          found=True,
          label=str(label),
          confidence=float(scores[index]),
          object_id=f"{prompt.replace(' ', '_')}_{index + 1:03d}",
          bbox_2d=bbox,
          center_px=center,
          model=self.model_id,
          timing_ms={"grounding_dino": elapsed_ms},
          source="grounding_dino",
        )
      )
    return detections

  def _not_found(self, query: str, elapsed_ms: float) -> VisionDetection:
    return VisionDetection(
      found=False,
      label=query,
      confidence=0.0,
      model=self.model_id,
      timing_ms={"grounding_dino": elapsed_ms},
      source="grounding_dino",
    )

  def detect_all(
    self,
    *,
    query: str,
    image_path: str | None,
    depth_path: str | None,
    options: VisionInferenceOptions,
  ) -> list[VisionDetection]:
    """Run text-grounded detection and return every matching box."""

    del depth_path
    result, prompt, elapsed_ms = self._run_grounding(
      query=query, image_path=image_path, options=options
    )
    detections = self._boxes_to_detections(result, prompt, query, elapsed_ms)
    if not detections:
      return [self._not_found(query, elapsed_ms)]
    return detections

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
    candidates = self.detect_all(
      query=query,
      image_path=image_path,
      depth_path=depth_path,
      options=options,
    )
    found = [candidate for candidate in candidates if candidate.found]
    if not found:
      return candidates[0]
    return max(found, key=lambda detection: detection.confidence)


class UltralyticsSam2Backend:
  """Lazy SAM 2 adapter using the Ultralytics box-prompt API."""

  def __init__(self, weights_path: str | Path | None = None) -> None:
    configured = os.getenv("SENSORAGENT_SAM2_WEIGHTS")
    self.weights_path = str(weights_path or configured or "sam2_t.pt")
    self._model = None

  def _load_model(self):
    if self._model is not None:
      return self._model
    if not Path(self.weights_path).is_file():
      raise VisionModelNotReadyError(
        f"SAM 2 weights not found: {self.weights_path}. Put the file in the "
        "repository root or set sam2_model_path / SENSORAGENT_SAM2_WEIGHTS."
      )
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


def _image_relation_key(
  detection: VisionDetection,
  relation: str,
) -> float | None:
  """Sort key for image-space relations; None if the relation is not image-space."""

  bbox = detection.bbox_2d
  if bbox is None or len(bbox) < 4:
    return None
  center = detection.center_px
  if center is None or len(center) < 2:
    center = [(bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0]
  if relation in _SPATIAL_IMAGE_X_RELATIONS:
    return float(center[0])
  if relation in _SPATIAL_IMAGE_Y_RELATIONS:
    return float(center[1])
  if relation in _SPATIAL_IMAGE_AREA_RELATIONS:
    return abs((bbox[2] - bbox[0]) * (bbox[3] - bbox[1]))
  return None


def _resolve_spatial(
  candidates: list[VisionDetection],
  constraint: SpatialConstraint,
  base_xy_of: Callable[[VisionDetection], tuple[float, float] | None] | None = None,
) -> tuple[VisionDetection | None, list[VisionDetection], str | None]:
  """Pick one candidate by the spatial constraint.

  Returns (winner, alternatives, error). error is None on success, "not_found"
  when no candidate qualifies, or "ambiguous" on a tie or out-of-range ordinal.
  """

  if not candidates:
    return None, [], "not_found"
  relation = constraint.relation
  take_max = relation in {"right", "front", "largest", "farthest"}
  keyed: list[tuple[float, VisionDetection]] = []
  for detection in candidates:
    if relation in _SPATIAL_BASE_RELATIONS:
      if base_xy_of is None:
        continue
      xy = base_xy_of(detection)
      if xy is None:
        continue
      key = float((xy[0] ** 2 + xy[1] ** 2) ** 0.5)
    else:
      key = _image_relation_key(detection, relation)
      if key is None:
        continue
    keyed.append((key, detection))
  if not keyed:
    return None, candidates, "ambiguous"
  keyed.sort(key=lambda item: item[0], reverse=take_max)
  if constraint.ordinal > len(keyed):
    return None, candidates, "ambiguous"
  if (
    constraint.ordinal == 1
    and len(keyed) >= 2
    and relation in (_SPATIAL_IMAGE_X_RELATIONS | _SPATIAL_IMAGE_Y_RELATIONS)
    and abs(keyed[0][0] - keyed[1][0]) <= constraint.tolerance_px
  ):
    return None, candidates, "ambiguous"
  winner = keyed[constraint.ordinal - 1][1]
  alternatives = [detection for _, detection in keyed if detection is not winner]
  return winner, alternatives, None


def _within_workspace(
  point_xy: tuple[float, float] | None,
  workspace: dict,
) -> bool:
  """True if a base XY point is inside the workspace x/y envelope."""

  if point_xy is None or not workspace:
    return True
  for axis, value in (("x", point_xy[0]), ("y", point_xy[1])):
    bounds = workspace.get(axis)
    if isinstance(bounds, list) and len(bounds) == 2:
      try:
        low, high = float(bounds[0]), float(bounds[1])
      except (TypeError, ValueError):
        continue
      if value < low or value > high:
        return False
  return True


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
    workspace: dict | None = None,
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
    self._workspace = dict(workspace or {})
    try:
      self._table_z = float(self._workspace.get("table_z", 0.12))
    except (TypeError, ValueError):
      self._table_z = 0.12
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
    except (RuntimeError, ValueError, OSError) as exc:
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

  def _base_xy_estimator(
    self,
    camera_info: dict | None,
    t_base_camera: list[list[float]] | None,
  ) -> Callable[[VisionDetection], tuple[float, float] | None] | None:
    """Build a depth-free pixel -> base XY estimator on the table plane.

    Returns None when camera intrinsics or the camera->base transform are
    unavailable, so nearest/farthest and workspace filtering degrade gracefully.
    """

    if camera_info is None or t_base_camera is None:
      return None
    try:
      fx, fy, cx, cy = _camera_intrinsics(camera_info)
    except (ValueError, KeyError, TypeError):
      return None
    matrix = np.asarray(t_base_camera, dtype=np.float64)
    if matrix.shape != (4, 4):
      return None
    origin = matrix[:3, 3]
    rotation = matrix[:3, :3]
    table_z = self._table_z

    def estimate(detection: VisionDetection) -> tuple[float, float] | None:
      center = detection.center_px
      if center is None or len(center) < 2:
        bbox = detection.bbox_2d
        if bbox is None or len(bbox) < 4:
          return None
        center = [(bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0]
      direction = rotation @ np.array(
        [(float(center[0]) - cx) / fx, (float(center[1]) - cy) / fy, 1.0]
      )
      if abs(direction[2]) < 1e-9:
        return None
      scale = (table_z - float(origin[2])) / float(direction[2])
      point = origin + scale * direction
      return float(point[0]), float(point[1])

    return estimate

  def _select_by_spatial(
    self,
    *,
    query: str,
    image_path: str | None,
    depth_path: str | None,
    options: VisionInferenceOptions,
    spatial: SpatialConstraint,
    camera_info: dict | None,
    t_base_camera: list[list[float]] | None,
  ) -> tuple[VisionDetection | None, list[VisionDetection], str | None]:
    """Collect candidates, filter by workspace, and resolve the spatial constraint."""

    candidates = self._detector.detect_all(
      query=query,
      image_path=image_path,
      depth_path=depth_path,
      options=options,
    )
    candidates = [
      candidate
      for candidate in candidates
      if candidate.found and candidate.bbox_2d is not None
    ]
    base_xy_of = self._base_xy_estimator(camera_info, t_base_camera)
    if self._workspace and base_xy_of is not None:
      candidates = [
        candidate
        for candidate in candidates
        if _within_workspace(base_xy_of(candidate), self._workspace)
      ]
    return _resolve_spatial(candidates, spatial, base_xy_of=base_xy_of)

  def _spatial_failure(
    self,
    query: str,
    spatial: SpatialConstraint,
    alternatives: list[VisionDetection],
    error_kind: str,
  ) -> ToolResult:
    """Build the not-found / ambiguous ToolResult for the spatial path."""

    code = "OBJECT_AMBIGUOUS" if error_kind == "ambiguous" else "OBJECT_NOT_FOUND"
    candidate_outputs = [alternative.to_output() for alternative in alternatives]
    return ToolResult(
      tool=self.spec.name,
      success=False,
      output={
        "found": False,
        "label": query,
        "confidence": 0.0,
        "source": self._backend,
        "spatial_constraint": {
          "relation": spatial.relation,
          "ordinal": spatial.ordinal,
        },
        "candidates": candidate_outputs,
      },
      error=(
        f"{code}: relation={spatial.relation} ordinal={spatial.ordinal} "
        f"matched {len(candidate_outputs)} candidate(s)"
      ),
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
      spatial = SpatialConstraint.from_call(call.input.get("spatial_constraint"))
      red_detection = (
        self._largest_red_component(query, image_path)
        if self._red_color_shortcut
        else None
      )
      alternatives: list[VisionDetection] = []
      if red_detection is not None:
        detection = red_detection
      elif spatial is not None:
        detection, alternatives, spatial_error = self._select_by_spatial(
          query=query,
          image_path=image_path,
          depth_path=depth_path,
          options=options,
          spatial=spatial,
          camera_info=_load_camera_info(
            call.input.get("camera_info_path", self._camera_info_path),
            call.input.get("camera_info", self._camera_info),
          ),
          t_base_camera=call.input.get("T_base_camera", self._t_base_camera),
        )
        if spatial_error is not None:
          return self._spatial_failure(query, spatial, alternatives, spatial_error)
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
    except PermissionError as exc:
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
    except OSError as exc:
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
    output = detection.to_output()
    if alternatives:
      output["candidates"] = [alternative.to_output() for alternative in alternatives]
    return ToolResult(
      tool=self.spec.name,
      success=detection.found,
      output=output,
      error=None if detection.found else "OBJECT_NOT_FOUND",
    )
