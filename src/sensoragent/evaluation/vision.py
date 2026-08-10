"""Dataset validation and repeatable evaluation for open-vocabulary vision."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path
import time
from typing import Callable, Sequence

import numpy as np


VisionRunner = Callable[[dict[str, object]], object]
_SPLITS = frozenset({"train", "val", "test"})
_PATH_FIELDS = ("image", "depth", "camera_info")


@dataclass(frozen=True)
class ValidationIssue:
  """One actionable dataset-manifest problem."""

  code: str
  message: str
  line: int | None = None
  sample_id: str | None = None
  severity: str = "error"


@dataclass(frozen=True)
class ManifestValidation:
  """Parsed samples and all validation findings."""

  manifest: Path
  samples: tuple[dict[str, object], ...]
  issues: tuple[ValidationIssue, ...]

  @property
  def valid(self) -> bool:
    return not any(issue.severity == "error" for issue in self.issues)

  def to_dict(self) -> dict[str, object]:
    return {
      "manifest": str(self.manifest),
      "valid": self.valid,
      "sample_count": len(self.samples),
      "error_count": sum(issue.severity == "error" for issue in self.issues),
      "warning_count": sum(issue.severity == "warning" for issue in self.issues),
      "issues": [asdict(issue) for issue in self.issues],
    }


@dataclass(frozen=True)
class AcceptanceThresholds:
  """Optional pass/fail thresholds for one evaluation run."""

  min_precision: float | None = None
  min_recall: float | None = None
  min_box_iou: float | None = None
  min_mask_iou: float | None = None
  min_map50_95: float | None = None
  max_center_error_px: float | None = None
  max_warm_p95_ms: float | None = None


@dataclass(frozen=True)
class EvaluationRun:
  """Persisted rows, aggregate metrics, and acceptance result."""

  rows: tuple[dict[str, object], ...]
  summary: dict[str, object]
  failures: tuple[str, ...]

  @property
  def passed(self) -> bool:
    return not self.failures


def _issue(
  issues: list[ValidationIssue],
  code: str,
  message: str,
  *,
  line: int | None = None,
  sample_id: str | None = None,
  severity: str = "error",
) -> None:
  issues.append(
    ValidationIssue(
      code=code,
      message=message,
      line=line,
      sample_id=sample_id,
      severity=severity,
    )
  )


def _relative_path(
  value: object,
  field: str,
  *,
  root: Path,
  line: int,
  sample_id: str | None,
  issues: list[ValidationIssue],
  check_files: bool,
) -> Path | None:
  if value is None:
    return None
  if not isinstance(value, str) or not value.strip():
    _issue(
      issues,
      "INVALID_PATH",
      f"{field} must be a non-empty relative path",
      line=line,
      sample_id=sample_id,
    )
    return None
  path = Path(value)
  if path.is_absolute():
    _issue(
      issues,
      "ABSOLUTE_PATH",
      f"{field} must be relative to the manifest: {value}",
      line=line,
      sample_id=sample_id,
    )
    return None
  resolved = (root / path).resolve()
  if check_files and not resolved.is_file():
    _issue(
      issues,
      "MISSING_FILE",
      f"{field} does not exist: {value}",
      line=line,
      sample_id=sample_id,
    )
  return resolved


def _number_list(value: object, length: int) -> bool:
  return (
    isinstance(value, list)
    and len(value) == length
    and all(isinstance(item, (int, float)) and math.isfinite(item) for item in value)
  )


def _validate_sample(
  sample: dict[str, object],
  *,
  root: Path,
  line: int,
  issues: list[ValidationIssue],
  check_files: bool,
) -> None:
  sample_id_value = sample.get("sample_id")
  sample_id = sample_id_value if isinstance(sample_id_value, str) else None
  for field in ("sample_id", "scene_id", "query"):
    value = sample.get(field)
    if not isinstance(value, str) or not value.strip():
      _issue(
        issues,
        "MISSING_FIELD",
        f"{field} must be a non-empty string",
        line=line,
        sample_id=sample_id,
      )
  split = sample.get("split")
  if split not in _SPLITS:
    _issue(
      issues,
      "INVALID_SPLIT",
      f"split must be one of {sorted(_SPLITS)}",
      line=line,
      sample_id=sample_id,
    )
  _relative_path(
    sample.get("image"),
    "image",
    root=root,
    line=line,
    sample_id=sample_id,
    issues=issues,
    check_files=check_files,
  )
  for field in ("depth", "camera_info"):
    if field in sample:
      _relative_path(
        sample.get(field),
        field,
        root=root,
        line=line,
        sample_id=sample_id,
        issues=issues,
        check_files=check_files,
      )

  expected = sample.get("expected")
  if not isinstance(expected, dict) or not isinstance(expected.get("found"), bool):
    _issue(
      issues,
      "INVALID_EXPECTED",
      "expected.found must be true or false",
      line=line,
      sample_id=sample_id,
    )
  else:
    bbox = expected.get("bbox_2d")
    if bbox is not None:
      if not _number_list(bbox, 4) or not (bbox[2] > bbox[0] and bbox[3] > bbox[1]):
        _issue(
          issues,
          "INVALID_BBOX",
          "expected.bbox_2d must be [x1, y1, x2, y2] with x2>x1 and y2>y1",
          line=line,
          sample_id=sample_id,
        )
    center = expected.get("center_px")
    if center is not None and not _number_list(center, 2):
      _issue(
        issues,
        "INVALID_CENTER",
        "expected.center_px must contain two finite numbers",
        line=line,
        sample_id=sample_id,
      )
    if "mask" in expected:
      _relative_path(
        expected.get("mask"),
        "expected.mask",
        root=root,
        line=line,
        sample_id=sample_id,
        issues=issues,
        check_files=check_files,
      )

  source = sample.get("source")
  if not isinstance(source, dict):
    _issue(
      issues,
      "MISSING_SOURCE",
      "source must record kind and provenance",
      line=line,
      sample_id=sample_id,
    )
  else:
    kind = source.get("kind")
    if not isinstance(kind, str) or not kind.strip():
      _issue(
        issues,
        "MISSING_SOURCE_KIND",
        "source.kind is required",
        line=line,
        sample_id=sample_id,
      )
    if kind == "public":
      for field in ("url", "license"):
        value = source.get(field)
        if not isinstance(value, str) or not value.strip():
          _issue(
            issues,
            "MISSING_PUBLIC_LICENSE",
            f"public data requires source.{field}",
            line=line,
            sample_id=sample_id,
          )


def validate_manifest(
  manifest_path: str | Path,
  *,
  check_files: bool = True,
) -> ManifestValidation:
  """Load a JSONL dataset manifest and report all actionable problems."""

  manifest = Path(manifest_path).resolve()
  issues: list[ValidationIssue] = []
  samples: list[dict[str, object]] = []
  if not manifest.is_file():
    _issue(issues, "MISSING_MANIFEST", f"manifest does not exist: {manifest}")
    return ManifestValidation(manifest, tuple(samples), tuple(issues))

  for line_number, raw_line in enumerate(
    manifest.read_text(encoding="utf-8").splitlines(), start=1
  ):
    if not raw_line.strip():
      continue
    try:
      value = json.loads(raw_line)
    except json.JSONDecodeError as exc:
      _issue(
        issues,
        "INVALID_JSON",
        f"invalid JSON: {exc.msg}",
        line=line_number,
      )
      continue
    if not isinstance(value, dict):
      _issue(
        issues,
        "INVALID_SAMPLE",
        "each JSONL line must be an object",
        line=line_number,
      )
      continue
    samples.append(value)
    _validate_sample(
      value,
      root=manifest.parent,
      line=line_number,
      issues=issues,
      check_files=check_files,
    )

  seen_ids: dict[str, int] = {}
  scene_splits: dict[str, set[str]] = {}
  for line_number, sample in enumerate(samples, start=1):
    sample_id = sample.get("sample_id")
    if isinstance(sample_id, str) and sample_id:
      if sample_id in seen_ids:
        _issue(
          issues,
          "DUPLICATE_SAMPLE_ID",
          f"sample_id also appears on data row {seen_ids[sample_id]}",
          line=line_number,
          sample_id=sample_id,
        )
      else:
        seen_ids[sample_id] = line_number
    scene_id = sample.get("scene_id")
    split = sample.get("split")
    if isinstance(scene_id, str) and split in _SPLITS:
      scene_splits.setdefault(scene_id, set()).add(str(split))
  for scene_id, splits in scene_splits.items():
    if len(splits) > 1:
      _issue(
        issues,
        "SCENE_SPLIT_LEAKAGE",
        f"scene_id {scene_id!r} appears in multiple splits: {sorted(splits)}",
      )
  if not samples:
    _issue(issues, "EMPTY_MANIFEST", "manifest contains no samples")
  return ManifestValidation(manifest, tuple(samples), tuple(issues))


def box_iou(first: Sequence[float], second: Sequence[float]) -> float:
  """Compute intersection over union for two xyxy boxes."""

  left = max(float(first[0]), float(second[0]))
  top = max(float(first[1]), float(second[1]))
  right = min(float(first[2]), float(second[2]))
  bottom = min(float(first[3]), float(second[3]))
  intersection = max(0.0, right - left) * max(0.0, bottom - top)
  first_area = max(0.0, float(first[2]) - float(first[0])) * max(
    0.0, float(first[3]) - float(first[1])
  )
  second_area = max(0.0, float(second[2]) - float(second[0])) * max(
    0.0, float(second[3]) - float(second[1])
  )
  union = first_area + second_area - intersection
  return intersection / union if union > 0.0 else 0.0


def _center(value: dict[str, object]) -> list[float] | None:
  center = value.get("center_px")
  if _number_list(center, 2):
    return [float(center[0]), float(center[1])]
  bbox = value.get("bbox_2d")
  if _number_list(bbox, 4):
    return [
      (float(bbox[0]) + float(bbox[2])) / 2.0,
      (float(bbox[1]) + float(bbox[3])) / 2.0,
    ]
  return None


def _mask_iou(
  mask_path: Path,
  polygons: object,
) -> float | None:
  if not isinstance(polygons, list) or not polygons:
    return None
  try:
    from PIL import Image, ImageDraw
  except ImportError as exc:
    raise ImportError("Pillow is required to evaluate mask IoU") from exc
  expected = np.asarray(Image.open(mask_path).convert("L")) > 0
  predicted_image = Image.new("1", (expected.shape[1], expected.shape[0]), 0)
  draw = ImageDraw.Draw(predicted_image)
  for polygon in polygons:
    if not isinstance(polygon, list) or len(polygon) < 3:
      continue
    points = [
      (float(point[0]), float(point[1]))
      for point in polygon
      if _number_list(point, 2)
    ]
    if len(points) >= 3:
      draw.polygon(points, fill=1)
  predicted = np.asarray(predicted_image, dtype=bool)
  union = np.logical_or(expected, predicted).sum()
  if union == 0:
    return 1.0
  return float(np.logical_and(expected, predicted).sum() / union)


def _normalize_result(result: object) -> dict[str, object]:
  if isinstance(result, dict):
    return {
      "tool": result.get("tool", "vision.open_vocab_detect"),
      "success": bool(result.get("success", False)),
      "output": result.get("output") if isinstance(result.get("output"), dict) else {},
      "error": result.get("error"),
    }
  return {
    "tool": getattr(result, "tool", "vision.open_vocab_detect"),
    "success": bool(getattr(result, "success", False)),
    "output": getattr(result, "output", None) or {},
    "error": getattr(result, "error", None),
  }


def _percentile(values: Sequence[float], percentile: float) -> float | None:
  if not values:
    return None
  return round(float(np.percentile(np.asarray(values), percentile)), 3)


def _mean(values: Sequence[float]) -> float | None:
  return round(float(np.mean(np.asarray(values))), 6) if values else None


def _average_precision(rows: Sequence[dict[str, object]], iou_threshold: float) -> float | None:
  """Compute single-query 101-point interpolated AP from persisted rows.

  The current Tool returns one best candidate for one text query. This is a
  deliberately explicit query-level protocol: one row is one image/query,
  positives contain at most one expected box, and confidence ranks returned
  candidates. It is not a replacement for COCO multi-instance mAP.
  """

  positives = sum(bool(row["expected"].get("found", False)) for row in rows)
  if positives == 0:
    return None
  predictions = [
    row
    for row in rows
    if bool(row["prediction"].get("found", False))
  ]
  predictions.sort(
    key=lambda row: float(row["prediction"].get("confidence", 0.0) or 0.0),
    reverse=True,
  )
  true_positive: list[float] = []
  false_positive: list[float] = []
  for row in predictions:
    expected = row["expected"]
    prediction = row["prediction"]
    expected_box = expected.get("bbox_2d")
    predicted_box = prediction.get("bbox_2d")
    matched = (
      bool(expected.get("found", False))
      and _number_list(expected_box, 4)
      and _number_list(predicted_box, 4)
      and box_iou(expected_box, predicted_box) >= iou_threshold
    )
    true_positive.append(1.0 if matched else 0.0)
    false_positive.append(0.0 if matched else 1.0)
  if not true_positive:
    return 0.0
  cumulative_tp = np.cumsum(np.asarray(true_positive))
  cumulative_fp = np.cumsum(np.asarray(false_positive))
  recalls = cumulative_tp / float(positives)
  precisions = cumulative_tp / np.maximum(cumulative_tp + cumulative_fp, 1e-12)
  interpolated = []
  for recall_level in np.linspace(0.0, 1.0, 101):
    available = precisions[recalls >= recall_level]
    interpolated.append(float(np.max(available)) if available.size else 0.0)
  return round(float(np.mean(interpolated)), 6)


def _average_precision_by_query(
  rows: Sequence[dict[str, object]],
  iou_threshold: float,
) -> float | None:
  """Average AP over text queries that have at least one positive sample."""

  grouped: dict[str, list[dict[str, object]]] = {}
  for row in rows:
    grouped.setdefault(str(row["query"]), []).append(row)
  values = [
    score
    for query_rows in grouped.values()
    if (score := _average_precision(query_rows, iou_threshold)) is not None
  ]
  return _mean(values)


def _average_precision_50_95(rows: Sequence[dict[str, object]]) -> float | None:
  values = [
    score
    for threshold in np.arange(0.50, 0.951, 0.05)
    if (score := _average_precision_by_query(rows, round(float(threshold), 2))) is not None
  ]
  return _mean(values)


def _build_tool_input(
  sample: dict[str, object],
  *,
  root: Path,
  device: str | None,
  refine_masks: bool,
  require_masks: bool,
  box_threshold: float | None,
  text_threshold: float | None,
  overlay_path: Path | None,
) -> dict[str, object]:
  input_data: dict[str, object] = {
    "query": str(sample["query"]),
    "image_path": str((root / str(sample["image"])).resolve()),
    "refine_masks": refine_masks,
    "require_masks": require_masks,
  }
  optional: dict[str, object | None] = {
    "depth_path": (
      str((root / str(sample["depth"])).resolve()) if sample.get("depth") else None
    ),
    "camera_info_path": (
      str((root / str(sample["camera_info"])).resolve())
      if sample.get("camera_info")
      else None
    ),
    "device": device,
    "box_threshold": box_threshold,
    "text_threshold": text_threshold,
    "overlay_path": str(overlay_path) if overlay_path is not None else None,
  }
  input_data.update({key: value for key, value in optional.items() if value is not None})
  return input_data


def _evaluate_row(
  sample: dict[str, object],
  result: dict[str, object],
  *,
  root: Path,
  wall_clock_ms: float,
) -> dict[str, object]:
  expected = sample["expected"]
  output = result["output"]
  expected_found = bool(expected["found"])
  predicted_found = bool(output.get("found", False))
  if expected_found and predicted_found:
    outcome = "tp"
  elif expected_found:
    outcome = "fn"
  elif predicted_found:
    outcome = "fp"
  else:
    outcome = "tn"

  metrics: dict[str, float] = {}
  expected_bbox = expected.get("bbox_2d")
  predicted_bbox = output.get("bbox_2d")
  if _number_list(expected_bbox, 4) and _number_list(predicted_bbox, 4):
    metrics["box_iou"] = round(box_iou(expected_bbox, predicted_bbox), 6)
  expected_center = _center(expected)
  predicted_center = _center(output)
  if expected_center is not None and predicted_center is not None:
    metrics["center_error_px"] = round(
      math.dist(expected_center, predicted_center), 6
    )
  mask_value = expected.get("mask")
  if isinstance(mask_value, str):
    mask_score = _mask_iou((root / mask_value).resolve(), output.get("mask_polygons"))
    if mask_score is not None:
      metrics["mask_iou"] = round(mask_score, 6)

  inference_error = result.get("error")
  execution_ok = bool(result.get("success")) or (
    not predicted_found and inference_error == "OBJECT_NOT_FOUND"
  )
  return {
    "sample_id": sample["sample_id"],
    "scene_id": sample["scene_id"],
    "split": sample["split"],
    "query": sample["query"],
    "expected": expected,
    "prediction": output,
    "outcome": outcome,
    "execution_ok": execution_ok,
    "error": inference_error,
    "metrics": metrics,
    "wall_clock_ms": round(wall_clock_ms, 3),
  }


def _summary(rows: Sequence[dict[str, object]], warmup_runs: int) -> dict[str, object]:
  counts = {name: sum(row["outcome"] == name for row in rows) for name in ("tp", "fp", "tn", "fn")}
  precision_denominator = counts["tp"] + counts["fp"]
  recall_denominator = counts["tp"] + counts["fn"]
  precision = counts["tp"] / precision_denominator if precision_denominator else None
  recall = counts["tp"] / recall_denominator if recall_denominator else None
  f1 = (
    2.0 * precision * recall / (precision + recall)
    if precision is not None and recall is not None and precision + recall > 0
    else None
  )
  metric_values = {
    name: [
      float(row["metrics"][name])
      for row in rows
      if name in row["metrics"]
    ]
    for name in ("box_iou", "mask_iou", "center_error_px")
  }
  wall_times = [float(row["wall_clock_ms"]) for row in rows]
  warm_times = wall_times[max(0, warmup_runs) :]
  mask_outputs = [
    row for row in rows if row["prediction"].get("mask_polygons")
  ]
  return {
    "sample_count": len(rows),
    "execution_error_count": sum(not row["execution_ok"] for row in rows),
    "confusion": counts,
    "precision": round(precision, 6) if precision is not None else None,
    "recall": round(recall, 6) if recall is not None else None,
    "f1": round(f1, 6) if f1 is not None else None,
    "mean_box_iou": _mean(metric_values["box_iou"]),
    "box_iou_sample_count": len(metric_values["box_iou"]),
    "mean_mask_iou": _mean(metric_values["mask_iou"]),
    "mask_iou_sample_count": len(metric_values["mask_iou"]),
    "mean_center_error_px": _mean(metric_values["center_error_px"]),
    "center_error_sample_count": len(metric_values["center_error_px"]),
    "ap50": _average_precision_by_query(rows, 0.50),
    "ap75": _average_precision_by_query(rows, 0.75),
    "map50_95": _average_precision_50_95(rows),
    "ap_protocol": {
      "name": "query_level_single_best_box",
      "iou_thresholds": [round(float(value), 2) for value in np.arange(0.50, 0.951, 0.05)],
      "interpolation": "101_point",
      "warning": "Not COCO multi-instance mAP; preserve all candidates for that protocol.",
    },
    "mask_output_rate": round(len(mask_outputs) / len(rows), 6) if rows else None,
    "latency_ms": {
      "warmup_runs_excluded": min(max(0, warmup_runs), len(rows)),
      "cold_first": wall_times[0] if wall_times else None,
      "warm_mean": _mean(warm_times),
      "warm_p50": _percentile(warm_times, 50),
      "warm_p95": _percentile(warm_times, 95),
    },
  }


def check_acceptance(
  summary: dict[str, object],
  thresholds: AcceptanceThresholds,
) -> tuple[str, ...]:
  """Compare available aggregate metrics with requested acceptance gates."""

  failures: list[str] = []
  checks = (
    ("precision", thresholds.min_precision, "min"),
    ("recall", thresholds.min_recall, "min"),
    ("mean_box_iou", thresholds.min_box_iou, "min"),
    ("mean_mask_iou", thresholds.min_mask_iou, "min"),
    ("mean_center_error_px", thresholds.max_center_error_px, "max"),
  )
  for name, threshold, direction in checks:
    if threshold is None:
      continue
    value = summary.get(name)
    if value is None:
      failures.append(f"{name} is unavailable but a threshold was requested")
    elif direction == "min" and float(value) < threshold:
      failures.append(f"{name}={value} is below {threshold}")
    elif direction == "max" and float(value) > threshold:
      failures.append(f"{name}={value} is above {threshold}")
  if thresholds.max_warm_p95_ms is not None:
    latency = summary.get("latency_ms") or {}
    value = latency.get("warm_p95")
    if value is None:
      failures.append("latency_ms.warm_p95 is unavailable but a threshold was requested")
    elif float(value) > thresholds.max_warm_p95_ms:
      failures.append(
        f"latency_ms.warm_p95={value} is above {thresholds.max_warm_p95_ms}"
      )
  if thresholds.min_map50_95 is not None:
    value = summary.get("map50_95")
    if value is None:
      failures.append("map50_95 is unavailable but a threshold was requested")
    elif float(value) < thresholds.min_map50_95:
      failures.append(f"map50_95={value} is below {thresholds.min_map50_95}")
  execution_errors = int(summary.get("execution_error_count", 0))
  if execution_errors:
    failures.append(f"{execution_errors} sample(s) failed during model execution")
  return tuple(failures)


def evaluate_manifest(
  manifest_path: str | Path,
  *,
  runner: VisionRunner,
  output_dir: str | Path,
  device: str | None = None,
  refine_masks: bool = True,
  require_masks: bool = False,
  box_threshold: float | None = None,
  text_threshold: float | None = None,
  save_overlays: bool = False,
  warmup_runs: int = 1,
  thresholds: AcceptanceThresholds | None = None,
  tool_name: str = "vision.open_vocab_detect",
) -> EvaluationRun:
  """Validate a manifest, run one persistent backend, and save report artifacts."""

  validation = validate_manifest(manifest_path, check_files=True)
  if not validation.valid:
    messages = [f"{issue.code}: {issue.message}" for issue in validation.issues]
    raise ValueError("dataset manifest is invalid:\n" + "\n".join(messages))
  destination = Path(output_dir).resolve()
  destination.mkdir(parents=True, exist_ok=True)
  overlay_dir = destination / "overlays"
  if save_overlays:
    overlay_dir.mkdir(parents=True, exist_ok=True)

  rows: list[dict[str, object]] = []
  for sample in validation.samples:
    overlay_path = (
      overlay_dir / f"{sample['sample_id']}.jpg" if save_overlays else None
    )
    input_data = _build_tool_input(
      sample,
      root=validation.manifest.parent,
      device=device,
      refine_masks=refine_masks,
      require_masks=require_masks,
      box_threshold=box_threshold,
      text_threshold=text_threshold,
      overlay_path=overlay_path,
    )
    started = time.perf_counter()
    try:
      result = _normalize_result(runner(input_data))
    except Exception as exc:  # Keep the remaining dataset evaluable after one failure.
      result = {
        "tool": tool_name,
        "success": False,
        "output": {},
        "error": f"EVALUATION_RUNNER_ERROR: {exc}",
      }
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    rows.append(
      _evaluate_row(
        sample,
        result,
        root=validation.manifest.parent,
        wall_clock_ms=elapsed_ms,
      )
    )

  summary = _summary(rows, warmup_runs)
  failures = check_acceptance(summary, thresholds or AcceptanceThresholds())
  summary["acceptance"] = {
    "passed": not failures,
    "failures": list(failures),
    "thresholds": asdict(thresholds or AcceptanceThresholds()),
  }
  results_path = destination / "results.jsonl"
  results_path.write_text(
    "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
    encoding="utf-8",
  )
  (destination / "summary.json").write_text(
    json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
  )
  return EvaluationRun(tuple(rows), summary, failures)
