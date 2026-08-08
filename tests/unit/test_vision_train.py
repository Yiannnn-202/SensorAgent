"""Tests for the fixed-class segmentation training preflight."""

from __future__ import annotations

from pathlib import Path

import yaml

from scripts.vision_train import DatasetValidationError, main, validate_dataset


def _write_dataset(root: Path, *, label: str = "0 0.1 0.1 0.9 0.1 0.5 0.9") -> Path:
  for split in ("train", "val", "test"):
    image_dir = root / "images" / split
    label_dir = root / "labels" / split
    image_dir.mkdir(parents=True)
    label_dir.mkdir(parents=True)
    (image_dir / f"{split}.jpg").write_bytes(b"fixture")
    (label_dir / f"{split}.txt").write_text(label + "\n", encoding="utf-8")
  data = root / "dataset.yaml"
  data.write_text(
    yaml.safe_dump(
      {
        "path": ".",
        "train": "images/train",
        "val": "images/val",
        "test": "images/test",
        "names": {0: "roller", 1: "gear"},
      },
      sort_keys=False,
    ),
    encoding="utf-8",
  )
  return data


def test_validate_dataset_accepts_polygon_labels(tmp_path: Path) -> None:
  summary = validate_dataset(_write_dataset(tmp_path))

  assert summary.classes == ("roller", "gear")
  assert summary.splits["train"].images == 1
  assert summary.splits["train"].instances == 1


def test_validate_dataset_rejects_box_only_labels(tmp_path: Path) -> None:
  data = _write_dataset(tmp_path, label="0 0.5 0.5 0.2 0.2")

  try:
    validate_dataset(data)
  except DatasetValidationError as exc:
    assert "segmentation label" in str(exc)
  else:
    raise AssertionError("box-only labels must not pass segmentation preflight")


def test_validate_dataset_rejects_degenerate_polygons(tmp_path: Path) -> None:
  data = _write_dataset(tmp_path, label="0 0.1 0.1 0.2 0.2 0.3 0.3")

  try:
    validate_dataset(data)
  except DatasetValidationError as exc:
    assert "zero area" in str(exc)
  else:
    raise AssertionError("degenerate polygons must not pass segmentation preflight")


def test_validate_dataset_rejects_split_leakage(tmp_path: Path) -> None:
  data = _write_dataset(tmp_path)
  payload = yaml.safe_load(data.read_text(encoding="utf-8"))
  payload["val"] = "images/train"
  data.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

  try:
    validate_dataset(data)
  except DatasetValidationError as exc:
    assert "dataset leakage" in str(exc)
  else:
    raise AssertionError("the same image must not appear in train and val")


def test_dry_run_validates_without_loading_ultralytics(tmp_path: Path) -> None:
  data = _write_dataset(tmp_path)

  assert main(["--data", str(data), "--dry-run"]) == 0
