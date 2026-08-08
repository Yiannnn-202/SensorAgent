"""Audit a COCO export and write an explicit cleaned copy when images are missing."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


class CocoAuditError(ValueError):
  """Raised when a COCO export cannot be audited safely."""


def _sha256(path: Path) -> str:
  digest = hashlib.sha256()
  with path.open("rb") as stream:
    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
      digest.update(chunk)
  return digest.hexdigest()


def audit_coco(
  annotations_path: Path,
  image_root: Path,
  *,
  clean_output: Path | None = None,
  report_output: Path | None = None,
) -> dict[str, Any]:
  """Audit image references and optionally remove only confirmed missing-image rows."""

  if not annotations_path.is_file():
    raise CocoAuditError(f"COCO annotations do not exist: {annotations_path}")
  if not image_root.is_dir():
    raise CocoAuditError(f"COCO image root does not exist: {image_root}")
  try:
    payload = json.loads(annotations_path.read_text(encoding="utf-8"))
  except json.JSONDecodeError as exc:
    raise CocoAuditError(f"COCO annotations are invalid JSON: {exc.msg}") from exc
  if not isinstance(payload, dict):
    raise CocoAuditError("COCO annotations must contain a JSON object")
  images = payload.get("images")
  annotations = payload.get("annotations")
  if not isinstance(images, list) or not isinstance(annotations, list):
    raise CocoAuditError("COCO annotations must contain images and annotations lists")

  image_ids: set[int] = set()
  missing_images: list[dict[str, Any]] = []
  for image in images:
    if not isinstance(image, dict) or not isinstance(image.get("id"), int):
      raise CocoAuditError("each COCO image must have an integer id")
    image_id = image["id"]
    if image_id in image_ids:
      raise CocoAuditError(f"duplicate COCO image id: {image_id}")
    image_ids.add(image_id)
    file_name = image.get("file_name")
    if not isinstance(file_name, str) or not file_name.strip():
      raise CocoAuditError(f"COCO image {image_id} has no file_name")
    if not (image_root / file_name).is_file():
      missing_images.append({"id": image_id, "file_name": file_name})

  orphan_annotation_ids: set[int] = set()
  annotation_counts: dict[int, int] = {}
  for annotation in annotations:
    if not isinstance(annotation, dict) or not isinstance(annotation.get("image_id"), int):
      raise CocoAuditError("each COCO annotation must have an integer image_id")
    image_id = annotation["image_id"]
    annotation_counts[image_id] = annotation_counts.get(image_id, 0) + 1
    if image_id not in image_ids:
      orphan_annotation_ids.add(image_id)

  for image in missing_images:
    image["annotation_count"] = annotation_counts.get(image["id"], 0)
  missing_ids = {image["id"] for image in missing_images}
  removed_annotation_count = sum(annotation_counts.get(image_id, 0) for image_id in missing_ids)

  actual_files = {
    path.name
    for path in image_root.iterdir()
    if path.is_file() and path.suffix.casefold() in {".jpg", ".jpeg", ".png"}
  }
  declared_files = {
    str(image["file_name"])
    for image in images
    if isinstance(image, dict) and isinstance(image.get("file_name"), str)
  }
  unreferenced_files = sorted(actual_files - declared_files)

  report: dict[str, Any] = {
    "valid": not missing_images and not orphan_annotation_ids,
    "source_annotations": annotations_path.resolve().as_posix(),
    "source_annotations_sha256": _sha256(annotations_path),
    "image_root": image_root.resolve().as_posix(),
    "declared_images": len(images),
    "actual_image_files": len(actual_files),
    "annotations": len(annotations),
    "missing_image_count": len(missing_images),
    "missing_images": missing_images,
    "orphan_annotation_image_ids": sorted(orphan_annotation_ids),
    "unreferenced_image_count": len(unreferenced_files),
    "unreferenced_images": unreferenced_files,
    "removed_annotation_count": removed_annotation_count,
  }

  if clean_output is not None:
    if orphan_annotation_ids:
      raise CocoAuditError(
        "cannot clean COCO annotations with unknown image ids: "
        + ", ".join(str(item) for item in sorted(orphan_annotation_ids))
      )
    cleaned = dict(payload)
    cleaned["images"] = [image for image in images if image.get("id") not in missing_ids]
    cleaned["annotations"] = [
      annotation for annotation in annotations if annotation.get("image_id") not in missing_ids
    ]
    clean_output.parent.mkdir(parents=True, exist_ok=True)
    clean_output.write_text(
      json.dumps(cleaned, ensure_ascii=False, separators=(",", ":")) + "\n",
      encoding="utf-8",
    )
    report["clean_output"] = clean_output.resolve().as_posix()
    report["clean_output_sha256"] = _sha256(clean_output)
    report["cleaned_images"] = len(cleaned["images"])
    report["cleaned_annotations"] = len(cleaned["annotations"])

  if report_output is not None:
    report_output.parent.mkdir(parents=True, exist_ok=True)
    report_output.write_text(
      json.dumps(report, ensure_ascii=False, indent=2) + "\n",
      encoding="utf-8",
    )
  return report


def _parser() -> argparse.ArgumentParser:
  parser = argparse.ArgumentParser(description="Audit missing images in a COCO export.")
  parser.add_argument("--annotations", type=Path, required=True)
  parser.add_argument("--image-root", type=Path, required=True)
  parser.add_argument(
    "--clean-output",
    type=Path,
    help="Write a cleaned COCO copy with confirmed missing images and their annotations removed.",
  )
  parser.add_argument("--report-output", type=Path, help="Write the audit result as JSON.")
  return parser


def main(argv: list[str] | None = None) -> int:
  args = _parser().parse_args(argv)
  try:
    report = audit_coco(
      args.annotations,
      args.image_root,
      clean_output=args.clean_output,
      report_output=args.report_output,
    )
  except CocoAuditError as exc:
    print(json.dumps({"valid": False, "error": str(exc)}, ensure_ascii=False, indent=2))
    return 2
  print(json.dumps(report, ensure_ascii=False, indent=2))
  if report["valid"] or args.clean_output is not None:
    return 0
  return 2


if __name__ == "__main__":
  raise SystemExit(main())
