"""Tests for COCO-Segmentation truth-mask conversion."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from scripts.vision_coco_segmentation_to_eval import (
  CocoSegmentationConversionError,
  convert_coco_segmentation_export,
  decode_coco_segmentation,
)
from sensoragent.evaluation import validate_manifest


def _write_split(
  root: Path,
  directory: str,
  *,
  file_name: str,
  segmentation: object | None,
) -> None:
  image_module = pytest.importorskip("PIL.Image")
  destination = root / directory
  destination.mkdir(parents=True)
  image_module.new("RGB", (3, 2), (255, 0, 0)).save(destination / file_name)
  annotations = []
  if segmentation is not None:
    annotations.append(
      {
        "id": 1,
        "image_id": 1,
        "category_id": 1,
        "bbox": [1, 0, 1, 2],
        "area": 2,
        "segmentation": segmentation,
        "iscrowd": 0,
      }
    )
  payload = {
    "images": [{"id": 1, "file_name": file_name, "width": 3, "height": 2}],
    "categories": [
      {"id": 0, "name": "red-block"},
      {"id": 1, "name": "red-block"},
    ],
    "annotations": annotations,
  }
  (destination / "_annotations.coco.json").write_text(
    json.dumps(payload), encoding="utf-8"
  )


def _convert(source: Path, output: Path):
  return convert_coco_segmentation_export(
    source,
    output,
    sample_prefix="red_block_v2",
    query="red block",
    category_name="red-block",
    dataset_name="red block v2",
    source_url="https://universe.roboflow.com/example/red-block",
    source_license="CC BY 4.0",
  )


def test_decode_compressed_coco_rle_uses_column_major_order() -> None:
  mask = decode_coco_segmentation(
    {"counts": "222", "size": [2, 3]},
    height=2,
    width=3,
  )

  assert np.array_equal(
    mask,
    np.asarray([[False, True, False], [False, True, False]]),
  )


def test_convert_export_keeps_masks_negatives_and_duplicate_category_warning(
  tmp_path: Path,
) -> None:
  source = tmp_path / "source"
  _write_split(
    source,
    "train",
    file_name="train_png.rf.111.jpg",
    segmentation={"counts": "222", "size": [2, 3]},
  )
  _write_split(
    source,
    "valid",
    file_name="valid_png.rf.222.jpg",
    segmentation=None,
  )
  _write_split(
    source,
    "test",
    file_name="test_png.rf.333.jpg",
    segmentation={"counts": "222", "size": [2, 3]},
  )
  output = tmp_path / "output"

  report = _convert(source, output)

  assert report["image_count"] == 3
  assert report["positive_count"] == 2
  assert report["negative_count"] == 1
  assert len(report["warnings"]) == 3
  assert report["splits"]["train"]["unused_category_ids"] == [0]
  assert (output / "masks" / "train" / "red_block_v2_train_1.png").is_file()
  assert validate_manifest(output / "manifest_all.jsonl").valid
  val_row = json.loads((output / "manifest_val.jsonl").read_text(encoding="utf-8"))
  assert val_row["split"] == "val"
  assert val_row["expected"] == {"found": False}


def test_convert_export_rejects_source_scene_leakage(tmp_path: Path) -> None:
  source = tmp_path / "source"
  for directory, suffix in (("train", "111"), ("valid", "222"), ("test", "333")):
    _write_split(
      source,
      directory,
      file_name=f"same_scene_png.rf.{suffix}.jpg",
      segmentation=None,
    )

  with pytest.raises(CocoSegmentationConversionError, match="leakage"):
    _convert(source, tmp_path / "output")
