"""Tests for the reviewed COCO to Grounding DINO manifest conversion."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.vision_coco_to_grounding_dino import convert_coco


def test_convert_coco_maps_categories_and_boxes(tmp_path: Path) -> None:
  image_root = tmp_path / "images"
  image_root.mkdir()
  (image_root / "scene.png").write_bytes(b"image")
  annotations = tmp_path / "instances.json"
  annotations.write_text(
    json.dumps(
      {
        "images": [{"id": 1, "file_name": "scene.png", "width": 100, "height": 80}],
        "categories": [
          {"id": 1, "name": "gear"},
          {"id": 2, "name": "bearing"},
        ],
        "annotations": [
          {"id": 1, "image_id": 1, "category_id": 1, "bbox": [10, 20, 30, 40]},
          {"id": 2, "image_id": 1, "category_id": 2, "bbox": [1, 1, 5, 5]},
        ],
      }
    ),
    encoding="utf-8",
  )
  mapping = tmp_path / "mapping.yaml"
  mapping.write_text(
    "classes:\n  - gear\ncategory_map:\n  gear: gear\n  bearing: null\n",
    encoding="utf-8",
  )
  output = tmp_path / "manifest.jsonl"

  result = convert_coco(
    annotations,
    image_root,
    output,
    mapping,
    split="train",
    scene_prefix="public_mechanical",
    source_url="https://example.invalid/dataset",
    source_license="CC BY 4.0",
    include_negative=False,
  )

  row = json.loads(output.read_text(encoding="utf-8"))
  assert result["objects_written"] == 1
  assert row["objects"][0]["class_name"] == "gear"
  assert row["objects"][0]["bbox_xyxy"] == [10.0, 20.0, 40.0, 60.0]
  assert row["source"]["license"] == "CC BY 4.0"
