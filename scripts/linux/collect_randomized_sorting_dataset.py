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
PARTS = {
  "block": ("metal_block_01", 0.33, 0.0),
  "stepped_shaft": ("metal_stepped_shaft_01", 0.33, math.pi / 2.0),
  "hollow_sleeve": ("metal_hollow_sleeve_01", 0.3225, 0.0),
  "roller": ("metal_roller_01", 0.32, math.pi / 2.0),
  "hex_nut": ("metal_hex_nut_01", 0.3125, 0.0),
  "short_bolt": ("metal_short_bolt_01", 0.3275, 0.0),
  "flange_bushing": ("metal_flange_bushing_01", 0.325, 0.0),
}
T_BASE_CAMERA = [[0.0, 1.0, 0.0, -0.34], [1.0, 0.0, 0.0, 0.0], [0.0, 0.0, -1.0, 0.88], [0.0, 0.0, 0.0, 1.0]]
T_WORLD_CAMERA = [[0.0, -1.0, 0.0, 0.34], [-1.0, 0.0, 0.0, 0.0], [0.0, 0.0, -1.0, 1.06], [0.0, 0.0, 0.0, 1.0]]


def _pose_request(name: str, x: float, y: float, z: float, pitch: float, yaw: float) -> str:
  half_yaw = yaw / 2.0
  half_pitch = pitch / 2.0
  qx = -math.sin(half_yaw) * math.sin(half_pitch)
  qy = math.cos(half_yaw) * math.sin(half_pitch)
  qz = math.sin(half_yaw) * math.cos(half_pitch)
  qw = math.cos(half_yaw) * math.cos(half_pitch)
  return (
    f'name: "{name}" position {{ x: {x:.5f} y: {y:.5f} z: {z:.5f} }} '
    f"orientation {{ x: {qx:.8f} y: {qy:.8f} z: {qz:.8f} w: {qw:.8f} }}"
  )


def _set_pose(name: str, x: float, y: float, z: float, pitch: float, yaw: float) -> None:
  for attempt in range(3):
    result = subprocess.run(
      [
        "ign", "service", "-s", "/world/empty/set_pose",
        "--reqtype", "ignition.msgs.Pose", "--reptype", "ignition.msgs.Boolean",
        "--timeout", "5000", "--req", _pose_request(name, x, y, z, pitch, yaw),
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


def main() -> int:
  parser = argparse.ArgumentParser(description="Capture randomized industrial sorting RGB-D samples.")
  parser.add_argument("--dataset-dir", type=Path, default=ROOT / "data" / "vision" / "sorting_v0")
  parser.add_argument("--count", type=int, default=20)
  parser.add_argument("--seed", type=int, default=42)
  parser.add_argument("--occlusion-rate", type=float, default=0.0)
  parser.add_argument("--settle-seconds", type=float, default=1.0)
  args = parser.parse_args()
  if args.count <= 0 or not 0.0 <= args.occlusion_rate <= 1.0:
    raise ValueError("count must be positive and occlusion-rate must be within 0..1")

  dataset_dir = args.dataset_dir.resolve()
  images_dir = dataset_dir / "roboflow_images"
  raw_dir = dataset_dir / "raw"
  images_dir.mkdir(parents=True, exist_ok=True)
  raw_dir.mkdir(parents=True, exist_ok=True)
  rng = random.Random(args.seed)
  manifest_path = dataset_dir / "randomized_manifest.jsonl"
  existing_count = len(manifest_path.read_text(encoding="utf-8").splitlines()) if manifest_path.exists() else 0

  for index in range(existing_count + 1, existing_count + args.count + 1):
    # Keep samples out of the bin and robot silhouette; these points remain
    # separated enough for clear first-pass instance annotations.
    points = [(x, y) for x in (0.16, 0.24, 0.32) for y in (-0.22, -0.11, 0.0, 0.11)]
    rng.shuffle(points)
    poses = {}
    for (label, (entity, z, pitch)), (x, y) in zip(PARTS.items(), points):
      yaw = rng.uniform(-math.pi, math.pi)
      if poses and rng.random() < args.occlusion_rate:
        prior = rng.choice(list(poses.values()))
        x, y = prior["position"][:2]
      _set_pose(entity, x, y, z, pitch, yaw)
      poses[label] = {"entity": entity, "position": [x, y, z], "pitch": pitch, "yaw": yaw}
    time.sleep(args.settle_seconds)
    sample_raw = raw_dir / f"random_{index:04d}"
    subprocess.run(["python3", str(CAPTURE_SCRIPT), "--out-dir", str(sample_raw)], cwd=ROOT, check=True)
    image = images_dir / f"sorting_scene_{index + 1:04d}.png"
    capture = json.loads((sample_raw / "manifest.json").read_text(encoding="utf-8"))
    capture["T_base_camera"] = capture.get("T_base_camera") or T_BASE_CAMERA
    capture["T_world_camera"] = capture.get("T_world_camera") or T_WORLD_CAMERA
    (sample_raw / "manifest.json").write_text(json.dumps(capture, ensure_ascii=False, indent=2), encoding="utf-8")
    shutil.copy2(ROOT / capture["png_path"], image)
    with manifest_path.open("a", encoding="utf-8") as stream:
      stream.write(json.dumps({"sample_id": image.stem, "image": str(image.relative_to(dataset_dir)), "poses": poses}, ensure_ascii=False) + "\n")
    print(f"captured {image}")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
