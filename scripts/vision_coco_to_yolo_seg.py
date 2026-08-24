"""Convert a COCO instance-segmentation export to an Ultralytics YOLO dataset."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil

import cv2
import numpy as np
import yaml


def _parser() -> argparse.ArgumentParser:
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--source", type=Path, required=True, help="COCO export containing train/valid/test.")
  parser.add_argument("--output", type=Path, required=True, help="Output YOLO segmentation dataset directory.")
  parser.add_argument(
      "--classes",
      nargs="+",
      required=True,
      help="COCO category names in the desired YOLO class order.",
  )
  return parser


def _decode_compressed_rle(value: str) -> list[int]:
  counts: list[int] = []
  position = 0
  while position < len(value):
    number, shift, more = 0, 0, True
    while more:
      code = ord(value[position]) - 48
      position += 1
      number |= (code & 0x1F) << (5 * shift)
      more = bool(code & 0x20)
      if not more and code & 0x10:
        number |= -1 << (5 * (shift + 1))
      shift += 1
    if len(counts) > 2:
      number += counts[-2]
    counts.append(number)
  return counts


def _rle_polygons(segmentation: dict, height: int, width: int) -> list[list[float]]:
  counts = segmentation.get("counts")
  if isinstance(counts, str):
    counts = _decode_compressed_rle(counts)
  if not isinstance(counts, list):
    return []
  flat = np.zeros(height * width, dtype=np.uint8)
  offset = 0
  for index, count in enumerate(counts):
    count = int(count)
    if count < 0 or offset + count > flat.size:
      raise ValueError("invalid COCO RLE run")
    if index % 2:
      flat[offset : offset + count] = 1
    offset += count
  if offset != flat.size:
    raise ValueError("COCO RLE does not cover the full image")
  mask = flat.reshape((height, width), order="F")
  contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
  return [contour.reshape(-1, 2).astype(float).flatten().tolist() for contour in contours if len(contour) >= 3]


def _polygon_line(annotation: dict, image: dict, class_id: int) -> str | None:
  segmentation = annotation.get("segmentation")
  width, height = image["width"], image["height"]
  if not isinstance(width, int) or not isinstance(height, int) or width <= 0 or height <= 0:
    raise ValueError(f"invalid dimensions for {image.get('file_name')!r}")
  if isinstance(segmentation, dict):
    raw_polygons = _rle_polygons(segmentation, height, width)
  elif isinstance(segmentation, list):
    raw_polygons = segmentation
  else:
    return None
  polygons: list[str] = []
  for polygon in raw_polygons:
    if not isinstance(polygon, list) or len(polygon) < 6 or len(polygon) % 2:
      continue
    points = []
    for index in range(0, len(polygon), 2):
      x, y = float(polygon[index]), float(polygon[index + 1])
      points.extend((min(1.0, max(0.0, x / width)), min(1.0, max(0.0, y / height))))
    polygons.append(" ".join(f"{coordinate:.8f}" for coordinate in points))
  return f"{class_id} {' '.join(polygons)}" if polygons else None


def convert(source: Path, output: Path, classes: list[str]) -> None:
  source, output = source.resolve(), output.resolve()
  if output.exists():
    raise FileExistsError(f"refusing to overwrite existing output: {output}")
  requested = [name.casefold() for name in classes]
  if len(set(requested)) != len(requested):
    raise ValueError("class names must be unique")

  output.mkdir(parents=True)
  split_paths = {"train": "train", "valid": "val", "test": "test"}
  for coco_split, yolo_split in split_paths.items():
    source_split = source / coco_split
    payload = json.loads((source_split / "_annotations.coco.json").read_text(encoding="utf-8"))
    category_ids = {
        category["id"]: requested.index(category["name"].casefold())
        for category in payload["categories"]
        if category["name"].casefold() in requested
    }
    images = {image["id"]: image for image in payload["images"]}
    annotations: dict[int, list[dict]] = {image_id: [] for image_id in images}
    for annotation in payload["annotations"]:
      if annotation.get("category_id") in category_ids:
        annotations.setdefault(annotation["image_id"], []).append(annotation)

    image_dir, label_dir = output / "images" / yolo_split, output / "labels" / yolo_split
    image_dir.mkdir(parents=True)
    label_dir.mkdir(parents=True)
    for image_id, image in images.items():
      image_name = image["file_name"]
      shutil.copy2(source_split / image_name, image_dir / image_name)
      lines = [
          line
          for annotation in annotations.get(image_id, [])
          if (line := _polygon_line(annotation, image, category_ids[annotation["category_id"]])) is not None
      ]
      (label_dir / Path(image_name).with_suffix(".txt").name).write_text(
          "\n".join(lines) + ("\n" if lines else ""), encoding="utf-8"
      )

  (output / "data.yaml").write_text(
      yaml.safe_dump({"path": str(output), "train": "images/train", "val": "images/val", "test": "images/test", "names": classes}, sort_keys=False),
      encoding="utf-8",
  )


def main() -> None:
  args = _parser().parse_args()
  convert(args.source, args.output, args.classes)


if __name__ == "__main__":
  main()
