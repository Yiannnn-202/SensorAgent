"""Tests for scene-isolated vision dataset auditing."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.vision_dataset_audit import main


def _row(
  sample_id: str,
  scene_id: str,
  image: str,
  *,
  split: str | None = None,
  objects: object | None = None,
  source: dict[str, str] | None = None,
) -> dict[str, object]:
  row: dict[str, object] = {
    "sample_id": sample_id,
    "scene_id": scene_id,
    "image": image,
    "objects": (
      [{"class_name": "gear", "bbox_xyxy": [1, 1, 9, 9]}]
      if objects is None
      else objects
    ),
    "source": source or {"kind": "simulation"},
  }
  if split is not None:
    row["split"] = split
  return row


def _write_manifest(path: Path, rows: list[dict[str, object]]) -> None:
  path.write_text(
    "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
    encoding="utf-8",
  )


def test_assign_splits_keeps_minimum_three_scenes_non_empty(tmp_path: Path) -> None:
  rows = []
  for index, scene_id in enumerate(("scene-c", "scene-a", "scene-b"), start=1):
    image = f"image-{index}.jpg"
    (tmp_path / image).write_bytes(f"image-{index}".encode())
    rows.append(_row(f"sample-{index}", scene_id, image))
  manifest = tmp_path / "manifest.jsonl"
  output_dir = tmp_path / "audited"
  _write_manifest(manifest, rows)

  exit_code = main(
    [
      "--manifest",
      str(manifest),
      "--output-dir",
      str(output_dir),
      "--classes",
      "gear",
      "--assign-splits",
      "--require-all-splits",
    ]
  )

  report = json.loads((output_dir / "audit.json").read_text(encoding="utf-8"))
  assigned = [
    json.loads(line)
    for line in (output_dir / "all.jsonl").read_text(encoding="utf-8").splitlines()
  ]
  assert exit_code == 0
  assert report["valid"] is True
  assert {row["split"] for row in assigned} == {"train", "val", "test"}
  assert {split: report["splits"][split]["scenes"] for split in ("train", "val", "test")} == {
    "train": 1,
    "val": 1,
    "test": 1,
  }


def test_audit_reports_scene_leakage_and_duplicate_image_content(tmp_path: Path) -> None:
  (tmp_path / "first.jpg").write_bytes(b"same-image")
  (tmp_path / "second.jpg").write_bytes(b"same-image")
  manifest = tmp_path / "manifest.jsonl"
  output_dir = tmp_path / "audited"
  _write_manifest(
    manifest,
    [
      _row("sample-1", "scene-1", "first.jpg", split="train"),
      _row("sample-2", "scene-1", "second.jpg", split="test"),
    ],
  )

  exit_code = main(
    ["--manifest", str(manifest), "--output-dir", str(output_dir), "--classes", "gear"]
  )

  report = json.loads((output_dir / "audit.json").read_text(encoding="utf-8"))
  codes = {issue["code"] for issue in report["issues"]}
  assert exit_code == 2
  assert "SCENE_SPLIT_LEAKAGE" in codes
  assert "DUPLICATE_IMAGE_CONTENT" in codes


def test_audit_rejects_invalid_object_without_crashing(tmp_path: Path) -> None:
  (tmp_path / "image.jpg").write_bytes(b"image")
  manifest = tmp_path / "manifest.jsonl"
  output_dir = tmp_path / "audited"
  _write_manifest(
    manifest,
    [_row("sample-1", "scene-1", "image.jpg", split="train", objects=["bad-object"])],
  )

  exit_code = main(["--manifest", str(manifest), "--output-dir", str(output_dir)])

  report = json.loads((output_dir / "audit.json").read_text(encoding="utf-8"))
  assert exit_code == 2
  assert any(issue["code"] == "INVALID_OBJECT" for issue in report["issues"])


def test_audit_requires_public_url_and_license(tmp_path: Path) -> None:
  (tmp_path / "image.jpg").write_bytes(b"image")
  manifest = tmp_path / "manifest.jsonl"
  output_dir = tmp_path / "audited"
  _write_manifest(
    manifest,
    [
      _row(
        "sample-1",
        "scene-1",
        "image.jpg",
        split="train",
        source={"kind": "public"},
      )
    ],
  )

  exit_code = main(["--manifest", str(manifest), "--output-dir", str(output_dir)])

  report = json.loads((output_dir / "audit.json").read_text(encoding="utf-8"))
  provenance_issues = [
    issue for issue in report["issues"] if issue["code"] == "MISSING_PUBLIC_PROVENANCE"
  ]
  assert exit_code == 2
  assert len(provenance_issues) == 2


def test_audit_returns_structured_failure_for_invalid_json(
  tmp_path: Path,
  capsys,
) -> None:
  manifest = tmp_path / "manifest.jsonl"
  manifest.write_text('{"sample_id":\n', encoding="utf-8")

  exit_code = main(
    ["--manifest", str(manifest), "--output-dir", str(tmp_path / "audited")]
  )

  payload = json.loads(capsys.readouterr().out)
  assert exit_code == 2
  assert payload["issues"] == [
    {
      "code": "INVALID_JSON",
      "message": "line 1: Expecting value",
      "line": 1,
    }
  ]
