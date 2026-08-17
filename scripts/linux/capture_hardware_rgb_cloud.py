#!/usr/bin/env python3
"""Capture one physical RGB frame and its matching PointCloud2 without moving hardware."""

from __future__ import annotations

import argparse
from collections import deque
import json
import time
from pathlib import Path

import numpy as np
from PIL import Image as PilImage
import rclpy
from rclpy.node import Node
from rclpy.duration import Duration
from rclpy.time import Time
from sensor_msgs.msg import Image, PointCloud2
from tf2_ros import Buffer, TransformException, TransformListener


class FrameCapture(Node):
  def __init__(self, image_topic: str, cloud_topic: str) -> None:
    super().__init__("sensoragent_hardware_frame_capture")
    self.images: deque[Image] = deque(maxlen=20)
    self.clouds: deque[PointCloud2] = deque(maxlen=20)
    self.tf_buffer = Buffer()
    self.tf_listener = TransformListener(self.tf_buffer, self)
    self.create_subscription(Image, image_topic, self._on_image, 10)
    self.create_subscription(PointCloud2, cloud_topic, self._on_cloud, 10)

  def _on_image(self, message: Image) -> None:
    self.images.append(message)

  def _on_cloud(self, message: PointCloud2) -> None:
    self.clouds.append(message)

  def synchronized_pair(self, max_skew_ns: int) -> tuple[Image, PointCloud2] | None:
    pairs = [
        (abs((image.header.stamp.sec - cloud.header.stamp.sec) * 1_000_000_000 + image.header.stamp.nanosec - cloud.header.stamp.nanosec), image, cloud)
        for image in self.images for cloud in self.clouds
    ]
    if not pairs:
      return None
    skew_ns, image, cloud = min(pairs, key=lambda pair: pair[0])
    return (image, cloud) if skew_ns <= max_skew_ns else None


def _decode_bgr_image(message: Image) -> np.ndarray:
  if message.encoding != "bgr8":
    raise ValueError(f"Expected bgr8 image, got {message.encoding}")
  values = np.frombuffer(message.data, dtype=np.uint8)
  image = values.reshape((message.height, message.step // 3, 3))[:, : message.width, :]
  return image[:, :, ::-1].copy()


def _decode_xyzuv(message: PointCloud2) -> np.ndarray:
  names = [field.name for field in message.fields]
  if names[:5] != ["x", "y", "z", "u", "v"] or message.point_step != 20:
    raise ValueError(f"Expected float32 xyzuv PointCloud2, got fields={names}, point_step={message.point_step}")
  return np.frombuffer(message.data, dtype=np.float32).reshape((-1, 5)).copy()


def _transform_matrix(transform) -> list[list[float]]:
  rotation = transform.transform.rotation
  x, y, z, w = rotation.x, rotation.y, rotation.z, rotation.w
  translation = transform.transform.translation
  return [
    [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w), translation.x],
    [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w), translation.y],
    [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y), translation.z],
    [0.0, 0.0, 0.0, 1.0],
  ]


def main() -> int:
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--out-dir", type=Path, default=Path("logs/vision/hardware_latest"))
  parser.add_argument("--image-topic", default="/vision/raw")
  parser.add_argument("--cloud-topic", default="/vision/cloud")
  parser.add_argument("--base-frame", default="base_link")
  parser.add_argument("--max-skew-ms", type=float, default=50.0)
  parser.add_argument("--timeout", type=float, default=10.0)
  args = parser.parse_args()
  rclpy.init()
  node = FrameCapture(args.image_topic, args.cloud_topic)
  try:
    # Fill the TF buffer before selecting a frame pair; otherwise a fresh node
    # can receive an image before it has any base-to-tool transform history.
    warmup_deadline = time.monotonic() + 1.2
    while time.monotonic() < warmup_deadline:
      rclpy.spin_once(node, timeout_sec=0.1)
    node.images.clear()
    node.clouds.clear()
    deadline = time.monotonic() + args.timeout
    pair = None
    while time.monotonic() < deadline and pair is None:
      rclpy.spin_once(node, timeout_sec=0.1)
      pair = node.synchronized_pair(round(args.max_skew_ms * 1_000_000))
    if pair is None:
      raise TimeoutError("Timed out waiting for time-synchronized RGB image and point cloud")
    image_message, cloud_message = pair
    image = _decode_bgr_image(image_message)
    cloud = _decode_xyzuv(cloud_message)
    cloud_stamp = Time.from_msg(cloud_message.header.stamp)
    transform = None
    transform_error: TransformException | None = None
    transform_deadline = time.monotonic() + 3.0
    while time.monotonic() < transform_deadline and transform is None:
      try:
        transform = node.tf_buffer.lookup_transform(
            args.base_frame, cloud_message.header.frame_id, cloud_stamp, timeout=Duration(seconds=0.2)
        )
      except TransformException as exc:
        transform_error = exc
        rclpy.spin_once(node, timeout_sec=0.1)
    if transform is None and transform_error is not None:
      try:
        transform = node.tf_buffer.lookup_transform(
            args.base_frame, cloud_message.header.frame_id, Time(), timeout=Duration(seconds=0.2)
        )
        node.get_logger().warning(
            f"Using latest TF for {args.base_frame} <- {cloud_message.header.frame_id} after timestamp lookup failed: {transform_error}"
        )
      except TransformException as exc:
        transform_error = exc
    if transform is None:
      raise RuntimeError(
          f"Missing TF {args.base_frame} <- {cloud_message.header.frame_id}: {transform_error}"
      )
    args.out_dir.mkdir(parents=True, exist_ok=True)
    np.save(args.out_dir / "rgb.npy", image)
    PilImage.fromarray(image).save(args.out_dir / "rgb.png")
    np.save(args.out_dir / "cloud_xyzuv.npy", cloud)
    manifest = {
      "image_path": str(args.out_dir / "rgb.npy"),
      "png_path": str(args.out_dir / "rgb.png"),
        "cloud_path": str(args.out_dir / "cloud_xyzuv.npy"),
        "image_shape": list(image.shape),
        "cloud_points": int(len(cloud)),
        "image_frame": image_message.header.frame_id,
        "cloud_frame": cloud_message.header.frame_id,
        "image_stamp_ns": int(image_message.header.stamp.sec * 1_000_000_000 + image_message.header.stamp.nanosec),
        "cloud_stamp_ns": int(cloud_message.header.stamp.sec * 1_000_000_000 + cloud_message.header.stamp.nanosec),
        "sync_skew_ms": abs((image_message.header.stamp.sec - cloud_message.header.stamp.sec) * 1_000 + (image_message.header.stamp.nanosec - cloud_message.header.stamp.nanosec) / 1_000_000),
        "T_base_camera": _transform_matrix(transform),
    }
    (args.out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    return 0
  finally:
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
  raise SystemExit(main())
