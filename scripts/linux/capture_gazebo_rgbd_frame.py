#!/usr/bin/env python3
"""Capture one Gazebo industrial RGB-D frame to files.

Run this with the ROS 2 Python environment after Gazebo is running:

  python3 scripts/linux/capture_gazebo_rgbd_frame.py --out-dir logs/vision/latest
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import CameraInfo, Image


class FrameCapture(Node):
  def __init__(self, image_topic: str, depth_topic: str, camera_info_topic: str) -> None:
    super().__init__("sensoragent_rgbd_frame_capture")
    self.image: Image | None = None
    self.depth: Image | None = None
    self.camera_info: CameraInfo | None = None
    self.create_subscription(Image, image_topic, self._on_image, 10)
    self.create_subscription(Image, depth_topic, self._on_depth, 10)
    self.create_subscription(CameraInfo, camera_info_topic, self._on_camera_info, 10)

  def _on_image(self, message: Image) -> None:
    self.image = message

  def _on_depth(self, message: Image) -> None:
    self.depth = message

  def _on_camera_info(self, message: CameraInfo) -> None:
    self.camera_info = message

  def ready(self) -> bool:
    return self.image is not None and self.depth is not None and self.camera_info is not None


def _decode_image(message: Image) -> np.ndarray:
  data = np.frombuffer(message.data, dtype=np.uint8)
  channels_by_encoding = {
    "rgb8": 3,
    "bgr8": 3,
    "rgba8": 4,
    "bgra8": 4,
  }
  channels = channels_by_encoding.get(message.encoding)
  if channels is None:
    raise ValueError(f"Unsupported RGB image encoding: {message.encoding}")
  image = data.reshape((message.height, message.step // channels, channels))[:, : message.width, :]
  if message.encoding == "bgr8":
    image = image[:, :, ::-1]
  elif message.encoding == "bgra8":
    image = image[:, :, [2, 1, 0, 3]]
  if image.shape[2] == 4:
    image = image[:, :, :3]
  return image.copy()


def _decode_depth(message: Image) -> np.ndarray:
  if message.encoding == "32FC1":
    dtype = np.float32
    scale = 1.0
  elif message.encoding == "16UC1":
    dtype = np.uint16
    scale = 0.001
  else:
    raise ValueError(f"Unsupported depth image encoding: {message.encoding}")
  values_per_row = message.step // np.dtype(dtype).itemsize
  depth = np.frombuffer(message.data, dtype=dtype).reshape((message.height, values_per_row))
  depth = depth[:, : message.width].astype(np.float32) * scale
  return depth.copy()


def _camera_info_json(message: CameraInfo) -> dict:
  return {
    "width": int(message.width),
    "height": int(message.height),
    "k": [float(value) for value in message.k],
    "d": [float(value) for value in message.d],
    "distortion_model": message.distortion_model,
    "frame_id": message.header.frame_id,
  }


def _write_ppm(path: Path, image: np.ndarray) -> None:
  path.parent.mkdir(parents=True, exist_ok=True)
  with path.open("wb") as stream:
    stream.write(f"P6\n{image.shape[1]} {image.shape[0]}\n255\n".encode("ascii"))
    stream.write(image.astype(np.uint8).tobytes())


def main() -> int:
  parser = argparse.ArgumentParser(description="Capture one industrial Gazebo RGB-D frame.")
  parser.add_argument("--out-dir", type=Path, default=Path("logs/vision/latest"))
  parser.add_argument("--image-topic", default="/industrial_camera/image")
  parser.add_argument("--depth-topic", default="/industrial_camera/depth_image")
  parser.add_argument("--camera-info-topic", default="/industrial_camera/camera_info")
  parser.add_argument("--timeout", type=float, default=10.0)
  args = parser.parse_args()

  rclpy.init()
  node = FrameCapture(args.image_topic, args.depth_topic, args.camera_info_topic)
  deadline = time.monotonic() + args.timeout
  try:
    while time.monotonic() < deadline and not node.ready():
      rclpy.spin_once(node, timeout_sec=0.1)
    if not node.ready():
      raise TimeoutError("Timed out waiting for RGB, depth, and CameraInfo messages.")

    image = _decode_image(node.image)
    depth = _decode_depth(node.depth)
    camera_info = _camera_info_json(node.camera_info)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    np.save(args.out_dir / "rgb.npy", image)
    _write_ppm(args.out_dir / "rgb.ppm", image)
    np.save(args.out_dir / "depth.npy", depth)
    (args.out_dir / "camera_info.json").write_text(
      json.dumps(camera_info, ensure_ascii=False, indent=2),
      encoding="utf-8",
    )
    manifest = {
      "image_path": str(args.out_dir / "rgb.npy"),
      "preview_path": str(args.out_dir / "rgb.ppm"),
      "depth_path": str(args.out_dir / "depth.npy"),
      "camera_info_path": str(args.out_dir / "camera_info.json"),
      "image_shape": list(image.shape),
      "depth_shape": list(depth.shape),
    }
    (args.out_dir / "manifest.json").write_text(
      json.dumps(manifest, ensure_ascii=False, indent=2),
      encoding="utf-8",
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0
  finally:
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
  raise SystemExit(main())
