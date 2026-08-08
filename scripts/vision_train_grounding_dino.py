"""Validate industrial detection data and fine-tune Grounding DINO directly."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path
import random
import sys
import time
from typing import Any

import yaml


SPLITS = ("train", "val", "test")
REQUIRED_SPLITS = ("train", "val")


class GroundingDinoDatasetError(ValueError):
  """Raised when training data cannot be mapped safely to text-grounded boxes."""


@dataclass(frozen=True)
class TrainingObject:
  """One text-class target with an absolute xyxy box."""

  class_name: str
  class_id: int
  bbox_xyxy: tuple[float, float, float, float]
  mask: str | None = None


@dataclass(frozen=True)
class TrainingSample:
  """One validated image row from the JSONL training manifest."""

  sample_id: str
  scene_id: str
  split: str
  image: str
  image_path: Path
  objects: tuple[TrainingObject, ...]
  source: dict[str, Any]


@dataclass(frozen=True)
class SplitSummary:
  """Validated counts for one data split."""

  samples: int
  scenes: int
  negative_samples: int
  instances: int
  class_instances: dict[str, int]


@dataclass(frozen=True)
class DatasetSummary:
  """Manifest identity, class order, and split statistics."""

  manifest: str
  manifest_sha256: str
  dataset_sha256: str
  classes: tuple[str, ...]
  splits: dict[str, SplitSummary]

  def to_dict(self) -> dict[str, Any]:
    payload = asdict(self)
    payload["classes"] = list(self.classes)
    return payload


@dataclass(frozen=True)
class TrainSettings:
  """Resolved direct fine-tuning settings."""

  model: str
  manifest: Path
  output_dir: Path
  classes: tuple[str, ...]
  epochs: int
  batch_size: int
  gradient_accumulation_steps: int
  learning_rate: float
  weight_decay: float
  warmup_ratio: float
  max_grad_norm: float
  image_shortest_edge: int
  image_longest_edge: int
  num_workers: int
  seed: int
  device: str
  amp: bool


def _sha256(path: Path) -> str:
  digest = hashlib.sha256()
  with path.open("rb") as stream:
    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
      digest.update(chunk)
  return digest.hexdigest()


def _dataset_sha256(manifest_path: Path, samples: tuple[TrainingSample, ...]) -> str:
  digest = hashlib.sha256()
  digest.update(manifest_path.read_bytes())
  for sample in sorted(samples, key=lambda item: item.sample_id):
    digest.update(f"{sample.sample_id}\0{sample.image}\0".encode("utf-8"))
    with sample.image_path.open("rb") as stream:
      for chunk in iter(lambda: stream.read(1024 * 1024), b""):
        digest.update(chunk)
    for target in sample.objects:
      if target.mask is not None:
        digest.update(target.mask.encode("utf-8"))
        with (manifest_path.parent / target.mask).resolve().open("rb") as stream:
          for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
  return digest.hexdigest()


def _clean_classes(value: object) -> tuple[str, ...]:
  if not isinstance(value, list):
    raise GroundingDinoDatasetError("config classes must be a list in prompt order")
  classes = tuple(str(item).strip() for item in value)
  if not classes or any(not item for item in classes):
    raise GroundingDinoDatasetError("config classes must contain non-empty names")
  if any("." in item for item in classes):
    raise GroundingDinoDatasetError("class names cannot contain '.', the Grounding DINO prompt delimiter")
  if len({item.casefold() for item in classes}) != len(classes):
    raise GroundingDinoDatasetError("config classes must be unique")
  return classes


def _relative_file(
  value: object,
  *,
  manifest_path: Path,
  field: str,
  check_files: bool,
) -> tuple[str, Path]:
  if not isinstance(value, str) or not value.strip():
    raise GroundingDinoDatasetError(f"{field} must be a non-empty relative path")
  relative = Path(value)
  if relative.is_absolute():
    raise GroundingDinoDatasetError(f"{field} must be relative to the manifest: {value}")
  resolved = (manifest_path.parent / relative).resolve()
  if check_files and not resolved.is_file():
    raise GroundingDinoDatasetError(f"{field} does not exist: {resolved}")
  return relative.as_posix(), resolved


def _validate_source(value: object) -> dict[str, Any]:
  if not isinstance(value, dict):
    raise GroundingDinoDatasetError("source must be an object")
  kind = value.get("kind")
  if not isinstance(kind, str) or not kind.strip():
    raise GroundingDinoDatasetError("source.kind must be a non-empty string")
  if kind.casefold() == "public":
    if not isinstance(value.get("url"), str) or not value["url"].strip():
      raise GroundingDinoDatasetError("public data must record source.url")
    if not isinstance(value.get("license"), str) or not value["license"].strip():
      raise GroundingDinoDatasetError("public data must record source.license")
  return dict(value)


def _validate_box(value: object) -> tuple[float, float, float, float]:
  if not isinstance(value, list) or len(value) != 4:
    raise GroundingDinoDatasetError("bbox_xyxy must contain [x_min, y_min, x_max, y_max]")
  if any(isinstance(item, bool) or not isinstance(item, (int, float)) for item in value):
    raise GroundingDinoDatasetError("bbox_xyxy values must be numbers")
  box = tuple(float(item) for item in value)
  if any(not math.isfinite(item) or item < 0 for item in box):
    raise GroundingDinoDatasetError("bbox_xyxy values must be finite and non-negative")
  if box[2] <= box[0] or box[3] <= box[1]:
    raise GroundingDinoDatasetError("bbox_xyxy must have positive width and height")
  return box


def _parse_object(
  value: object,
  *,
  class_ids: dict[str, int],
  manifest_path: Path,
  check_files: bool,
) -> TrainingObject:
  if not isinstance(value, dict):
    raise GroundingDinoDatasetError("each objects entry must be an object")
  class_name = value.get("class_name")
  if not isinstance(class_name, str) or class_name not in class_ids:
    raise GroundingDinoDatasetError(
      f"class_name must match the configured prompt classes: {class_name!r}"
    )
  mask = value.get("mask")
  mask_value = None
  if mask is not None:
    mask_value, _ = _relative_file(
      mask,
      manifest_path=manifest_path,
      field="objects[].mask",
      check_files=check_files,
    )
  return TrainingObject(
    class_name=class_name,
    class_id=class_ids[class_name],
    bbox_xyxy=_validate_box(value.get("bbox_xyxy")),
    mask=mask_value,
  )


def _parse_row(
  value: object,
  *,
  line_number: int,
  manifest_path: Path,
  class_ids: dict[str, int],
  check_files: bool,
) -> TrainingSample:
  if not isinstance(value, dict):
    raise GroundingDinoDatasetError("row must be a JSON object")
  sample_id = value.get("sample_id")
  scene_id = value.get("scene_id")
  split = value.get("split")
  if not isinstance(sample_id, str) or not sample_id.strip():
    raise GroundingDinoDatasetError("sample_id must be a non-empty string")
  if not isinstance(scene_id, str) or not scene_id.strip():
    raise GroundingDinoDatasetError("scene_id must be a non-empty string")
  if split not in SPLITS:
    raise GroundingDinoDatasetError(f"split must be one of {SPLITS}")
  image, image_path = _relative_file(
    value.get("image"),
    manifest_path=manifest_path,
    field="image",
    check_files=check_files,
  )
  raw_objects = value.get("objects")
  if not isinstance(raw_objects, list):
    raise GroundingDinoDatasetError("objects must be a list; use [] for a negative sample")
  try:
    objects = tuple(
      _parse_object(
        target,
        class_ids=class_ids,
        manifest_path=manifest_path,
        check_files=check_files,
      )
      for target in raw_objects
    )
    source = _validate_source(value.get("source"))
  except GroundingDinoDatasetError as exc:
    raise GroundingDinoDatasetError(f"line {line_number}: {exc}") from exc
  return TrainingSample(
    sample_id=sample_id,
    scene_id=scene_id,
    split=split,
    image=image,
    image_path=image_path,
    objects=objects,
    source=source,
  )


def validate_manifest(
  manifest_path: Path,
  classes: tuple[str, ...],
  *,
  check_files: bool = True,
) -> tuple[DatasetSummary, tuple[TrainingSample, ...]]:
  """Validate a Grounding DINO JSONL manifest and scene-level split isolation."""

  manifest_path = manifest_path.resolve()
  if not manifest_path.is_file():
    raise GroundingDinoDatasetError(f"manifest does not exist: {manifest_path}")
  class_ids = {name: index for index, name in enumerate(classes)}
  samples: list[TrainingSample] = []
  for line_number, raw_line in enumerate(manifest_path.read_text(encoding="utf-8").splitlines(), 1):
    if not raw_line.strip():
      continue
    try:
      value = json.loads(raw_line)
      sample = _parse_row(
        value,
        line_number=line_number,
        manifest_path=manifest_path,
        class_ids=class_ids,
        check_files=check_files,
      )
    except json.JSONDecodeError as exc:
      raise GroundingDinoDatasetError(f"line {line_number}: invalid JSON: {exc.msg}") from exc
    except GroundingDinoDatasetError as exc:
      if str(exc).startswith("line "):
        raise
      raise GroundingDinoDatasetError(f"line {line_number}: {exc}") from exc
    samples.append(sample)
  if not samples:
    raise GroundingDinoDatasetError("manifest contains no samples")

  sample_ids: set[str] = set()
  image_ids: dict[Path, str] = {}
  image_hashes: dict[str, str] = {}
  scene_splits: dict[str, str] = {}
  for sample in samples:
    if sample.sample_id in sample_ids:
      raise GroundingDinoDatasetError(f"duplicate sample_id: {sample.sample_id}")
    sample_ids.add(sample.sample_id)
    if sample.image_path in image_ids:
      raise GroundingDinoDatasetError(
        f"image is listed more than once: {sample.image} ({image_ids[sample.image_path]}, {sample.sample_id})"
      )
    image_ids[sample.image_path] = sample.sample_id
    if check_files:
      image_hash = _sha256(sample.image_path)
      previous_sample = image_hashes.setdefault(image_hash, sample.sample_id)
      if previous_sample != sample.sample_id:
        raise GroundingDinoDatasetError(
          f"image content is duplicated: {previous_sample} and {sample.sample_id}"
        )
    previous_split = scene_splits.setdefault(sample.scene_id, sample.split)
    if previous_split != sample.split:
      raise GroundingDinoDatasetError(
        f"scene leakage: {sample.scene_id} appears in {previous_split} and {sample.split}"
      )

  split_summaries: dict[str, SplitSummary] = {}
  for split in SPLITS:
    selected = [sample for sample in samples if sample.split == split]
    if not selected:
      if split in REQUIRED_SPLITS:
        raise GroundingDinoDatasetError(f"manifest must contain the {split} split")
      continue
    class_instances = {
      name: sum(target.class_name == name for sample in selected for target in sample.objects)
      for name in classes
    }
    missing = [name for name, count in class_instances.items() if count == 0]
    if split in REQUIRED_SPLITS and missing:
      raise GroundingDinoDatasetError(
        f"{split} split has no target boxes for classes: {', '.join(missing)}"
      )
    split_summaries[split] = SplitSummary(
      samples=len(selected),
      scenes=len({sample.scene_id for sample in selected}),
      negative_samples=sum(not sample.objects for sample in selected),
      instances=sum(len(sample.objects) for sample in selected),
      class_instances=class_instances,
    )

  sample_tuple = tuple(samples)
  summary = DatasetSummary(
    manifest=manifest_path.as_posix(),
    manifest_sha256=_sha256(manifest_path),
    dataset_sha256=_dataset_sha256(manifest_path, sample_tuple) if check_files else "not-computed",
    classes=classes,
    splits=split_summaries,
  )
  return summary, sample_tuple


def _number(value: object, name: str, kind: type[int] | type[float]) -> int | float:
  if isinstance(value, bool) or not isinstance(value, (int, float)):
    raise GroundingDinoDatasetError(f"training.{name} must be numeric")
  return kind(value)


def load_settings(path: Path, args: argparse.Namespace) -> TrainSettings:
  """Load and validate the YAML training configuration plus CLI overrides."""

  if not path.is_file():
    raise GroundingDinoDatasetError(f"config does not exist: {path}")
  try:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
  except yaml.YAMLError as exc:
    raise GroundingDinoDatasetError(f"config YAML is invalid: {exc}") from exc
  if not isinstance(payload, dict):
    raise GroundingDinoDatasetError("config YAML must contain a mapping")
  training = payload.get("training", {})
  if not isinstance(training, dict):
    raise GroundingDinoDatasetError("training must be a mapping")

  model = args.model or payload.get("model")
  manifest = args.manifest or payload.get("manifest")
  output_dir = args.output_dir or payload.get("output_dir", "runs/vision/train/grounding_dino")
  if not isinstance(model, str) or not model.strip():
    raise GroundingDinoDatasetError("model must be a Hugging Face ID or local directory")
  if not isinstance(manifest, (str, Path)) or not str(manifest).strip():
    raise GroundingDinoDatasetError("manifest must be a JSONL path")

  epochs = args.epochs if args.epochs is not None else _number(training.get("epochs", 30), "epochs", int)
  batch_size = (
    args.batch_size
    if args.batch_size is not None
    else _number(training.get("batch_size", 1), "batch_size", int)
  )
  accumulation = _number(
    training.get("gradient_accumulation_steps", 4),
    "gradient_accumulation_steps",
    int,
  )
  learning_rate = _number(training.get("learning_rate", 1e-5), "learning_rate", float)
  weight_decay = _number(training.get("weight_decay", 1e-4), "weight_decay", float)
  warmup_ratio = _number(training.get("warmup_ratio", 0.1), "warmup_ratio", float)
  max_grad_norm = _number(training.get("max_grad_norm", 1.0), "max_grad_norm", float)
  image_shortest_edge = _number(
    training.get("image_shortest_edge", 512),
    "image_shortest_edge",
    int,
  )
  image_longest_edge = _number(
    training.get("image_longest_edge", 768),
    "image_longest_edge",
    int,
  )
  num_workers = _number(training.get("num_workers", 0), "num_workers", int)
  seed = _number(training.get("seed", 42), "seed", int)
  amp = bool(training.get("amp", True)) and not args.no_amp
  values = (
    epochs,
    batch_size,
    accumulation,
    learning_rate,
    max_grad_norm,
    image_shortest_edge,
    image_longest_edge,
  )
  if any(value <= 0 for value in values) or weight_decay < 0 or num_workers < 0:
    raise GroundingDinoDatasetError(
      "epochs, batch_size, accumulation, learning_rate, and max_grad_norm must be positive; "
      "weight_decay and num_workers must be non-negative"
    )
  if warmup_ratio < 0 or warmup_ratio > 1:
    raise GroundingDinoDatasetError("training.warmup_ratio must be between 0 and 1")
  if image_longest_edge < image_shortest_edge:
    raise GroundingDinoDatasetError(
      "training.image_longest_edge must be greater than or equal to image_shortest_edge"
    )
  if batch_size != 1:
    raise GroundingDinoDatasetError(
      "training.batch_size must be 1 for the verified transformers Grounding DINO label-map path; "
      "increase gradient_accumulation_steps for a larger effective batch"
    )
  if sys.platform == "win32" and num_workers != 0:
    raise GroundingDinoDatasetError("training.num_workers must be 0 on Windows")

  return TrainSettings(
    model=model.strip(),
    manifest=Path(manifest),
    output_dir=Path(output_dir),
    classes=_clean_classes(payload.get("classes")),
    epochs=epochs,
    batch_size=batch_size,
    gradient_accumulation_steps=accumulation,
    learning_rate=learning_rate,
    weight_decay=weight_decay,
    warmup_ratio=warmup_ratio,
    max_grad_norm=max_grad_norm,
    image_shortest_edge=image_shortest_edge,
    image_longest_edge=image_longest_edge,
    num_workers=num_workers,
    seed=seed,
    device=args.device or str(training.get("device", "cuda:0")),
    amp=amp,
  )


def _normalized_device(value: str, torch_module: Any) -> str:
  if value.isdigit():
    value = f"cuda:{value}"
  if value.startswith("cuda") and not torch_module.cuda.is_available():
    raise GroundingDinoDatasetError("CUDA was requested but torch.cuda.is_available() is false")
  return value


def _coco_target(sample: TrainingSample, image_id: int) -> dict[str, Any]:
  annotations = []
  for target in sample.objects:
    x1, y1, x2, y2 = target.bbox_xyxy
    width = x2 - x1
    height = y2 - y1
    annotations.append(
      {
        "bbox": [x1, y1, width, height],
        "category_id": target.class_id,
        "area": width * height,
        "iscrowd": 0,
      }
    )
  return {"image_id": image_id, "annotations": annotations}


def _save_checkpoint(model: Any, processor: Any, destination: Path) -> str:
  destination.mkdir(parents=True, exist_ok=True)
  model.save_pretrained(destination)
  processor.save_pretrained(destination)
  digest = hashlib.sha256()
  for path in sorted((item for item in destination.rglob("*") if item.is_file())):
    digest.update(path.relative_to(destination).as_posix().encode("utf-8"))
    digest.update(bytes.fromhex(_sha256(path)))
  return digest.hexdigest()


def _move_batch(batch: dict[str, Any], device: str) -> dict[str, Any]:
  moved: dict[str, Any] = {}
  for key, value in batch.items():
    if key == "labels":
      moved[key] = [
        {name: tensor.to(device) if hasattr(tensor, "to") else tensor for name, tensor in label.items()}
        for label in value
      ]
    else:
      moved[key] = value.to(device) if hasattr(value, "to") else value
  return moved


def train(
  settings: TrainSettings,
  summary: DatasetSummary,
  samples: tuple[TrainingSample, ...],
) -> dict[str, Any]:
  """Run a direct full-parameter Grounding DINO fine-tuning loop."""

  try:
    import torch
    from PIL import Image
    from torch.utils.data import DataLoader, Dataset
    from transformers import AutoModelForZeroShotObjectDetection, AutoProcessor
    import transformers
  except ImportError as exc:
    raise GroundingDinoDatasetError(
      "Grounding DINO training requires torch, Pillow, scipy, and transformers from requirements-vision.txt"
    ) from exc

  device = _normalized_device(settings.device, torch)
  random.seed(settings.seed)
  torch.manual_seed(settings.seed)
  if torch.cuda.is_available():
    torch.cuda.manual_seed_all(settings.seed)

  class ManifestDataset(Dataset):
    def __init__(self, rows: list[TrainingSample]):
      self.rows = rows

    def __len__(self) -> int:
      return len(self.rows)

    def __getitem__(self, index: int) -> tuple[Any, dict[str, Any], str]:
      row = self.rows[index]
      with Image.open(row.image_path) as opened:
        image = opened.convert("RGB")
      width, height = image.size
      for target in row.objects:
        x1, y1, x2, y2 = target.bbox_xyxy
        if x2 > width or y2 > height:
          raise GroundingDinoDatasetError(
            f"box exceeds image bounds for {row.sample_id}: {target.bbox_xyxy} vs {image.size}"
          )
      return image, _coco_target(row, index), row.sample_id

  processor = AutoProcessor.from_pretrained(settings.model)
  model = AutoModelForZeroShotObjectDetection.from_pretrained(settings.model).to(device)

  def collate(batch: list[tuple[Any, dict[str, Any], str]]) -> dict[str, Any]:
    images, targets, sample_ids = zip(*batch)
    encoded = processor(
      images=list(images),
      text=[list(settings.classes) for _ in images],
      annotations=list(targets),
      size={
        "shortest_edge": settings.image_shortest_edge,
        "longest_edge": settings.image_longest_edge,
      },
      return_tensors="pt",
    )
    encoded["sample_ids"] = list(sample_ids)
    return encoded

  train_rows = [sample for sample in samples if sample.split == "train"]
  val_rows = [sample for sample in samples if sample.split == "val"]
  generator = torch.Generator().manual_seed(settings.seed)
  train_loader = DataLoader(
    ManifestDataset(train_rows),
    batch_size=settings.batch_size,
    shuffle=True,
    num_workers=settings.num_workers,
    collate_fn=collate,
    generator=generator,
  )
  val_loader = DataLoader(
    ManifestDataset(val_rows),
    batch_size=settings.batch_size,
    shuffle=False,
    num_workers=settings.num_workers,
    collate_fn=collate,
  )

  optimizer = torch.optim.AdamW(
    model.parameters(),
    lr=settings.learning_rate,
    weight_decay=settings.weight_decay,
  )
  updates_per_epoch = math.ceil(len(train_loader) / settings.gradient_accumulation_steps)
  total_updates = max(1, updates_per_epoch * settings.epochs)
  warmup_updates = round(total_updates * settings.warmup_ratio)

  def lr_lambda(step: int) -> float:
    if warmup_updates and step < warmup_updates:
      return float(step + 1) / float(warmup_updates)
    remaining = total_updates - warmup_updates
    return max(0.0, float(total_updates - step) / float(max(1, remaining)))

  scheduler = torch.optim.lr_scheduler.LambdaLR(optimizer, lr_lambda)
  amp_enabled = settings.amp and device.startswith("cuda")
  scaler = torch.amp.GradScaler("cuda", enabled=amp_enabled)
  destination = settings.output_dir.resolve()
  destination.mkdir(parents=True, exist_ok=True)
  history: list[dict[str, Any]] = []
  best_val_loss = math.inf
  best_checkpoint_sha256 = None
  optimizer_updates = 0
  skipped_optimizer_steps = 0
  if device.startswith("cuda"):
    torch.cuda.reset_peak_memory_stats(device)
  started = time.perf_counter()

  for epoch in range(1, settings.epochs + 1):
    epoch_started = time.perf_counter()
    model.train()
    optimizer.zero_grad(set_to_none=True)
    train_loss_sum = 0.0
    train_batches = 0
    for batch_index, batch in enumerate(train_loader, 1):
      batch.pop("sample_ids")
      moved = _move_batch(batch, device)
      with torch.autocast(device_type="cuda", dtype=torch.float16, enabled=amp_enabled):
        output = model(**moved)
        raw_loss = output.loss
      if raw_loss is None or not torch.isfinite(raw_loss):
        raise GroundingDinoDatasetError(f"non-finite training loss at epoch {epoch}, batch {batch_index}")
      loss = raw_loss / settings.gradient_accumulation_steps
      scaler.scale(loss).backward()
      train_loss_sum += raw_loss.detach().item()
      train_batches += 1
      should_update = (
        batch_index % settings.gradient_accumulation_steps == 0 or batch_index == len(train_loader)
      )
      if should_update:
        scaler.unscale_(optimizer)
        torch.nn.utils.clip_grad_norm_(model.parameters(), settings.max_grad_norm)
        scale_before = scaler.get_scale()
        scaler.step(optimizer)
        scaler.update()
        scale_after = scaler.get_scale()
        if not amp_enabled or scale_after >= scale_before:
          scheduler.step()
          optimizer_updates += 1
        else:
          skipped_optimizer_steps += 1
        optimizer.zero_grad(set_to_none=True)

    model.eval()
    val_loss_sum = 0.0
    val_batches = 0
    with torch.no_grad():
      for batch in val_loader:
        batch.pop("sample_ids")
        moved = _move_batch(batch, device)
        with torch.autocast(device_type="cuda", dtype=torch.float16, enabled=amp_enabled):
          output = model(**moved)
        if output.loss is None or not torch.isfinite(output.loss):
          raise GroundingDinoDatasetError(f"non-finite validation loss at epoch {epoch}")
        val_loss_sum += output.loss.detach().item()
        val_batches += 1

    train_loss = train_loss_sum / max(1, train_batches)
    val_loss = val_loss_sum / max(1, val_batches)
    epoch_row = {
      "epoch": epoch,
      "train_loss": train_loss,
      "val_loss": val_loss,
      "learning_rate": optimizer.param_groups[0]["lr"],
      "duration_s": round(time.perf_counter() - epoch_started, 3),
    }
    history.append(epoch_row)
    print(json.dumps(epoch_row, ensure_ascii=False), flush=True)
    if val_loss < best_val_loss:
      best_val_loss = val_loss
      best_checkpoint_sha256 = _save_checkpoint(model, processor, destination / "checkpoint-best")

  last_checkpoint_sha256 = _save_checkpoint(model, processor, destination / "checkpoint-last")
  elapsed = time.perf_counter() - started
  cuda_memory = None
  if device.startswith("cuda"):
    properties = torch.cuda.get_device_properties(device)
    cuda_memory = {
      "device_name": properties.name,
      "total_device_memory_bytes": properties.total_memory,
      "peak_allocated_bytes": torch.cuda.max_memory_allocated(device),
      "peak_reserved_bytes": torch.cuda.max_memory_reserved(device),
    }
  result = {
    "status": "completed" if optimizer_updates else "no_optimizer_update",
    "training_target": "GroundingDinoForObjectDetection",
    "fine_tuning": "full_parameter",
    "initial_model": settings.model,
    "prompt_classes": list(settings.classes),
    "class_id_contract": "class_labels index the prompt_classes list in the same order",
    "dataset": summary.to_dict(),
    "parameters": {
      "epochs": settings.epochs,
      "batch_size": settings.batch_size,
      "gradient_accumulation_steps": settings.gradient_accumulation_steps,
      "learning_rate": settings.learning_rate,
      "weight_decay": settings.weight_decay,
      "warmup_ratio": settings.warmup_ratio,
      "max_grad_norm": settings.max_grad_norm,
      "image_shortest_edge": settings.image_shortest_edge,
      "image_longest_edge": settings.image_longest_edge,
      "seed": settings.seed,
      "device": device,
      "amp": amp_enabled,
    },
    "optimizer_updates": optimizer_updates,
    "skipped_optimizer_steps": skipped_optimizer_steps,
    "software": {
      "torch": torch.__version__,
      "transformers": transformers.__version__,
    },
    "cuda_memory": cuda_memory,
    "best_val_loss": best_val_loss,
    "best_checkpoint": (destination / "checkpoint-best").as_posix(),
    "best_checkpoint_sha256": best_checkpoint_sha256,
    "last_checkpoint": (destination / "checkpoint-last").as_posix(),
    "last_checkpoint_sha256": last_checkpoint_sha256,
    "duration_s": round(elapsed, 3),
    "history": history,
  }
  summary_path = destination / "sensoragent_grounding_dino_train_summary.json"
  summary_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
  print(json.dumps(result, ensure_ascii=False, indent=2))
  return result


def _parser() -> argparse.ArgumentParser:
  parser = argparse.ArgumentParser(
    description="Validate data or directly fine-tune Grounding DINO on text-grounded boxes."
  )
  parser.add_argument(
    "--config",
    type=Path,
    default=Path("configs/vision_train_grounding_dino.example.yaml"),
  )
  parser.add_argument("--manifest", type=Path, help="Override the JSONL manifest path.")
  parser.add_argument("--model", help="Override the Hugging Face model ID or local model directory.")
  parser.add_argument("--output-dir", type=Path, help="Override the local run directory.")
  parser.add_argument("--device", help="Examples: 0, cuda:0, or cpu.")
  parser.add_argument("--epochs", type=int)
  parser.add_argument("--batch-size", type=int)
  parser.add_argument("--no-amp", action="store_true")
  parser.add_argument(
    "--allow-missing-files",
    action="store_true",
    help="Validate a template structure without hashing local images; training still requires files.",
  )
  parser.add_argument("--dry-run", action="store_true", help="Validate data without loading a model.")
  return parser


def main(argv: list[str] | None = None) -> int:
  args = _parser().parse_args(argv)
  try:
    settings = load_settings(args.config, args)
    summary, samples = validate_manifest(
      settings.manifest,
      settings.classes,
      check_files=not args.allow_missing_files,
    )
    if args.dry_run:
      print(
        json.dumps(
          {
            "valid": True,
            "training_target": "GroundingDinoForObjectDetection",
            "dataset": summary.to_dict(),
          },
          ensure_ascii=False,
          indent=2,
        )
      )
      return 0
    if args.allow_missing_files:
      raise GroundingDinoDatasetError("--allow-missing-files can only be used with --dry-run")
    result = train(settings, summary, samples)
    if result["optimizer_updates"] == 0:
      print(
        "no optimizer update was applied; retry with more batches, a lower AMP scale, or --no-amp",
        file=sys.stderr,
      )
      return 3
  except GroundingDinoDatasetError as exc:
    print(json.dumps({"valid": False, "error": str(exc)}, ensure_ascii=False, indent=2))
    return 2
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
