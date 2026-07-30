"""Convert a reviewed COCO detection export into the Grounding DINO JSONL contract."""

from __future__ import annotations

import argparse
from collections import defaultdict
import json
import math
import os
from pathlib import Path
from typing import Any

import yaml


class CocoConversionError(ValueError):
  """Raised when a COCO export cannot be mapped without losing label meaning."""


def _load_mapping(path: Path) -> tuple[tuple[str, ...], dict[str, str | None]]:
  if not path.is_file():
    raise CocoConversionError(f"category mapping does not exist: {path}")
  payload = yaml.safe_load(path.read_text(encoding="utf-8"))
  if not isinstance(payload, dict):
    raise CocoConversionError("category mapping must contain a YAML mapping")
  raw_classes = payload.get("classes")
  raw_mapping = payload.get("category_map")
  if not isinstance(raw_classes, list) or not raw_classes:
    raise CocoConversionError("category mapping classes must be a non-empty list")
  classes = tuple(str(item).strip() for item in raw_classes)
  if any(not item for item in classes) or len(set(classes)) != len(classes):
    raise CocoConversionError("category mapping classes must be unique non-empty names")
  if not isinstance(raw_mapping, dict):
    raise CocoConversionError("category_map must map source category names to target names or null")
  mapping: dict[str, str | None] = {}
  for source, target in raw_mapping.items():
    if not isinstance(source, str) or not source.strip():
      raise CocoConversionError("category_map source names must be non-empty strings")
    if target is not None and (not isinstance(target, str) or not target.strip()):
      raise CocoConversionError("category_map targets must be non-empty strings or null")
    mapping[source.casefold()] = target.strip() if isinstance(target, str) else None
  unknown_targets = sorted({target for target in mapping.values() if target is not None} - set(classes))
  if unknown_targets:
    raise CocoConversionError(
      f"category_map targets are not present in classes: {', '.join(unknown_targets)}"
    )
  return classes, mapping


def _box_xyxy(value: object, width: int, height: int) -> list[float]:
  if not isinstance(value, list) or len(value) != 4:
    raise CocoConversionError("COCO annotation bbox must contain [x, y, width, height]")
  if any(isinstance(item, bool) or not isinstance(item, (int, float)) for item in value):
    raise CocoConversionError("COCO annotation bbox values must be numeric")
  x, y, box_width, box_height = (float(item) for item in value)
  if any(not math.isfinite(item) for item in (x, y, box_width, box_height)):
    raise CocoConversionError("COCO annotation bbox values must be finite")
  x1 = max(0.0, min(float(width), x))
  y1 = max(0.0, min(float(height), y))
  x2 = max(0.0, min(float(width), x + box_width))
  y2 = max(0.0, min(float(height), y + box_height))
  if x2 <= x1 or y2 <= y1:
    raise CocoConversionError("COCO annotation bbox is empty after image-bound clipping")
  return [x1, y1, x2, y2]


def convert_coco(
  annotations_path: Path,
  image_root: Path,
  output_path: Path,
  mapping_path: Path,
  *,
  split: str,
  scene_prefix: str,
  source_url: str,
  source_license: str,
  include_negative: bool,
) -> dict[str, Any]:
  """Write the mapped rows and return a conversion summary."""

  if split not in {"train", "val", "test"}:
    raise CocoConversionError("split must be train, val, or test")
  if not annotations_path.is_file():
    raise CocoConversionError(f"COCO annotations do not exist: {annotations_path}")
  try:
    payload = json.loads(annotations_path.read_text(encoding="utf-8"))
  except json.JSONDecodeError as exc:
    raise CocoConversionError(f"COCO annotations are invalid JSON: {exc.msg}") from exc
  if not isinstance(payload, dict):
    raise CocoConversionError("COCO annotations must contain a JSON object")
  images = payload.get("images")
  annotations = payload.get("annotations")
  categories = payload.get("categories")
  if not isinstance(images, list) or not isinstance(annotations, list) or not isinstance(categories, list):
    raise CocoConversionError("COCO annotations must contain images, annotations, and categories lists")
  classes, mapping = _load_mapping(mapping_path)
  category_names = {
    item.get("id"): item.get("name")
    for item in categories
    if isinstance(item, dict) and isinstance(item.get("id"), int) and isinstance(item.get("name"), str)
  }
  grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
  for annotation in annotations:
    if not isinstance(annotation, dict) or not isinstance(annotation.get("image_id"), int):
      raise CocoConversionError("each COCO annotation must have an integer image_id")
    if annotation.get("iscrowd", 0) == 0:
      grouped[annotation["image_id"]].append(annotation)

  output_path.parent.mkdir(parents=True, exist_ok=True)
  rows: list[dict[str, Any]] = []
  skipped_images = 0
  object_count = 0
  for image in images:
    if not isinstance(image, dict) or not isinstance(image.get("id"), int):
      raise CocoConversionError("each COCO image must have an integer id")
    file_name = image.get("file_name")
    width = image.get("width")
    height = image.get("height")
    if not isinstance(file_name, str) or not file_name.strip():
      raise CocoConversionError(f"COCO image {image['id']} has no file_name")
    if not isinstance(width, int) or not isinstance(height, int) or width <= 0 or height <= 0:
      raise CocoConversionError(f"COCO image {image['id']} has invalid dimensions")
    image_path = (image_root / file_name).resolve()
    if not image_path.is_file():
      raise CocoConversionError(f"COCO image does not exist: {image_path}")
    objects = []
    for annotation in grouped.get(image["id"], []):
      source_name = category_names.get(annotation.get("category_id"))
      if not isinstance(source_name, str):
        raise CocoConversionError(
          f"COCO annotation references unknown category: {annotation.get('category_id')}"
        )
      target_name = mapping.get(source_name.casefold())
      if target_name is None:
        continue
      objects.append(
        {
          "class_name": target_name,
          "bbox_xyxy": _box_xyxy(annotation.get("bbox"), width, height),
        }
      )
    if not objects and not include_negative:
      skipped_images += 1
      continue
    relative_image = Path(os.path.relpath(image_path, output_path.parent)).as_posix()
    rows.append(
      {
        "sample_id": f"{scene_prefix}_{image['id']}",
        "scene_id": f"{scene_prefix}_{image['id']}",
        "split": split,
        "image": relative_image,
        "objects": objects,
        "source": {
          "kind": "public",
          "dataset": annotations_path.stem,
          "url": source_url,
          "license": source_license,
        },
      }
    )
    object_count += len(objects)

  output_path.write_text(
    "\n".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) for row in rows) + "\n",
    encoding="utf-8",
  )
  return {
    "output": output_path.as_posix(),
    "classes": list(classes),
    "split": split,
    "images_written": len(rows),
    "images_skipped": skipped_images,
    "objects_written": object_count,
  }


def _parser() -> argparse.ArgumentParser:
  parser = argparse.ArgumentParser(description="Convert COCO boxes to Grounding DINO JSONL.")
  parser.add_argument("--annotations", type=Path, required=True)
  parser.add_argument("--image-root", type=Path, required=True)
  parser.add_argument("--output", type=Path, required=True)
  parser.add_argument("--category-map", type=Path, required=True)
  parser.add_argument("--split", choices=("train", "val", "test"), default="train")
  parser.add_argument("--scene-prefix", required=True)
  parser.add_argument("--source-url", required=True)
  parser.add_argument("--source-license", required=True)
  parser.add_argument(
    "--include-negative",
    action="store_true",
    help="Keep images without mapped targets; use only after checking unmapped objects are annotated.",
  )
  return parser


def main(argv: list[str] | None = None) -> int:
  args = _parser().parse_args(argv)
  try:
    result = convert_coco(
      args.annotations,
      args.image_root,
      args.output,
      args.category_map,
      split=args.split,
      scene_prefix=args.scene_prefix,
      source_url=args.source_url,
      source_license=args.source_license,
      include_negative=args.include_negative,
    )
  except CocoConversionError as exc:
    print(json.dumps({"valid": False, "error": str(exc)}, ensure_ascii=False, indent=2))
    return 2
  print(json.dumps({"valid": True, **result}, ensure_ascii=False, indent=2))
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
