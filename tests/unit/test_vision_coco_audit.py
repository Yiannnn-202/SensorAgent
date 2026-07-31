"""Tests for explicit COCO missing-image auditing and cleaning."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.vision_coco_audit import audit_coco


def test_audit_coco_writes_traceable_clean_copy(tmp_path: Path) -> None:
  image_root = tmp_path / "images"
  image_root.mkdir()
  (image_root / "present.jpg").write_bytes(b"image")
  annotations = tmp_path / "instances.json"
  annotations.write_text(
    json.dumps(
      {
        "images": [
          {"id": 1, "file_name": "present.jpg", "width": 10, "height": 10},
          {"id": 2, "file_name": "missing.jpg", "width": 10, "height": 10},
        ],
        "categories": [{"id": 1, "name": "gear"}],
        "annotations": [
          {"id": 1, "image_id": 1, "category_id": 1, "bbox": [1, 1, 5, 5]},
          {"id": 2, "image_id": 2, "category_id": 1, "bbox": [2, 2, 4, 4]},
        ],
      }
    ),
    encoding="utf-8",
  )
  clean_output = tmp_path / "instances.cleaned.json"
  report_output = tmp_path / "audit.json"

  report = audit_coco(
    annotations,
    image_root,
    clean_output=clean_output,
    report_output=report_output,
  )

  cleaned = json.loads(clean_output.read_text(encoding="utf-8"))
  saved_report = json.loads(report_output.read_text(encoding="utf-8"))
  assert report["valid"] is False
  assert report["missing_images"] == [
    {"id": 2, "file_name": "missing.jpg", "annotation_count": 1}
  ]
  assert report["removed_annotation_count"] == 1
  assert [image["id"] for image in cleaned["images"]] == [1]
  assert [annotation["image_id"] for annotation in cleaned["annotations"]] == [1]
  assert saved_report["clean_output_sha256"] == report["clean_output_sha256"]
