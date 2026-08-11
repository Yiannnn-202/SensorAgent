"""Tests for vision dataset validation and aggregate evaluation metrics."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sensoragent.evaluation.vision import (
  AcceptanceThresholds,
  box_iou,
  check_acceptance,
  evaluate_manifest,
  validate_manifest,
)
from sensoragent.tools.vision.open_vocab import (
  GroundingDinoBackend,
  VisionDetection,
  VisionInferenceOptions,
)


def _write_jsonl(path: Path, rows: list[dict]) -> None:
  path.write_text(
    "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
    encoding="utf-8",
  )


def _sample(
  sample_id: str,
  *,
  scene_id: str | None = None,
  split: str = "test",
  query: str = "wrench",
  image: str | None = None,
  expected: dict | None = None,
) -> dict:
  return {
    "sample_id": sample_id,
    "scene_id": scene_id or f"scene_{sample_id}",
    "split": split,
    "query": query,
    "image": image or f"{sample_id}.jpg",
    "expected": expected or {"found": True, "bbox_2d": [0, 0, 10, 10]},
    "source": {"kind": "owned", "capture_session": "session_001"},
  }


def test_validate_manifest_accepts_relative_complete_sample(tmp_path: Path) -> None:
  (tmp_path / "sample.jpg").write_bytes(b"fixture")
  manifest = tmp_path / "dataset.jsonl"
  _write_jsonl(manifest, [_sample("sample")])

  validation = validate_manifest(manifest)

  assert validation.valid
  assert validation.to_dict()["sample_count"] == 1
  assert validation.issues == ()


def test_validate_manifest_reports_duplicates_and_scene_leakage(tmp_path: Path) -> None:
  (tmp_path / "same.jpg").write_bytes(b"fixture")
  manifest = tmp_path / "dataset.jsonl"
  _write_jsonl(
    manifest,
    [
      _sample("same", scene_id="shared", split="train"),
      _sample("same", scene_id="shared", split="test"),
    ],
  )

  validation = validate_manifest(manifest)
  codes = {issue.code for issue in validation.issues}

  assert not validation.valid
  assert "DUPLICATE_SAMPLE_ID" in codes
  assert "SCENE_SPLIT_LEAKAGE" in codes


def test_validate_manifest_rejects_absolute_path_and_unlicensed_public_data(
  tmp_path: Path,
) -> None:
  manifest = tmp_path / "dataset.jsonl"
  sample = _sample("public", image=str((tmp_path / "public.jpg").resolve()))
  sample["source"] = {"kind": "public"}
  _write_jsonl(manifest, [sample])

  validation = validate_manifest(manifest)
  codes = [issue.code for issue in validation.issues]

  assert "ABSOLUTE_PATH" in codes
  assert codes.count("MISSING_PUBLIC_LICENSE") == 2


def test_validate_manifest_can_check_template_without_local_files(
  tmp_path: Path,
) -> None:
  manifest = tmp_path / "dataset.jsonl"
  _write_jsonl(manifest, [_sample("future")])

  validation = validate_manifest(manifest, check_files=False)

  assert validation.valid


def test_validate_manifest_checks_bbox_order(tmp_path: Path) -> None:
  (tmp_path / "bad.jpg").write_bytes(b"fixture")
  manifest = tmp_path / "dataset.jsonl"
  sample = _sample("bad", expected={"found": True, "bbox_2d": [10, 0, 2, 4]})
  _write_jsonl(manifest, [sample])

  validation = validate_manifest(manifest)

  assert any(issue.code == "INVALID_BBOX" for issue in validation.issues)


def test_box_iou_uses_xyxy_coordinates() -> None:
  assert box_iou([0, 0, 10, 10], [5, 0, 15, 10]) == pytest.approx(1 / 3)
  assert box_iou([0, 0, 2, 2], [3, 3, 4, 4]) == 0.0


def test_grounding_dino_single_detect_forwards_optional_depth_path() -> None:
  backend = object.__new__(GroundingDinoBackend)
  received: dict[str, object] = {}

  def detect_all(**kwargs):
    received.update(kwargs)
    return [VisionDetection(found=True, label="wrench", confidence=0.9)]

  backend.detect_all = detect_all

  detection = backend.detect(
    query="wrench",
    image_path="scene.jpg",
    depth_path=None,
    options=VisionInferenceOptions(),
  )

  assert detection.found
  assert received["depth_path"] is None


def test_evaluate_manifest_writes_rows_and_summary(tmp_path: Path) -> None:
  for name in ("positive", "negative", "false_positive"):
    (tmp_path / f"{name}.jpg").write_bytes(b"fixture")
  manifest = tmp_path / "dataset.jsonl"
  _write_jsonl(
    manifest,
    [
      _sample("positive", expected={"found": True, "bbox_2d": [0, 0, 10, 10]}),
      _sample("negative", expected={"found": False}),
      _sample("false_positive", expected={"found": False}),
    ],
  )

  def runner(input_data: dict[str, object]) -> dict[str, object]:
    image_name = Path(str(input_data["image_path"])).stem
    if image_name == "negative":
      return {
        "tool": "vision.open_vocab_detect",
        "success": False,
        "output": {"found": False, "confidence": 0.0},
        "error": "OBJECT_NOT_FOUND",
      }
    bbox = [0, 0, 8, 10] if image_name == "positive" else [2, 2, 8, 8]
    return {
      "tool": "vision.open_vocab_detect",
      "success": True,
      "output": {
        "found": True,
        "confidence": 0.8,
        "bbox_2d": bbox,
        "center_px": [(bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2],
      },
      "error": None,
    }

  output_dir = tmp_path / "out"
  evaluation = evaluate_manifest(
    manifest,
    runner=runner,
    output_dir=output_dir,
    warmup_runs=1,
  )

  assert evaluation.passed
  assert evaluation.summary["confusion"] == {"tp": 1, "fp": 1, "tn": 1, "fn": 0}
  assert evaluation.summary["precision"] == 0.5
  assert evaluation.summary["recall"] == 1.0
  assert evaluation.summary["mean_box_iou"] == 0.8
  assert evaluation.summary["box_iou_sample_count"] == 1
  assert evaluation.summary["execution_error_count"] == 0
  assert (output_dir / "results.jsonl").is_file()
  assert (output_dir / "summary.json").is_file()
  assert len((output_dir / "results.jsonl").read_text(encoding="utf-8").splitlines()) == 3
  assert evaluation.summary["ap50"] == pytest.approx(1.0, abs=1e-6)
  assert evaluation.summary["map50_95"] == pytest.approx(0.7, abs=1e-6)


def test_evaluate_manifest_reports_ranked_ap_at_multiple_iou_thresholds(
  tmp_path: Path,
) -> None:
  for name in ("good", "borderline", "negative"):
    (tmp_path / f"{name}.jpg").write_bytes(b"fixture-" + name.encode())
  manifest = tmp_path / "dataset.jsonl"
  _write_jsonl(
    manifest,
    [
      _sample("good", query="gear", expected={"found": True, "bbox_2d": [0, 0, 10, 10]}),
      _sample(
        "borderline",
        query="gear",
        expected={"found": True, "bbox_2d": [0, 0, 10, 10]},
      ),
      _sample("negative", query="gear", expected={"found": False}),
    ],
  )

  predictions = {
    "good": ([0, 0, 10, 10], 0.95),
    "borderline": ([0, 0, 6, 10], 0.90),
    "negative": ([0, 0, 10, 10], 0.85),
  }

  def runner(input_data: dict[str, object]) -> dict[str, object]:
    bbox, confidence = predictions[Path(str(input_data["image_path"])).stem]
    return {"success": True, "output": {"found": True, "bbox_2d": bbox, "confidence": confidence}}

  evaluation = evaluate_manifest(manifest, runner=runner, output_dir=tmp_path / "out")

  assert evaluation.summary["ap50"] > evaluation.summary["ap75"]
  assert evaluation.summary["map50_95"] < evaluation.summary["ap50"]
  assert evaluation.summary["ap_protocol"]["name"] == "query_level_single_best_box"


def test_evaluate_manifest_reports_scene_aware_rejection_and_ambiguity_metrics(
  tmp_path: Path,
) -> None:
  (tmp_path / "sample.jpg").write_bytes(b"fixture")
  manifest = tmp_path / "dataset.jsonl"
  _write_jsonl(
    manifest,
    [_sample("sample", expected={"found": True, "bbox_2d": [2, 2, 8, 8]})],
  )

  def runner(input_data: dict[str, object]) -> dict[str, object]:
    assert input_data["candidate_policy"] == "scene_aware"
    assert input_data["scene_profile"] == {"name": "competition_tabletop_v1"}
    return {
      "success": True,
      "output": {
        "found": True,
        "confidence": 0.9,
        "bbox_2d": [2, 2, 8, 8],
        "candidate_policy": "scene_aware",
        "scene_score": 0.82,
        "ambiguity": {
          "is_ambiguous": False,
          "score_margin": 0.2,
          "required_margin": 0.03,
        },
        "timing_ms": {"scene_policy": 2.5},
        "candidates": [
          {
            "found": True,
            "confidence": 0.95,
            "bbox_2d": [90, 90, 100, 100],
            "rejection_reason": "outside_workspace_roi",
          }
        ],
      },
    }

  evaluation = evaluate_manifest(
    manifest,
    runner=runner,
    output_dir=tmp_path / "out",
    candidate_policy="scene_aware",
    scene_profile={"name": "competition_tabletop_v1"},
  )

  scene_summary = evaluation.summary["scene_aware"]
  assert scene_summary["sample_count"] == 1
  assert scene_summary["candidate_count"] == 2
  assert scene_summary["scene_rejection_rate"] == 0.5
  assert scene_summary["ambiguity_rate"] == 0.0
  assert scene_summary["policy_latency_ms"]["p50"] == 2.5


def test_scene_aware_ambiguity_is_a_measured_rejection_not_execution_error(
  tmp_path: Path,
) -> None:
  (tmp_path / "sample.jpg").write_bytes(b"fixture")
  manifest = tmp_path / "dataset.jsonl"
  _write_jsonl(manifest, [_sample("sample")])

  evaluation = evaluate_manifest(
    manifest,
    runner=lambda _: {
      "success": False,
      "output": {
        "found": False,
        "confidence": 0.0,
        "candidate_policy": "scene_aware",
        "ambiguity": {
          "is_ambiguous": True,
          "score_margin": 0.01,
          "required_margin": 0.03,
        },
        "timing_ms": {"scene_policy": 1.2},
        "candidates": [
          {"found": True, "confidence": 0.80, "scene_score": 0.70},
          {"found": True, "confidence": 0.79, "scene_score": 0.69},
        ],
      },
      "error": "OBJECT_AMBIGUOUS: two candidates are too close",
    },
    output_dir=tmp_path / "out",
  )

  assert evaluation.summary["execution_error_count"] == 0
  assert evaluation.summary["scene_aware"]["ambiguity_rate"] == 1.0
  assert evaluation.summary["scene_aware"]["candidate_count"] == 2


def test_evaluate_manifest_records_runner_failure(tmp_path: Path) -> None:
  (tmp_path / "sample.jpg").write_bytes(b"fixture")
  manifest = tmp_path / "dataset.jsonl"
  _write_jsonl(manifest, [_sample("sample")])

  def runner(input_data: dict[str, object]):
    del input_data
    raise RuntimeError("backend unavailable")

  evaluation = evaluate_manifest(
    manifest,
    runner=runner,
    output_dir=tmp_path / "out",
  )

  assert not evaluation.passed
  assert evaluation.summary["execution_error_count"] == 1
  assert "failed during model execution" in evaluation.failures[0]


def test_check_acceptance_fails_unavailable_or_out_of_range_metrics() -> None:
  summary = {
    "execution_error_count": 0,
    "precision": 0.8,
    "recall": 0.7,
    "mean_box_iou": None,
    "mean_mask_iou": 0.6,
    "mean_center_error_px": 12.0,
    "latency_ms": {"warm_p95": 900.0},
  }
  failures = check_acceptance(
    summary,
    AcceptanceThresholds(
      min_precision=0.9,
      min_recall=0.6,
      min_box_iou=0.5,
      min_mask_iou=0.5,
      min_map50_95=0.9,
      max_center_error_px=10.0,
      max_warm_p95_ms=800.0,
    ),
  )

  assert len(failures) == 5
  assert any("precision" in failure for failure in failures)
  assert any("mean_box_iou is unavailable" in failure for failure in failures)
  assert any("mean_center_error_px" in failure for failure in failures)
  assert any("warm_p95" in failure for failure in failures)
  assert any("map50_95" in failure for failure in failures)


def test_evaluate_mask_iou_from_polygon(tmp_path: Path) -> None:
  image_module = pytest.importorskip("PIL.Image")
  mask = image_module.new("L", (10, 10), 0)
  for y in range(2, 8):
    for x in range(2, 8):
      mask.putpixel((x, y), 255)
  mask.save(tmp_path / "mask.png")
  (tmp_path / "sample.jpg").write_bytes(b"fixture")
  manifest = tmp_path / "dataset.jsonl"
  sample = _sample(
    "sample",
    expected={"found": True, "mask": "mask.png", "bbox_2d": [2, 2, 7, 7]},
  )
  _write_jsonl(manifest, [sample])

  evaluation = evaluate_manifest(
    manifest,
    runner=lambda _: {
      "success": True,
      "output": {
        "found": True,
        "bbox_2d": [2, 2, 7, 7],
        "mask_polygons": [[[2, 2], [7, 2], [7, 7], [2, 7]]],
      },
    },
    output_dir=tmp_path / "out",
  )

  assert evaluation.summary["mask_iou_sample_count"] == 1
  assert evaluation.summary["mean_mask_iou"] == 1.0
