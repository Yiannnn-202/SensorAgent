"""Audit a vision JSONL manifest and emit scene-isolated split manifests.

The input uses the training contract consumed by
``scripts/vision_train_grounding_dino.py``: ``image``, ``scene_id``,
``objects`` and provenance. Existing ``split`` values are audited as-is. If
rows do not have a split, ``--assign-splits`` creates a deterministic split at
the scene level. The original manifest is never modified.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
  sys.path.insert(0, str(SRC))

SPLITS = ("train", "val", "test")


def _sha256(path: Path) -> str:
  digest = hashlib.sha256()
  with path.open("rb") as stream:
    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
      digest.update(chunk)
  return digest.hexdigest()


def _classes(rows: list[dict[str, Any]]) -> list[str]:
  names = {
    str(target["class_name"])
    for row in rows
    for target in (row.get("objects") or [])
    if isinstance(target, dict) and isinstance(target.get("class_name"), str)
  }
  return sorted(names)


def _assign_scene_splits(
  rows: list[dict[str, Any]],
  ratios: tuple[float, float, float],
) -> None:
  """Assign all rows in a scene to one split using stable scene ordering."""

  scenes = sorted({str(row["scene_id"]) for row in rows})
  total = len(scenes)
  if total < 3:
    raise ValueError("--assign-splits requires at least 3 distinct scene_id values")
  train_count = max(1, min(total - 2, int(round(total * ratios[0]))))
  remaining = total - train_count
  val_count = max(1, min(remaining - 1, int(round(total * ratios[1]))))
  boundaries = (train_count, train_count + val_count)
  scene_split = {
    scene: ("train" if index < boundaries[0] else "val" if index < boundaries[1] else "test")
    for index, scene in enumerate(scenes)
  }
  for row in rows:
    row["split"] = scene_split[str(row["scene_id"])]


def _audit_rows(
  rows: list[dict[str, Any]],
  manifest: Path,
  classes: list[str],
  *,
  check_files: bool,
) -> dict[str, Any]:
  issues: list[dict[str, Any]] = []
  seen_ids: dict[str, int] = {}
  seen_images: dict[str, str] = {}
  image_hashes: dict[str, str] = {}
  scene_splits: dict[str, str] = {}
  split_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
  root = manifest.parent

  def issue(code: str, message: str, row_index: int | None = None) -> None:
    item: dict[str, Any] = {"code": code, "message": message}
    if row_index is not None:
      item["line"] = row_index + 1
    issues.append(item)

  for index, row in enumerate(rows):
    sample_id = row.get("sample_id")
    scene_id = row.get("scene_id")
    image = row.get("image")
    split = row.get("split")
    if not isinstance(sample_id, str) or not sample_id.strip():
      issue("MISSING_SAMPLE_ID", "sample_id must be a non-empty string", index)
    elif sample_id in seen_ids:
      issue("DUPLICATE_SAMPLE_ID", f"sample_id repeats line {seen_ids[sample_id]}", index)
    else:
      seen_ids[sample_id] = index + 1
    if not isinstance(scene_id, str) or not scene_id.strip():
      issue("MISSING_SCENE_ID", "scene_id must be a non-empty string", index)
    if split not in SPLITS:
      issue("INVALID_SPLIT", f"split must be one of {list(SPLITS)}", index)
    if not isinstance(image, str) or not image.strip():
      issue("MISSING_IMAGE", "image must be a relative path", index)
      image_path = None
    else:
      image_path = (root / image).resolve()
      if Path(image).is_absolute():
        issue("ABSOLUTE_IMAGE_PATH", "image must be relative to the manifest", index)
      if check_files and not image_path.is_file():
        issue("MISSING_IMAGE_FILE", f"image does not exist: {image}", index)
      key = str(image_path).casefold()
      if key in seen_images and seen_images[key] != sample_id:
        issue("DUPLICATE_IMAGE_PATH", f"image repeats sample {seen_images[key]}", index)
      else:
        seen_images[key] = str(sample_id)
      if check_files and image_path.is_file():
        digest = _sha256(image_path)
        if digest in image_hashes and image_hashes[digest] != sample_id:
          issue("DUPLICATE_IMAGE_CONTENT", f"image bytes repeat sample {image_hashes[digest]}", index)
        else:
          image_hashes[digest] = str(sample_id)
    if isinstance(scene_id, str) and split in SPLITS:
      previous = scene_splits.setdefault(scene_id, str(split))
      if previous != split:
        issue("SCENE_SPLIT_LEAKAGE", f"scene {scene_id!r} appears in {previous} and {split}", index)
    if split in SPLITS:
      split_rows[str(split)].append(row)
    objects = row.get("objects")
    if not isinstance(objects, list):
      issue("INVALID_OBJECTS", "objects must be a list; use [] for a negative sample", index)
      continue
    for target in objects:
      if not isinstance(target, dict) or not isinstance(target.get("class_name"), str):
        issue("INVALID_OBJECT", "each object needs a class_name", index)
        continue
      elif classes and target["class_name"] not in classes:
        issue("UNKNOWN_CLASS", f"class {target['class_name']!r} is not in the agreed class list", index)
      box = target.get("bbox_xyxy")
      if not (
        isinstance(box, list)
        and len(box) == 4
        and all(isinstance(value, (int, float)) for value in box)
        and box[0] >= 0
        and box[1] >= 0
        and box[2] > box[0]
        and box[3] > box[1]
      ):
        issue("MISSING_BBOX", "each object needs bbox_xyxy for Grounding DINO training", index)
      mask = target.get("mask")
      if mask is not None:
        if not isinstance(mask, str) or Path(mask).is_absolute():
          issue("INVALID_MASK_PATH", "mask must be a relative path", index)
        elif check_files and not (root / mask).resolve().is_file():
          issue("MISSING_MASK_FILE", f"mask does not exist: {mask}", index)
    source = row.get("source")
    if not isinstance(source, dict) or not isinstance(source.get("kind"), str) or not source["kind"].strip():
      issue("MISSING_SOURCE", "source.kind is required", index)
    elif source["kind"] == "public":
      for field in ("url", "license"):
        if not isinstance(source.get(field), str) or not source[field].strip():
          issue("MISSING_PUBLIC_PROVENANCE", f"public data requires source.{field}", index)

  summaries: dict[str, Any] = {}
  for split in SPLITS:
    selected = split_rows.get(split, [])
    counts = Counter(
      str(target["class_name"])
      for row in selected
      for target in (row.get("objects") or [])
      if isinstance(target, dict) and isinstance(target.get("class_name"), str)
    )
    summaries[split] = {
      "samples": len(selected),
      "scenes": len({row.get("scene_id") for row in selected}),
      "negative_samples": sum(not row.get("objects") for row in selected),
      "instances": sum(len(row.get("objects") or []) for row in selected),
      "class_instances": {name: counts.get(name, 0) for name in classes or sorted(counts)},
    }
    if split in ("train", "val"):
      missing = [name for name in classes if counts.get(name, 0) == 0]
      if missing:
        issue("MISSING_CLASS_IN_SPLIT", f"{split} has no objects for: {', '.join(missing)}")
  return {
    "manifest": manifest.as_posix(),
    "valid": not issues,
    "sample_count": len(rows),
    "scene_count": len({row.get("scene_id") for row in rows}),
    "classes": classes or _classes(rows),
    "splits": summaries,
    "issues": issues,
  }


def _parser() -> argparse.ArgumentParser:
  parser = argparse.ArgumentParser(description="Audit vision JSONL data and write scene-isolated manifests.")
  parser.add_argument("--manifest", type=Path, required=True)
  parser.add_argument("--output-dir", type=Path, required=True)
  parser.add_argument("--classes", nargs="*", default=None, help="Agreed class names in prompt order.")
  parser.add_argument("--assign-splits", action="store_true", help="Assign train/val/test by sorted scene_id.")
  parser.add_argument("--require-all-splits", action="store_true", help="Require non-empty train, val and test splits.")
  parser.add_argument("--train-ratio", type=float, default=0.7)
  parser.add_argument("--val-ratio", type=float, default=0.15)
  parser.add_argument("--allow-missing-files", action="store_true")
  parser.add_argument("--report", type=Path, default=None)
  return parser


def main(argv: list[str] | None = None) -> int:
  args = _parser().parse_args(argv)
  manifest = args.manifest.resolve()
  if not manifest.is_file():
    print(json.dumps({"valid": False, "issues": [{"code": "MISSING_MANIFEST"}]}, ensure_ascii=False, indent=2))
    return 2
  rows: list[dict[str, Any]] = []
  for line_number, line in enumerate(manifest.read_text(encoding="utf-8").splitlines(), start=1):
    if not line.strip():
      continue
    try:
      row = json.loads(line)
    except json.JSONDecodeError as exc:
      print(
        json.dumps(
          {
            "valid": False,
            "manifest": manifest.as_posix(),
            "issues": [
              {
                "code": "INVALID_JSON",
                "message": f"line {line_number}: {exc.msg}",
                "line": line_number,
              }
            ],
          },
          ensure_ascii=False,
          indent=2,
        )
      )
      return 2
    if not isinstance(row, dict):
      print(
        json.dumps(
          {
            "valid": False,
            "manifest": manifest.as_posix(),
            "issues": [
              {
                "code": "INVALID_ROW",
                "message": "manifest rows must be JSON objects",
                "line": line_number,
              }
            ],
          },
          ensure_ascii=False,
          indent=2,
        )
      )
      return 2
    rows.append(row)
  if args.assign_splits:
    if not 0 < args.train_ratio < 1 or not 0 < args.val_ratio < 1 or args.train_ratio + args.val_ratio >= 1:
      print("train/val ratios must be positive and leave room for test", file=sys.stderr)
      return 2
    _assign_scene_splits(rows, (args.train_ratio, args.val_ratio, 1 - args.train_ratio - args.val_ratio))
  classes = list(args.classes or _classes(rows))
  report = _audit_rows(rows, manifest, classes, check_files=not args.allow_missing_files)
  if args.require_all_splits:
    missing = [split for split in SPLITS if not any(row.get("split") == split for row in rows)]
    for split in missing:
      report["issues"].append({"code": "MISSING_SPLIT", "message": f"manifest has no {split} samples"})
    for split in ("test",):
      counts = report["splits"][split]["class_instances"]
      missing_classes = [name for name in classes if counts.get(name, 0) == 0]
      if missing_classes:
        report["issues"].append(
          {
            "code": "MISSING_CLASS_IN_SPLIT",
            "message": f"{split} has no objects for: {', '.join(missing_classes)}",
          }
        )
    report["valid"] = not report["issues"]
  output_dir = args.output_dir.resolve()
  output_dir.mkdir(parents=True, exist_ok=True)
  (output_dir / "all.jsonl").write_text(
    "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8"
  )
  for split in SPLITS:
    selected = [row for row in rows if row.get("split") == split]
    if selected:
      (output_dir / f"{split}.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in selected), encoding="utf-8"
      )
  report_path = (args.report or output_dir / "audit.json").resolve()
  report_path.parent.mkdir(parents=True, exist_ok=True)
  report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
  print(json.dumps(report, ensure_ascii=False, indent=2))
  return 0 if report["valid"] else 2


if __name__ == "__main__":
  raise SystemExit(main())
