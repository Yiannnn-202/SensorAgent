"""Tests for Grounding DINO training data validation and dry-run behavior."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from scripts.vision_train_grounding_dino import (
  GroundingDinoDatasetError,
  _coco_target,
  main,
  validate_manifest,
)


CLASSES = ("roller", "gear")


def _row(sample_id: str, split: str, class_name: str, *, scene_id: str | None = None) -> dict:
  return {
    "sample_id": sample_id,
    "scene_id": scene_id or f"scene_{sample_id}",
    "split": split,
    "image": f"images/{sample_id}.png",
    "objects": [{"class_name": class_name, "bbox_xyxy": [1, 2, 11, 22]}],
    "source": {"kind": "owned", "capture_session": f"capture_{sample_id}"},
  }


def _write_manifest(root: Path, rows: list[dict] | None = None) -> Path:
  rows = rows or [
    _row("train_roller", "train", "roller"),
    _row("train_gear", "train", "gear"),
    _row("val_roller", "val", "roller"),
    _row("val_gear", "val", "gear"),
  ]
  image_dir = root / "images"
  image_dir.mkdir()
  for row in rows:
    image_path = root / row["image"]
    image_path.parent.mkdir(parents=True, exist_ok=True)
    image_path.write_bytes(row["sample_id"].encode("utf-8"))
  manifest = root / "training.jsonl"
  manifest.write_text(
    "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
    encoding="utf-8",
  )
  return manifest


def _write_config(root: Path, manifest: Path) -> Path:
  config = root / "training.yaml"
  config.write_text(
    yaml.safe_dump(
      {
        "model": "IDEA-Research/grounding-dino-tiny",
        "manifest": str(manifest),
        "classes": list(CLASSES),
        "training": {"device": "cpu", "amp": False},
      },
      sort_keys=False,
    ),
    encoding="utf-8",
  )
  return config


def test_validate_manifest_preserves_prompt_class_order(tmp_path: Path) -> None:
  summary, samples = validate_manifest(_write_manifest(tmp_path), CLASSES)

  assert summary.classes == CLASSES
  assert summary.splits["train"].class_instances == {"roller": 1, "gear": 1}
  target = _coco_target(samples[1], image_id=7)
  assert target["annotations"][0]["category_id"] == 1
  assert target["annotations"][0]["bbox"] == [1.0, 2.0, 10.0, 20.0]


def test_validate_manifest_accepts_negative_samples(tmp_path: Path) -> None:
  rows = [
    _row("train_roller", "train", "roller"),
    _row("train_gear", "train", "gear"),
    _row("val_roller", "val", "roller"),
    _row("val_gear", "val", "gear"),
    {
      "sample_id": "train_negative",
      "scene_id": "scene_negative",
      "split": "train",
      "image": "images/train_negative.png",
      "objects": [],
      "source": {"kind": "owned"},
    },
  ]

  summary, _ = validate_manifest(_write_manifest(tmp_path, rows), CLASSES)

  assert summary.splits["train"].negative_samples == 1


def test_validate_manifest_rejects_scene_leakage(tmp_path: Path) -> None:
  rows = [
    _row("train_roller", "train", "roller", scene_id="shared"),
    _row("train_gear", "train", "gear"),
    _row("val_roller", "val", "roller", scene_id="shared"),
    _row("val_gear", "val", "gear"),
  ]

  try:
    validate_manifest(_write_manifest(tmp_path, rows), CLASSES)
  except GroundingDinoDatasetError as exc:
    assert "scene leakage" in str(exc)
  else:
    raise AssertionError("one scene must not cross train and validation splits")


def test_validate_manifest_rejects_duplicate_image_content(tmp_path: Path) -> None:
  manifest = _write_manifest(tmp_path)
  rows = [json.loads(line) for line in manifest.read_text(encoding="utf-8").splitlines()]
  duplicate_path = tmp_path / rows[-1]["image"]
  duplicate_path.write_bytes((tmp_path / rows[0]["image"]).read_bytes())

  try:
    validate_manifest(manifest, CLASSES)
  except GroundingDinoDatasetError as exc:
    assert "image content is duplicated" in str(exc)
  else:
    raise AssertionError("renamed copies must not cross dataset splits")


def test_validate_manifest_rejects_unknown_class(tmp_path: Path) -> None:
  rows = [
    _row("train_roller", "train", "roller"),
    _row("train_unknown", "train", "flange"),
    _row("val_roller", "val", "roller"),
    _row("val_gear", "val", "gear"),
  ]

  try:
    validate_manifest(_write_manifest(tmp_path, rows), CLASSES)
  except GroundingDinoDatasetError as exc:
    assert "prompt classes" in str(exc)
  else:
    raise AssertionError("labels outside the text prompt must be rejected")


def test_validate_manifest_rejects_invalid_box(tmp_path: Path) -> None:
  rows = [
    _row("train_roller", "train", "roller"),
    _row("train_gear", "train", "gear"),
    _row("val_roller", "val", "roller"),
    _row("val_gear", "val", "gear"),
  ]
  rows[0]["objects"][0]["bbox_xyxy"] = [10, 10, 5, 20]

  try:
    validate_manifest(_write_manifest(tmp_path, rows), CLASSES)
  except GroundingDinoDatasetError as exc:
    assert "positive width" in str(exc)
  else:
    raise AssertionError("inverted boxes must be rejected")


def test_public_data_requires_url_and_license(tmp_path: Path) -> None:
  rows = [
    _row("train_roller", "train", "roller"),
    _row("train_gear", "train", "gear"),
    _row("val_roller", "val", "roller"),
    _row("val_gear", "val", "gear"),
  ]
  rows[0]["source"] = {"kind": "public"}

  try:
    validate_manifest(_write_manifest(tmp_path, rows), CLASSES)
  except GroundingDinoDatasetError as exc:
    assert "source.url" in str(exc)
  else:
    raise AssertionError("public data provenance must be recorded")


def test_dry_run_does_not_import_or_download_model(tmp_path: Path) -> None:
  manifest = _write_manifest(tmp_path)
  config = _write_config(tmp_path, manifest)

  assert main(["--config", str(config), "--dry-run"]) == 0
