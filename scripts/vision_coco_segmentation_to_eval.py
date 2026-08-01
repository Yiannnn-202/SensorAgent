"""Convert a reviewed COCO-Segmentation export into vision evaluation data."""

from __future__ import annotations

import argparse
from collections import defaultdict
import json
import math
from pathlib import Path
import re
import shutil
from typing import Any, Sequence

import numpy as np


class CocoSegmentationConversionError(ValueError):
  """Raised when an export cannot be converted without ambiguous ground truth."""


_SPLIT_DIRECTORIES = (("train", "train"), ("valid", "val"), ("test", "test"))
_ROBOFLOW_SUFFIX = re.compile(r"\.rf\.[^.]+$", flags=re.IGNORECASE)


def _compressed_rle_counts(value: str) -> list[int]:
  """Decode the compact count string used by the COCO mask API."""

  counts: list[int] = []
  position = 0
  while position < len(value):
    number = 0
    shift = 0
    more = True
    while more:
      if position >= len(value):
        raise CocoSegmentationConversionError("compressed COCO RLE ends mid-value")
      code = ord(value[position]) - 48
      position += 1
      if code < 0 or code > 0x3F:
        raise CocoSegmentationConversionError("compressed COCO RLE has an invalid character")
      number |= (code & 0x1F) << (5 * shift)
      more = bool(code & 0x20)
      if not more and (code & 0x10):
        number |= -1 << (5 * (shift + 1))
      shift += 1
    if len(counts) > 2:
      number += counts[-2]
    if number < 0:
      raise CocoSegmentationConversionError("compressed COCO RLE decoded a negative run")
    counts.append(number)
  return counts


def _mask_from_rle_counts(counts: Sequence[int], height: int, width: int) -> np.ndarray:
  total = height * width
  flat = np.zeros(total, dtype=np.uint8)
  offset = 0
  foreground = False
  for raw_count in counts:
    if isinstance(raw_count, bool) or not isinstance(raw_count, (int, np.integer)):
      raise CocoSegmentationConversionError("COCO RLE counts must be integers")
    count = int(raw_count)
    if count < 0 or offset + count > total:
      raise CocoSegmentationConversionError("COCO RLE run exceeds the image dimensions")
    if foreground and count:
      flat[offset : offset + count] = 1
    offset += count
    foreground = not foreground
  if offset != total:
    raise CocoSegmentationConversionError(
      f"COCO RLE covers {offset} pixels but image contains {total}"
    )
  return flat.reshape((height, width), order="F").astype(bool)


def decode_coco_segmentation(
  segmentation: object,
  *,
  height: int,
  width: int,
) -> np.ndarray:
  """Decode compressed/uncompressed COCO RLE or polygon segmentation."""

  if isinstance(segmentation, dict):
    size = segmentation.get("size")
    if size != [height, width]:
      raise CocoSegmentationConversionError(
        f"COCO RLE size {size!r} does not match image [{height}, {width}]"
      )
    raw_counts = segmentation.get("counts")
    if isinstance(raw_counts, str):
      counts = _compressed_rle_counts(raw_counts)
    elif isinstance(raw_counts, list):
      counts = raw_counts
    else:
      raise CocoSegmentationConversionError("COCO RLE counts must be a string or list")
    return _mask_from_rle_counts(counts, height, width)

  if isinstance(segmentation, list):
    try:
      from PIL import Image, ImageDraw
    except ImportError as exc:
      raise ImportError("Pillow is required to rasterize COCO polygons") from exc
    image = Image.new("1", (width, height), 0)
    draw = ImageDraw.Draw(image)
    for raw_polygon in segmentation:
      if not isinstance(raw_polygon, list) or len(raw_polygon) < 6 or len(raw_polygon) % 2:
        raise CocoSegmentationConversionError(
          "each COCO polygon must contain at least three x/y coordinate pairs"
        )
      if any(
        isinstance(value, bool) or not isinstance(value, (int, float))
        for value in raw_polygon
      ):
        raise CocoSegmentationConversionError("COCO polygon coordinates must be numeric")
      points = [
        (float(raw_polygon[index]), float(raw_polygon[index + 1]))
        for index in range(0, len(raw_polygon), 2)
      ]
      draw.polygon(points, fill=1)
    return np.asarray(image, dtype=bool)

  raise CocoSegmentationConversionError(
    "COCO annotation segmentation must be compressed RLE, uncompressed RLE, or polygons"
  )


def _bbox_xyxy(value: object, width: int, height: int) -> list[float]:
  if not isinstance(value, list) or len(value) != 4:
    raise CocoSegmentationConversionError("COCO bbox must contain [x, y, width, height]")
  if any(
    isinstance(item, bool) or not isinstance(item, (int, float))
    for item in value
  ):
    raise CocoSegmentationConversionError("COCO bbox values must be numeric")
  x, y, box_width, box_height = (float(item) for item in value)
  if any(not math.isfinite(item) for item in (x, y, box_width, box_height)):
    raise CocoSegmentationConversionError("COCO bbox values must be finite")
  bbox = [
    max(0.0, min(float(width), x)),
    max(0.0, min(float(height), y)),
    max(0.0, min(float(width), x + box_width)),
    max(0.0, min(float(height), y + box_height)),
  ]
  if bbox[2] <= bbox[0] or bbox[3] <= bbox[1]:
    raise CocoSegmentationConversionError("COCO bbox is empty after image-bound clipping")
  return bbox


def _source_scene(file_name: str) -> str:
  stem = _ROBOFLOW_SUFFIX.sub("", Path(file_name).stem)
  normalized = re.sub(r"[^A-Za-z0-9_-]+", "_", stem).strip("_").casefold()
  if not normalized:
    raise CocoSegmentationConversionError(f"cannot derive scene_id from {file_name!r}")
  return normalized


def _load_split(root: Path, directory: str) -> dict[str, Any]:
  annotation_path = root / directory / "_annotations.coco.json"
  if not annotation_path.is_file():
    raise CocoSegmentationConversionError(f"COCO annotations do not exist: {annotation_path}")
  try:
    payload = json.loads(annotation_path.read_text(encoding="utf-8"))
  except json.JSONDecodeError as exc:
    raise CocoSegmentationConversionError(
      f"invalid JSON in {annotation_path}: {exc.msg}"
    ) from exc
  if not isinstance(payload, dict):
    raise CocoSegmentationConversionError(f"COCO file must contain an object: {annotation_path}")
  for field in ("images", "annotations", "categories"):
    if not isinstance(payload.get(field), list):
      raise CocoSegmentationConversionError(f"COCO {field} must be a list: {annotation_path}")
  return payload


def _write_jsonl(path: Path, rows: Sequence[dict[str, Any]]) -> None:
  path.write_text(
    "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in rows),
    encoding="utf-8",
  )


def convert_coco_segmentation_export(
  source_root: Path,
  output_root: Path,
  *,
  sample_prefix: str,
  query: str,
  category_name: str | None,
  dataset_name: str,
  source_url: str,
  source_license: str,
) -> dict[str, Any]:
  """Convert train/valid/test COCO-Seg folders and return an audit report."""

  source_root = source_root.resolve()
  output_root = output_root.resolve()
  normalized_prefix = _source_scene(sample_prefix)
  if not query.strip():
    raise CocoSegmentationConversionError("query must be non-empty")
  if not source_url.strip() or not source_license.strip():
    raise CocoSegmentationConversionError("public data requires source URL and license")

  prepared: list[dict[str, Any]] = []
  split_reports: dict[str, dict[str, Any]] = {}
  warnings: list[str] = []
  scene_splits: dict[str, set[str]] = defaultdict(set)

  for directory, split in _SPLIT_DIRECTORIES:
    payload = _load_split(source_root, directory)
    category_by_id: dict[int, str] = {}
    name_to_ids: dict[str, list[int]] = defaultdict(list)
    for category in payload["categories"]:
      if (
        not isinstance(category, dict)
        or not isinstance(category.get("id"), int)
        or not isinstance(category.get("name"), str)
        or not category["name"].strip()
      ):
        raise CocoSegmentationConversionError(f"invalid category in split {directory}")
      category_id = category["id"]
      if category_id in category_by_id:
        raise CocoSegmentationConversionError(
          f"duplicate category id {category_id} in split {directory}"
        )
      name = category["name"].strip()
      category_by_id[category_id] = name
      name_to_ids[name.casefold()].append(category_id)

    duplicate_names = {
      name: ids for name, ids in name_to_ids.items() if len(ids) > 1
    }
    for name, ids in sorted(duplicate_names.items()):
      warnings.append(
        f"{directory}: duplicate category name {name!r} uses ids {ids}; all matching ids are accepted"
      )
    if category_name is None:
      if len(name_to_ids) != 1:
        raise CocoSegmentationConversionError(
          f"split {directory} has several category names; pass --category-name"
        )
      selected_name = next(iter(name_to_ids))
    else:
      selected_name = category_name.strip().casefold()
    selected_ids = set(name_to_ids.get(selected_name, []))
    if not selected_ids:
      raise CocoSegmentationConversionError(
        f"category {category_name!r} does not exist in split {directory}"
      )

    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    used_category_ids: set[int] = set()
    for annotation in payload["annotations"]:
      if not isinstance(annotation, dict) or not isinstance(annotation.get("image_id"), int):
        raise CocoSegmentationConversionError(f"invalid annotation in split {directory}")
      category_id = annotation.get("category_id")
      if category_id not in category_by_id:
        raise CocoSegmentationConversionError(
          f"annotation references unknown category {category_id!r} in split {directory}"
        )
      used_category_ids.add(category_id)
      if category_id in selected_ids:
        grouped[annotation["image_id"]].append(annotation)

    split_entries: list[dict[str, Any]] = []
    for image in payload["images"]:
      if not isinstance(image, dict) or not isinstance(image.get("id"), int):
        raise CocoSegmentationConversionError(f"invalid image record in split {directory}")
      file_name = image.get("file_name")
      width = image.get("width")
      height = image.get("height")
      if not isinstance(file_name, str) or not file_name.strip():
        raise CocoSegmentationConversionError(f"image {image['id']} has no file_name")
      if not isinstance(width, int) or not isinstance(height, int) or width <= 0 or height <= 0:
        raise CocoSegmentationConversionError(f"image {file_name!r} has invalid dimensions")
      source_image = source_root / directory / file_name
      if not source_image.is_file():
        raise CocoSegmentationConversionError(f"COCO image does not exist: {source_image}")
      annotations = grouped.get(image["id"], [])
      if len(annotations) > 1:
        raise CocoSegmentationConversionError(
          f"image {file_name!r} has {len(annotations)} matching instances; "
          "this evaluator needs one target instance per image"
        )
      scene_id = _source_scene(file_name)
      scene_splits[scene_id].add(split)
      sample_id = f"{normalized_prefix}_{split}_{image['id']}"
      split_entries.append(
        {
          "directory": directory,
          "split": split,
          "sample_id": sample_id,
          "scene_id": scene_id,
          "file_name": file_name,
          "source_image": source_image,
          "width": width,
          "height": height,
          "annotation": annotations[0] if annotations else None,
        }
      )

    prepared.extend(split_entries)
    split_reports[split] = {
      "image_count": len(split_entries),
      "positive_count": sum(entry["annotation"] is not None for entry in split_entries),
      "negative_count": sum(entry["annotation"] is None for entry in split_entries),
      "annotation_count": sum(len(items) for items in grouped.values()),
      "category_ids": sorted(category_by_id),
      "selected_category_ids": sorted(selected_ids),
      "used_category_ids": sorted(used_category_ids),
      "unused_category_ids": sorted(set(category_by_id) - used_category_ids),
      "duplicate_category_names": duplicate_names,
    }

  leakage = {
    scene_id: sorted(splits)
    for scene_id, splits in scene_splits.items()
    if len(splits) > 1
  }
  if leakage:
    details = ", ".join(f"{scene}: {splits}" for scene, splits in sorted(leakage.items()))
    raise CocoSegmentationConversionError(f"source scene leakage across splits: {details}")

  try:
    from PIL import Image
  except ImportError as exc:
    raise ImportError("Pillow is required to validate images and save masks") from exc

  output_root.mkdir(parents=True, exist_ok=True)
  rows_by_split: dict[str, list[dict[str, Any]]] = defaultdict(list)
  area_mismatch_count = 0
  area_equals_bbox_count = 0
  area_mismatch_examples: list[dict[str, Any]] = []
  for entry in prepared:
    image_destination = output_root / "images" / entry["split"] / entry["file_name"]
    image_destination.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(entry["source_image"]) as source_image:
      source_image.verify()
    shutil.copy2(entry["source_image"], image_destination)

    expected: dict[str, Any]
    annotation = entry["annotation"]
    if annotation is None:
      expected = {"found": False}
    else:
      mask = decode_coco_segmentation(
        annotation.get("segmentation"),
        height=entry["height"],
        width=entry["width"],
      )
      mask_area = int(mask.sum())
      if mask_area <= 0:
        raise CocoSegmentationConversionError(
          f"annotation {annotation.get('id')} produced an empty mask"
        )
      recorded_area = annotation.get("area")
      bbox = _bbox_xyxy(annotation.get("bbox"), entry["width"], entry["height"])
      if isinstance(recorded_area, (int, float)) and not isinstance(recorded_area, bool):
        tolerance = max(1.0, mask_area * 0.01)
        if abs(float(recorded_area) - mask_area) > tolerance:
          area_mismatch_count += 1
          bbox_area = (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])
          if abs(float(recorded_area) - bbox_area) <= max(1.0, bbox_area * 0.01):
            area_equals_bbox_count += 1
          if len(area_mismatch_examples) < 10:
            area_mismatch_examples.append(
              {
                "split": entry["split"],
                "annotation_id": annotation.get("id"),
                "recorded_area": recorded_area,
                "decoded_mask_area": mask_area,
                "bbox_area": bbox_area,
              }
            )
      mask_path = output_root / "masks" / entry["split"] / f"{entry['sample_id']}.png"
      mask_path.parent.mkdir(parents=True, exist_ok=True)
      Image.fromarray(mask.astype(np.uint8) * 255, mode="L").save(mask_path)
      y_coordinates, x_coordinates = np.where(mask)
      expected = {
        "found": True,
        "bbox_2d": bbox,
        "center_px": [float(x_coordinates.mean()), float(y_coordinates.mean())],
        "mask": mask_path.relative_to(output_root).as_posix(),
      }

    row = {
      "sample_id": entry["sample_id"],
      "scene_id": entry["scene_id"],
      "split": entry["split"],
      "query": query.strip(),
      "image": image_destination.relative_to(output_root).as_posix(),
      "expected": expected,
      "source": {
        "kind": "public",
        "dataset": dataset_name,
        "url": source_url,
        "license": source_license,
      },
    }
    rows_by_split[entry["split"]].append(row)

  all_rows: list[dict[str, Any]] = []
  for split in ("train", "val", "test"):
    rows = rows_by_split[split]
    _write_jsonl(output_root / f"manifest_{split}.jsonl", rows)
    all_rows.extend(rows)
  _write_jsonl(output_root / "manifest_all.jsonl", all_rows)

  if area_mismatch_count:
    warnings.append(
      f"{area_mismatch_count} annotation area values differ from decoded RLE mask area; "
      f"{area_equals_bbox_count} equal bbox area. Evaluation masks use decoded RLE pixels."
    )

  report = {
    "valid": True,
    "source_root": str(source_root),
    "output_root": str(output_root),
    "dataset": dataset_name,
    "sample_prefix": normalized_prefix,
    "query": query.strip(),
    "category_name": category_name,
    "source_url": source_url,
    "license": source_license,
    "image_count": len(all_rows),
    "positive_count": sum(row["expected"]["found"] for row in all_rows),
    "negative_count": sum(not row["expected"]["found"] for row in all_rows),
    "scene_count": len(scene_splits),
    "scene_split_leakage": leakage,
    "area_mismatch_count": area_mismatch_count,
    "area_equals_bbox_count": area_equals_bbox_count,
    "area_mismatch_examples": area_mismatch_examples,
    "splits": split_reports,
    "warnings": warnings,
    "outputs": {
      "manifest_train": "manifest_train.jsonl",
      "manifest_val": "manifest_val.jsonl",
      "manifest_test": "manifest_test.jsonl",
      "manifest_all": "manifest_all.jsonl",
      "masks": "masks/",
      "images": "images/",
    },
  }
  (output_root / "conversion_report.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
  )
  return report


def _parser() -> argparse.ArgumentParser:
  parser = argparse.ArgumentParser(
    description="Convert a Roboflow-style COCO-Seg train/valid/test export for evaluation."
  )
  parser.add_argument("--source-root", type=Path, required=True)
  parser.add_argument("--output-root", type=Path, required=True)
  parser.add_argument("--sample-prefix", required=True)
  parser.add_argument("--query", required=True)
  parser.add_argument("--category-name", default=None)
  parser.add_argument("--dataset-name", required=True)
  parser.add_argument("--source-url", required=True)
  parser.add_argument("--source-license", required=True)
  return parser


def main(argv: list[str] | None = None) -> int:
  args = _parser().parse_args(argv)
  try:
    report = convert_coco_segmentation_export(
      args.source_root,
      args.output_root,
      sample_prefix=args.sample_prefix,
      query=args.query,
      category_name=args.category_name,
      dataset_name=args.dataset_name,
      source_url=args.source_url,
      source_license=args.source_license,
    )
  except (CocoSegmentationConversionError, ImportError, OSError) as exc:
    print(json.dumps({"valid": False, "error": str(exc)}, ensure_ascii=False, indent=2))
    return 2
  print(json.dumps(report, ensure_ascii=False, indent=2))
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
