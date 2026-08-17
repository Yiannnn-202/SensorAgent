#!/usr/bin/env python3
"""Randomize Gazebo sorting parts and capture RGB-D annotation samples."""

from __future__ import annotations

import argparse
import json
import math
import random
import shutil
import subprocess
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CAPTURE_SCRIPT = ROOT / "scripts" / "linux" / "capture_gazebo_rgbd_frame.py"
PARTS = tuple(
  {
    "class_name": class_name,
    "instance_id": f"{class_name}_{index:02d}",
    "entity": f"metal_{class_name}_{index:02d}",
    "z": z,
    "roll": roll,
    "pitch": pitch,
  }
  for class_name, z, roll, pitch in (
    ("roller", 0.320, 0.0, math.pi / 2.0),
    ("hex_nut", 0.3125, 0.0, 0.0),
    # The scene presents bolts head-down with the narrow shaft pointing up.
    ("short_bolt", 0.3325, math.pi, 0.0),
  )
  for index in range(1, 4)
)
GRID_POINTS = tuple(
  (x, y)
  for y in (-0.22, -0.13, -0.04)
  for x in (0.1625, 0.2625, 0.3625)
)
CLASS_NAMES = ("roller", "hex_nut", "short_bolt")
PARKING_POINTS = {
  str(part["instance_id"]): (
    1.20 + 0.10 * index,
    0.80,
    float(part["z"]),
  )
  for index, part in enumerate(PARTS)
}
T_BASE_CAMERA = [[0.0, 1.0, 0.0, -0.34], [1.0, 0.0, 0.0, 0.0], [0.0, 0.0, -1.0, 0.88], [0.0, 0.0, 0.0, 1.0]]
T_WORLD_CAMERA = [[0.0, -1.0, 0.0, 0.34], [-1.0, 0.0, 0.0, 0.0], [0.0, 0.0, -1.0, 1.06], [0.0, 0.0, 0.0, 1.0]]


def _quaternion_from_euler(
  roll: float,
  pitch: float,
  yaw: float,
) -> tuple[float, float, float, float]:
  cr, sr = math.cos(roll / 2.0), math.sin(roll / 2.0)
  cp, sp = math.cos(pitch / 2.0), math.sin(pitch / 2.0)
  cy, sy = math.cos(yaw / 2.0), math.sin(yaw / 2.0)
  return (
    sr * cp * cy - cr * sp * sy,
    cr * sp * cy + sr * cp * sy,
    cr * cp * sy - sr * sp * cy,
    cr * cp * cy + sr * sp * sy,
  )


def _pose_request(
  name: str,
  x: float,
  y: float,
  z: float,
  roll: float,
  pitch: float,
  yaw: float,
) -> str:
  qx, qy, qz, qw = _quaternion_from_euler(roll, pitch, yaw)
  return (
    f'name: "{name}" position {{ x: {x:.5f} y: {y:.5f} z: {z:.5f} }} '
    f"orientation {{ x: {qx:.8f} y: {qy:.8f} z: {qz:.8f} w: {qw:.8f} }}"
  )


def _set_pose(
  name: str,
  x: float,
  y: float,
  z: float,
  roll: float,
  pitch: float,
  yaw: float,
) -> None:
  for attempt in range(3):
    result = subprocess.run(
      [
        "ign", "service", "-s", "/world/empty/set_pose",
        "--reqtype", "ignition.msgs.Pose", "--reptype", "ignition.msgs.Boolean",
        "--timeout", "5000", "--req",
        _pose_request(name, x, y, z, roll, pitch, yaw),
      ],
      capture_output=True,
      text=True,
      check=False,
    )
    if result.returncode == 0 and "true" in result.stdout:
      return
    if attempt < 2:
      time.sleep(0.5)
  raise RuntimeError(f"set_pose failed for {name}: {result.stderr or result.stdout}")


def _randomized_poses(
  rng: random.Random,
  *,
  position_jitter: float,
  min_per_class: int,
  max_per_class: int,
  allow_empty_scene: bool,
) -> tuple[dict[str, dict], dict[str, int]]:
  counts = {
    class_name: rng.randint(min_per_class, max_per_class)
    for class_name in CLASS_NAMES
  }
  if not allow_empty_scene and sum(counts.values()) == 0:
    counts[rng.choice(CLASS_NAMES)] = 1

  selected_ids: set[str] = set()
  for class_name in CLASS_NAMES:
    class_parts = [
      part for part in PARTS if part["class_name"] == class_name
    ]
    selected_ids.update(
      str(part["instance_id"])
      for part in rng.sample(class_parts, counts[class_name])
    )

  points = list(GRID_POINTS)
  rng.shuffle(points)
  poses: dict[str, dict] = {}
  active_points = iter(points)
  for part in PARTS:
    instance_id = str(part["instance_id"])
    active = instance_id in selected_ids
    if active:
      grid_x, grid_y = next(active_points)
      x = grid_x + rng.uniform(-position_jitter, position_jitter)
      y = grid_y + rng.uniform(-position_jitter, position_jitter)
      z = float(part["z"])
      yaw = rng.uniform(-math.pi, math.pi)
    else:
      x, y, z = PARKING_POINTS[instance_id]
      yaw = 0.0
    poses[instance_id] = {
      "class_name": part["class_name"],
      "entity": part["entity"],
      "active": active,
      "position": [x, y, z],
      "roll": part["roll"],
      "pitch": part["pitch"],
      "yaw": yaw,
    }
  return poses, counts


def main() -> int:
  parser = argparse.ArgumentParser(description="Capture randomized industrial sorting RGB-D samples.")
  parser.add_argument("--dataset-dir", type=Path, default=ROOT / "data" / "vision" / "sorting_v0")
  parser.add_argument("--count", type=int, default=100)
  parser.add_argument("--seed", type=int, default=42)
  parser.add_argument(
    "--min-per-class",
    type=int,
    default=0,
    help="Minimum visible instances sampled independently for each class.",
  )
  parser.add_argument(
    "--max-per-class",
    type=int,
    default=3,
    help="Maximum visible instances sampled independently for each class.",
  )
  parser.add_argument(
    "--allow-empty-scene",
    action="store_true",
    help="Allow all three class counts to be zero in one image.",
  )
  parser.add_argument(
    "--position-jitter",
    type=float,
    default=0.0075,
    help="Maximum XY jitter around each safe grid point in metres.",
  )
  parser.add_argument("--settle-seconds", type=float, default=1.0)
  parser.add_argument("--ros-python", default="python3")
  args = parser.parse_args()
  if (
    args.count <= 0
    or not 0 <= args.min_per_class <= args.max_per_class <= 3
    or not 0.0 <= args.position_jitter <= 0.01
  ):
    raise ValueError(
      "count must be positive, class counts must satisfy 0 <= min <= max <= 3, "
      "and position-jitter must be within 0..0.01"
    )

  dataset_dir = args.dataset_dir.resolve()
  images_dir = dataset_dir / "roboflow_images"
  raw_dir = dataset_dir / "raw"
  images_dir.mkdir(parents=True, exist_ok=True)
  raw_dir.mkdir(parents=True, exist_ok=True)
  manifest_path = dataset_dir / "randomized_manifest.jsonl"
  existing_count = len(manifest_path.read_text(encoding="utf-8").splitlines()) if manifest_path.exists() else 0

  for index in range(existing_count + 1, existing_count + args.count + 1):
    rng = random.Random(f"{args.seed}:{index}")
    poses, class_counts = _randomized_poses(
      rng,
      position_jitter=args.position_jitter,
      min_per_class=args.min_per_class,
      max_per_class=args.max_per_class,
      allow_empty_scene=args.allow_empty_scene,
    )
    for pose in poses.values():
      _set_pose(
        pose["entity"],
        *pose["position"],
        pose["roll"],
        pose["pitch"],
        pose["yaw"],
      )
    time.sleep(args.settle_seconds)
    sample_raw = raw_dir / f"random_{index:04d}"
    subprocess.run(
      [args.ros_python, str(CAPTURE_SCRIPT), "--out-dir", str(sample_raw)],
      cwd=ROOT,
      check=True,
    )
    image = images_dir / f"sorting_scene_{index:04d}.png"
    capture = json.loads((sample_raw / "manifest.json").read_text(encoding="utf-8"))
    capture["T_base_camera"] = capture.get("T_base_camera") or T_BASE_CAMERA
    capture["T_world_camera"] = capture.get("T_world_camera") or T_WORLD_CAMERA
    (sample_raw / "manifest.json").write_text(json.dumps(capture, ensure_ascii=False, indent=2), encoding="utf-8")
    shutil.copy2(ROOT / capture["png_path"], image)
    with manifest_path.open("a", encoding="utf-8") as stream:
      stream.write(
        json.dumps(
          {
            "sample_id": image.stem,
            "image": str(image.relative_to(dataset_dir)),
            "class_counts": class_counts,
            "empty_classes": [
              class_name
              for class_name, count in class_counts.items()
              if count == 0
            ],
            "poses": poses,
          },
          ensure_ascii=False,
        )
        + "\n"
      )
    print(f"captured {image} counts={class_counts}")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
