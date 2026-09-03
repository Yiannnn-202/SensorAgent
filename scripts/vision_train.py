"""Validate and train the fixed-class industrial segmentation baseline."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path
import sys

import yaml


IMAGE_SUFFIXES = frozenset({".bmp", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"})
REQUIRED_SPLITS = ("train", "val")


class DatasetValidationError(ValueError):
  """Raised when a YOLO segmentation dataset cannot be trained safely."""


@dataclass(frozen=True)
class SplitSummary:
  """Validated image and polygon counts for one dataset split."""

  images: int
  labeled_images: int
  negative_images: int
  instances: int


@dataclass(frozen=True)
class DatasetSummary:
  """Validated class map and split statistics."""

  data: str
  root: str
  classes: tuple[str, ...]
  splits: dict[str, SplitSummary]

  def to_dict(self) -> dict[str, object]:
    payload = asdict(self)
    payload["classes"] = list(self.classes)
    return payload


def _load_yaml(path: Path) -> dict[str, object]:
  if not path.is_file():
    raise DatasetValidationError(f"dataset YAML does not exist: {path}")
  try:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
  except yaml.YAMLError as exc:
    raise DatasetValidationError(f"dataset YAML is invalid: {exc}") from exc
  if not isinstance(payload, dict):
    raise DatasetValidationError("dataset YAML must contain a mapping")
  return payload


def _class_names(payload: dict[str, object]) -> tuple[str, ...]:
  raw_names = payload.get("names")
  if isinstance(raw_names, list):
    names = [str(name).strip() for name in raw_names]
  elif isinstance(raw_names, dict):
    try:
      indexed = {int(index): str(name).strip() for index, name in raw_names.items()}
    except (TypeError, ValueError) as exc:
      raise DatasetValidationError("class-map keys must be integer IDs") from exc
    expected = list(range(len(indexed)))
    if sorted(indexed) != expected:
      raise DatasetValidationError("class-map IDs must be continuous and start at 0")
    names = [indexed[index] for index in expected]
  else:
    raise DatasetValidationError("dataset YAML must define names as a list or ID mapping")
  if not names or any(not name for name in names):
    raise DatasetValidationError("class names must be non-empty")
  normalized = [name.casefold() for name in names]
  if len(set(normalized)) != len(normalized):
    raise DatasetValidationError("class names must be unique")
  return tuple(names)


def _dataset_root(data_path: Path, payload: dict[str, object]) -> Path:
  raw_root = payload.get("path", ".")
  if not isinstance(raw_root, str) or not raw_root.strip():
    raise DatasetValidationError("dataset path must be a non-empty string")
  root = Path(raw_root)
  if not root.is_absolute():
    root = data_path.parent / root
  return root.resolve()


def _resolve_entry(root: Path, value: str) -> Path:
  path = Path(value)
  if not path.is_absolute():
    path = root / path
  return path.resolve()


def _images_from_entry(root: Path, value: object, split: str) -> list[Path]:
  entries = value if isinstance(value, list) else [value]
  images: list[Path] = []
  for entry in entries:
    if not isinstance(entry, str) or not entry.strip():
      raise DatasetValidationError(f"{split} entries must be non-empty paths")
    path = _resolve_entry(root, entry)
    if path.is_dir():
      images.extend(
        candidate.resolve()
        for candidate in path.rglob("*")
        if candidate.is_file() and candidate.suffix.casefold() in IMAGE_SUFFIXES
      )
      continue
    if path.is_file() and path.suffix.casefold() == ".txt":
      for line in path.read_text(encoding="utf-8").splitlines():
        item = line.strip()
        if item:
          images.append(_resolve_entry(root, item))
      continue
    if path.is_file() and path.suffix.casefold() in IMAGE_SUFFIXES:
      images.append(path)
      continue
    raise DatasetValidationError(f"{split} path does not exist or has no supported format: {path}")
  unique = sorted(set(images))
  if not unique:
    raise DatasetValidationError(f"{split} split contains no images")
  missing = [path for path in unique if not path.is_file()]
  if missing:
    raise DatasetValidationError(f"{split} image does not exist: {missing[0]}")
  return unique


def _label_path(image_path: Path) -> Path:
  parts = list(image_path.parts)
  image_indices = [index for index, part in enumerate(parts) if part.casefold() == "images"]
  if not image_indices:
    raise DatasetValidationError(
      f"image path must contain an images directory so its label can be located: {image_path}"
    )
  parts[image_indices[-1]] = "labels"
  return Path(*parts).with_suffix(".txt")


def _validate_label(path: Path, class_count: int) -> int:
  if not path.is_file():
    return 0
  instances = 0
  for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
    line = raw_line.strip()
    if not line:
      continue
    tokens = line.split()
    if len(tokens) < 7 or (len(tokens) - 1) % 2 != 0:
      raise DatasetValidationError(
        f"segmentation label must contain a class ID and at least 3 polygon points: "
        f"{path}:{line_number}"
      )
    try:
      class_id = int(tokens[0])
      coordinates = [float(value) for value in tokens[1:]]
    except ValueError as exc:
      raise DatasetValidationError(
        f"label contains a non-numeric value: {path}:{line_number}"
      ) from exc
    if class_id < 0 or class_id >= class_count:
      raise DatasetValidationError(
        f"class ID is outside 0..{class_count - 1}: {path}:{line_number}"
      )
    if any(not math.isfinite(value) or value < 0.0 or value > 1.0 for value in coordinates):
      raise DatasetValidationError(
        f"polygon coordinates must be normalized to 0..1: {path}:{line_number}"
      )
    points = list(zip(coordinates[::2], coordinates[1::2]))
    area = abs(
      sum(
        x1 * y2 - x2 * y1
        for (x1, y1), (x2, y2) in zip(points, points[1:] + points[:1])
      )
    ) / 2.0
    if len(set(points)) < 3 or area <= 1e-8:
      raise DatasetValidationError(f"polygon has zero area: {path}:{line_number}")
    instances += 1
  return instances


def validate_dataset(data_path: Path) -> DatasetSummary:
  """Validate split isolation and segmentation labels before model training."""

  data_path = data_path.resolve()
  payload = _load_yaml(data_path)
  classes = _class_names(payload)
  root = _dataset_root(data_path, payload)
  split_images: dict[str, list[Path]] = {}
  split_summaries: dict[str, SplitSummary] = {}
  for split in (*REQUIRED_SPLITS, "test"):
    if split not in payload:
      if split in REQUIRED_SPLITS:
        raise DatasetValidationError(f"dataset YAML must define the {split} split")
      continue
    images = _images_from_entry(root, payload[split], split)
    split_images[split] = images
    labeled_images = 0
    instances = 0
    for image in images:
      image_instances = _validate_label(_label_path(image), len(classes))
      if image_instances:
        labeled_images += 1
        instances += image_instances
    if instances == 0:
      raise DatasetValidationError(f"{split} split contains no segmentation polygons")
    split_summaries[split] = SplitSummary(
      images=len(images),
      labeled_images=labeled_images,
      negative_images=len(images) - labeled_images,
      instances=instances,
    )

  split_names = list(split_images)
  for index, left in enumerate(split_names):
    for right in split_names[index + 1 :]:
      overlap = set(split_images[left]) & set(split_images[right])
      if overlap:
        sample = sorted(overlap)[0]
        raise DatasetValidationError(
          f"dataset leakage: {sample} appears in both {left} and {right}"
        )
  return DatasetSummary(
    data=data_path.as_posix(),
    root=root.as_posix(),
    classes=classes,
    splits=split_summaries,
  )


def _sha256(path: Path) -> str:
  digest = hashlib.sha256()
  with path.open("rb") as stream:
    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
      digest.update(chunk)
  return digest.hexdigest()


def _parser() -> argparse.ArgumentParser:
  parser = argparse.ArgumentParser(
    description="Validate or train the fixed-class YOLO11 segmentation baseline."
  )
  parser.add_argument("--data", type=Path, required=True, help="Ultralytics dataset YAML.")
  parser.add_argument("--model", default="models/vision/yolo11n-seg.pt")
  parser.add_argument("--epochs", type=int, default=100)
  parser.add_argument("--imgsz", type=int, default=640)
  parser.add_argument("--batch", type=int, default=8)
  parser.add_argument("--device", default="0")
  parser.add_argument("--workers", type=int, default=4)
  parser.add_argument("--patience", type=int, default=20)
  parser.add_argument("--seed", type=int, default=42)
  parser.add_argument("--project", type=Path, default=Path("runs/vision/train"))
  parser.add_argument("--name", default="baseline_seg")
  parser.add_argument(
    "--no-amp",
    action="store_true",
    help="Disable mixed precision when the Ultralytics CUDA AMP check stalls.",
  )
  parser.add_argument(
    "--dry-run",
    action="store_true",
    help="Validate data without loading a model.",
  )
  return parser


def main(argv: list[str] | None = None) -> int:
  args = _parser().parse_args(argv)
  try:
    summary = validate_dataset(args.data)
  except DatasetValidationError as exc:
    print(json.dumps({"valid": False, "error": str(exc)}, ensure_ascii=False, indent=2))
    return 2
  if args.dry_run:
    print(json.dumps({"valid": True, "dataset": summary.to_dict()}, ensure_ascii=False, indent=2))
    return 0
  if args.epochs <= 0 or args.imgsz <= 0 or args.batch == 0 or args.workers < 0:
    print(
      "epochs/imgsz must be positive, batch must be non-zero, and workers must be >= 0",
      file=sys.stderr,
    )
    return 2

  try:
    from ultralytics import YOLO
  except ImportError:
    print("ultralytics is required; install requirements.txt first", file=sys.stderr)
    return 2

  model = YOLO(args.model)
  metrics = model.train(
    data=str(args.data.resolve()),
    epochs=args.epochs,
    imgsz=args.imgsz,
    batch=args.batch,
    device=args.device,
    workers=args.workers,
    patience=args.patience,
    seed=args.seed,
    deterministic=True,
    amp=not args.no_amp,
    project=str(args.project),
    name=args.name,
  )
  save_dir = Path(getattr(metrics, "save_dir", args.project / args.name)).resolve()
  best = save_dir / "weights" / "best.pt"
  payload: dict[str, object] = {
    "dataset": summary.to_dict(),
    "model": args.model,
    "save_dir": save_dir.as_posix(),
    "best_weight": best.as_posix() if best.is_file() else None,
    "best_weight_sha256": _sha256(best) if best.is_file() else None,
    "epochs": args.epochs,
    "imgsz": args.imgsz,
    "batch": args.batch,
    "device": args.device,
    "seed": args.seed,
    "amp": not args.no_amp,
  }
  save_dir.mkdir(parents=True, exist_ok=True)
  (save_dir / "sensoragent_train_summary.json").write_text(
    json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
  )
  print(json.dumps(payload, ensure_ascii=False, indent=2))
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
