#!/usr/bin/env python3
"""Interactively collect Gazebo RGB-D frames for Roboflow annotation.

Run after the Gazebo industrial scene is ready:

  python3 scripts/linux/collect_gazebo_dataset.py

Menu:

  1  Capture the current camera frame
  2  Show collection progress
  0  Exit
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
CAPTURE_SCRIPT = ROOT / "scripts" / "linux" / "capture_gazebo_rgbd_frame.py"


def _completed_indices(images_dir: Path) -> list[int]:
  indices = []
  for path in images_dir.glob("red_block_*.png"):
    suffix = path.stem.removeprefix("red_block_")
    if suffix.isdigit():
      indices.append(int(suffix))
  return sorted(indices)


def _next_index(images_dir: Path) -> int:
  indices = _completed_indices(images_dir)
  return indices[-1] + 1 if indices else 1


def _relative(path: Path, root: Path) -> str:
  return path.resolve().relative_to(root.resolve()).as_posix()


def _append_manifest(
  manifest_path: Path,
  *,
  dataset_dir: Path,
  index: int,
  class_name: str,
  image_path: Path,
  raw_dir: Path,
) -> None:
  fields = (
    "capture_index",
    "scene_id",
    "captured_at",
    "class_name",
    "image",
    "raw_dir",
    "depth",
    "camera_info",
    "capture_manifest",
    "annotation_status",
  )
  write_header = not manifest_path.exists()
  manifest_path.parent.mkdir(parents=True, exist_ok=True)
  with manifest_path.open("a", encoding="utf-8", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields)
    if write_header:
      writer.writeheader()
    writer.writerow(
      {
        "capture_index": index,
        "scene_id": f"scene_{index:03d}",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "class_name": class_name,
        "image": _relative(image_path, dataset_dir),
        "raw_dir": _relative(raw_dir, dataset_dir),
        "depth": _relative(raw_dir / "depth.npy", dataset_dir),
        "camera_info": _relative(raw_dir / "camera_info.json", dataset_dir),
        "capture_manifest": _relative(raw_dir / "manifest.json", dataset_dir),
        "annotation_status": "pending",
      }
    )


def _capture(
  args: argparse.Namespace,
  *,
  dataset_dir: Path,
  images_dir: Path,
  raw_root: Path,
) -> bool:
  index = _next_index(images_dir)
  raw_dir = raw_root / f"scene_{index:03d}"
  image_path = images_dir / f"red_block_{index:03d}.png"
  command = [
    args.ros_python,
    str(CAPTURE_SCRIPT),
    "--out-dir",
    str(raw_dir),
    "--image-topic",
    args.image_topic,
    "--depth-topic",
    args.depth_topic,
    "--camera-info-topic",
    args.camera_info_topic,
    "--timeout",
    str(args.timeout),
  ]

  print(f"[capture] scene={index:03d} waiting for Gazebo camera...", flush=True)
  result = subprocess.run(
    command,
    cwd=ROOT,
    capture_output=True,
    text=True,
    check=False,
  )
  if result.returncode != 0:
    print("[capture] failed", file=sys.stderr)
    if result.stderr.strip():
      print(result.stderr.strip(), file=sys.stderr)
    elif result.stdout.strip():
      print(result.stdout.strip(), file=sys.stderr)
    if raw_dir.exists():
      shutil.rmtree(raw_dir)
    return False

  capture_manifest = json.loads((raw_dir / "manifest.json").read_text(encoding="utf-8"))
  generated_png = Path(capture_manifest["png_path"])
  if not generated_png.is_absolute():
    generated_png = ROOT / generated_png
  images_dir.mkdir(parents=True, exist_ok=True)
  shutil.copy2(generated_png, image_path)
  _append_manifest(
    dataset_dir / "capture_manifest.csv",
    dataset_dir=dataset_dir,
    index=index,
    class_name=args.class_name,
    image_path=image_path,
    raw_dir=raw_dir,
  )
  count = len(_completed_indices(images_dir))
  print(f"[capture] saved {image_path}")
  print(f"[capture] progress {count}/{args.target_count}")
  return True


def _show_status(dataset_dir: Path, images_dir: Path, target_count: int) -> None:
  indices = _completed_indices(images_dir)
  print()
  print(f"Dataset: {dataset_dir}")
  print(f"Roboflow images: {images_dir}")
  print(f"Captured: {len(indices)}/{target_count}")
  print(f"Next scene: {_next_index(images_dir):03d}")
  print()


def _parser() -> argparse.ArgumentParser:
  parser = argparse.ArgumentParser(
    description="Interactively collect Gazebo camera frames into a Roboflow-ready dataset.",
  )
  parser.add_argument(
    "--dataset-dir",
    type=Path,
    default=ROOT / "data" / "vision" / "red_block_v0",
  )
  parser.add_argument("--class-name", default="red block")
  parser.add_argument("--target-count", type=int, default=20)
  parser.add_argument("--ros-python", default="python3")
  parser.add_argument("--image-topic", default="/industrial_camera/image")
  parser.add_argument("--depth-topic", default="/industrial_camera/depth_image")
  parser.add_argument("--camera-info-topic", default="/industrial_camera/camera_info")
  parser.add_argument("--timeout", type=float, default=10.0)
  return parser


def main(argv: list[str] | None = None) -> int:
  args = _parser().parse_args(argv)
  if args.target_count <= 0:
    raise ValueError("--target-count must be positive")

  dataset_dir = args.dataset_dir.resolve()
  images_dir = dataset_dir / "roboflow_images"
  raw_root = dataset_dir / "raw"
  images_dir.mkdir(parents=True, exist_ok=True)
  raw_root.mkdir(parents=True, exist_ok=True)

  print("Gazebo red block dataset collector")
  print("Move the object in Gazebo, return here, then press 1 to capture.")
  _show_status(dataset_dir, images_dir, args.target_count)

  while True:
    choice = input("[1] capture  [2] status  [0] exit > ").strip().casefold()
    if choice in {"1", "c", "capture", ""}:
      _capture(
        args,
        dataset_dir=dataset_dir,
        images_dir=images_dir,
        raw_root=raw_root,
      )
    elif choice in {"2", "s", "status"}:
      _show_status(dataset_dir, images_dir, args.target_count)
    elif choice in {"0", "q", "quit", "exit"}:
      _show_status(dataset_dir, images_dir, args.target_count)
      print("Collection stopped. Existing captures are preserved.")
      return 0
    else:
      print("Unknown command. Use 1 to capture, 2 for status, or 0 to exit.")


if __name__ == "__main__":
  raise SystemExit(main())
