#!/usr/bin/env python3

"""ROS 2 → object_targets: stream aligned RGB + cloud over one WebSocket.

Subscribes to ``/vision/raw`` and ``/vision/cloud`` (from ``dep_cam``),
aligns by timestamp, and pushes snapshots to ``/ws/perception`` on the
object_targets service (default ``ws://127.0.0.1:20012/ws/perception``).

Reconnects automatically if the connection drops.
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
from rclpy.time import Time
from sensor_msgs.msg import Image, PointCloud2
from sensor_msgs_py import point_cloud2
from std_msgs.msg import Empty
from tf2_ros import Buffer, TransformListener

from rm_ros_interfaces.msg import Armstate

try:
  import websockets
except ImportError:
  websockets = None

DEFAULT_RGB_TOPIC = "/vision/raw"
DEFAULT_CLOUD_TOPIC = "/vision/cloud"
DEFAULT_WS_URL = "ws://127.0.0.1:20012/ws/perception"
DEFAULT_ARM_STATE_CMD_TOPIC = "/rm_driver/get_current_arm_state_cmd"
DEFAULT_ARM_STATE_RESULT_TOPIC = "/rm_driver/get_current_arm_state_result"
DEFAULT_BASE_FRAME = "base_link"
DEFAULT_TOOL_FRAME = "Link6"
DEFAULT_PUSH_INTERVAL_SEC = 2.0          # 0.5 Hz
SNAPSHOT_MAX_DT_SEC = 2.0
CLOUD_FRAMES_PER_PUSH = 5                # merge N cloud frames per snapshot


@dataclass
class RGBFrame:
  stamp: float
  img: np.ndarray


@dataclass
class CloudFrame:
  stamp: float
  frame_id: str
  xyz: np.ndarray
  uv: np.ndarray


def stamp_to_sec(stamp) -> float:
  return float(stamp.sec) + float(stamp.nanosec) * 1e-9


def quaternion_to_matrix(x: float, y: float, z: float, w: float) -> np.ndarray:
  norm = x * x + y * y + z * z + w * w
  if norm < 1e-12:
    return np.eye(3, dtype=float)
  scale = 2.0 / norm

  xx = x * x * scale
  yy = y * y * scale
  zz = z * z * scale
  xy = x * y * scale
  xz = x * z * scale
  yz = y * z * scale
  wx = w * x * scale
  wy = w * y * scale
  wz = w * z * scale

  return np.array(
    [
      [1.0 - (yy + zz), xy - wz, xz + wy],
      [xy + wz, 1.0 - (xx + zz), yz - wx],
      [xz - wy, yz + wx, 1.0 - (xx + yy)],
    ],
    dtype=float,
  )


class StreamNode(Node):
  """Continuously push aligned RGB + cloud to the object_targets server."""

  def __init__(
    self,
    rgb_topic: str,
    cloud_topic: str,
    rgb_buffer_size: int,
    arm_state_cmd_topic: str,
    arm_state_result_topic: str,
    base_frame: str,
    tool_frame: str,
  ):
    super().__init__("stream")

    self._rgb_frames: deque[RGBFrame] = deque(maxlen=max(1, int(rgb_buffer_size)))
    self._cloud_frames: deque[CloudFrame] = deque(maxlen=max(CLOUD_FRAMES_PER_PUSH + 3, 8))
    self._last_arm_state_msg: Optional[Armstate] = None
    self._base_frame = base_frame
    self._tool_frame = tool_frame

    cam_qos = QoSProfile(
      reliability=ReliabilityPolicy.BEST_EFFORT,
      history=HistoryPolicy.KEEP_LAST,
      depth=1,
    )

    self.create_subscription(Image, rgb_topic, self._on_rgb, cam_qos)
    self.create_subscription(PointCloud2, cloud_topic, self._on_cloud, cam_qos)

    self.arm_state_cmd_pub = self.create_publisher(Empty, arm_state_cmd_topic, 10)
    self.create_subscription(Armstate, arm_state_result_topic, self._on_arm_state, 10)

    self.tf_buffer = Buffer()
    self.tf_listener = TransformListener(self.tf_buffer, self)
    self._pose_warn_next_monotonic = 0.0

    self.get_logger().info(
      f"stream: rgb={rgb_topic}, cloud={cloud_topic}"
    )

  def _on_rgb(self, msg: Image) -> None:
    encoding = msg.encoding.lower()
    if encoding not in {"bgr8", "rgb8"}:
      return
    if msg.width <= 0 or msg.height <= 0 or msg.step < msg.width * 3:
      return
    try:
      flat = np.frombuffer(msg.data, dtype=np.uint8)
      row_major = flat.reshape(msg.height, msg.step)
      img = row_major[:, : msg.width * 3].reshape(msg.height, msg.width, 3)
    except ValueError:
      return
    if encoding == "rgb8":
      img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
    self._rgb_frames.append(RGBFrame(stamp=stamp_to_sec(msg.header.stamp), img=img.copy()))

  def _on_cloud(self, msg: PointCloud2) -> None:
    field_names = {field.name for field in msg.fields}
    if not {"x", "y", "z", "u", "v"}.issubset(field_names):
      return
    pts_iter = point_cloud2.read_points(
      msg, field_names=("x", "y", "z", "u", "v"), skip_nans=True,
    )
    arr = np.array(list(pts_iter)).view(np.float32).reshape(-1, 5)
    if arr.size == 0:
      return
    self._cloud_frames.append(
      CloudFrame(
        stamp=stamp_to_sec(msg.header.stamp),
        frame_id=msg.header.frame_id,
        xyz=arr[:, :3].copy(),
        uv=arr[:, 3:5].copy(),
      )
    )

  def _on_arm_state(self, msg: Armstate) -> None:
    self._last_arm_state_msg = msg

  def best_rgb_for_cloud(self, cloud_stamp: float, max_dt: float) -> Optional[np.ndarray]:
    if not self._rgb_frames:
      return None
    best = min(self._rgb_frames, key=lambda item: abs(float(item.stamp) - cloud_stamp))
    dt = abs(float(best.stamp) - cloud_stamp)
    if dt > max_dt:
      return None
    return best.img

  def get_current_base_to_link6(self, timeout_sec: float) -> Optional[np.ndarray]:
    timeout_sec = max(0.2, float(timeout_sec))
    deadline = time.time() + timeout_sec
    start = time.time()
    arm_triggered = False

    while rclpy.ok() and time.time() < deadline:
      try:
        transform = self.tf_buffer.lookup_transform(
          self._base_frame, self._tool_frame, Time(),
        )
        matrix = np.eye(4, dtype=float)
        matrix[:3, 3] = [
          transform.transform.translation.x,
          transform.transform.translation.y,
          transform.transform.translation.z,
        ]
        matrix[:3, :3] = quaternion_to_matrix(
          transform.transform.rotation.x,
          transform.transform.rotation.y,
          transform.transform.rotation.z,
          transform.transform.rotation.w,
        )
        return matrix
      except Exception:
        pass

      if arm_triggered and self._last_arm_state_msg is not None:
        msg = self._last_arm_state_msg
        matrix = np.eye(4, dtype=float)
        matrix[:3, 3] = [
          msg.pose.position.x,
          msg.pose.position.y,
          msg.pose.position.z,
        ]
        matrix[:3, :3] = quaternion_to_matrix(
          msg.pose.orientation.x,
          msg.pose.orientation.y,
          msg.pose.orientation.z,
          msg.pose.orientation.w,
        )
        return matrix

      if not arm_triggered and (time.time() - start) >= 0.2:
        self._last_arm_state_msg = None
        self.arm_state_cmd_pub.publish(Empty())
        arm_triggered = True

      time.sleep(0.05)

    return None


def _encode_rgb_jpeg(rgb: np.ndarray, quality: int = 90) -> bytes:
  ok, buf = cv2.imencode(".jpg", rgb, [cv2.IMWRITE_JPEG_QUALITY, quality])
  if not ok:
    raise RuntimeError("Failed to encode RGB to JPEG")
  return buf.tobytes()


def _merge_cloud_frames(frames: list[CloudFrame]) -> CloudFrame:
  """Merge multiple cloud frames into one by concatenating xyz/uv arrays.

  Uses the latest frame's stamp and frame_id as metadata.
  """
  latest = frames[-1]
  xyz = np.concatenate([f.xyz for f in frames], axis=0)
  uv = np.concatenate([f.uv for f in frames], axis=0)
  return CloudFrame(
    stamp=latest.stamp,
    frame_id=latest.frame_id,
    xyz=xyz,
    uv=uv,
  )


def _encode_cloud_npz(cloud: CloudFrame) -> bytes:
  buffer = io.BytesIO()
  np.savez_compressed(
    buffer,
    xyz=cloud.xyz,
    uv=cloud.uv,
    frame_id=cloud.frame_id,
    stamp=cloud.stamp,
  )
  return buffer.getvalue()


async def _ws_push_loop(
  node: StreamNode,
  ws_url: str,
  push_interval_sec: float,
  pose_timeout_sec: float,
) -> None:
  """Connect to the server WebSocket and push snapshots periodically."""
  if websockets is None:
    node.get_logger().error("websockets package not installed; cannot run stream node")
    return

  while rclpy.ok():
    try:
      node.get_logger().info(f"Connecting to {ws_url} ...")
      async with websockets.connect(
        ws_url,
        max_size=50 * 1024 * 1024,
        ping_interval=45.0,
        ping_timeout=120.0,
        open_timeout=30.0,
        close_timeout=10.0,
      ) as ws:
        node.get_logger().info(f"WebSocket connected to {ws_url}")
        last_sent_stamp = 0.0          # track last pushed cloud stamp

        while rclpy.ok():
          await asyncio.sleep(push_interval_sec)

          # Collect unsent cloud frames (newer than last push)
          pending = [
            f for f in node._cloud_frames
            if f.stamp > last_sent_stamp
          ]

          if len(pending) < CLOUD_FRAMES_PER_PUSH:
            node.get_logger().debug(
              f"Only {len(pending)}/{CLOUD_FRAMES_PER_PUSH} new cloud frames, skipping push"
            )
            continue

          # Take exactly CLOUD_FRAMES_PER_PUSH most recent unsent frames
          frames_to_send = pending[-CLOUD_FRAMES_PER_PUSH:]
          merged_cloud = _merge_cloud_frames(frames_to_send)

          rgb = node.best_rgb_for_cloud(float(merged_cloud.stamp), SNAPSHOT_MAX_DT_SEC)
          if rgb is None:
            node.get_logger().debug(
              f"No matching RGB for cloud stamp={merged_cloud.stamp:.3f}, skipping"
            )
            continue

          base_to_link6 = node.get_current_base_to_link6(pose_timeout_sec)
          if base_to_link6 is None:
            now_m = time.monotonic()
            if now_m >= node._pose_warn_next_monotonic:
              node.get_logger().warn(
                "Skipping snapshot push: no base_to_link6_matrix "
                f"(TF {node._base_frame}->{node._tool_frame} + "
                f"{node.arm_state_cmd_pub.topic_name} / arm_state). "
                "object_targets needs this for perception."
              )
              node._pose_warn_next_monotonic = now_m + 15.0
            continue

          source = {"base_to_link6_matrix": base_to_link6.tolist()}

          rgb_jpeg = _encode_rgb_jpeg(rgb)
          cloud_npz = _encode_cloud_npz(merged_cloud)

          snapshot_msg = json.dumps({
            "type": "snapshot",
            "objects": [],
            "source": source,
          })
          await ws.send(snapshot_msg)
          await ws.send(rgb_jpeg)
          await ws.send(cloud_npz)

          last_sent_stamp = frames_to_send[-1].stamp

          try:
            ack = await asyncio.wait_for(ws.recv(), timeout=5.0)
            node.get_logger().debug(f"Snapshot ack: {ack}")
          except asyncio.TimeoutError:
            node.get_logger().warn("No snapshot ack received (timeout)")

    except (
      websockets.exceptions.ConnectionClosed,
      websockets.exceptions.InvalidStatusCode,
      OSError,
    ) as exc:
      node.get_logger().warn(f"WebSocket disconnected: {exc}, reconnecting in 3s...")
      await asyncio.sleep(3.0)
    except Exception as exc:
      node.get_logger().error(f"WebSocket error: {exc}, reconnecting in 3s...")
      await asyncio.sleep(3.0)


def _spin_node(node: Node) -> None:
  while rclpy.ok():
    rclpy.spin_once(node, timeout_sec=0.1)


def main(args=None) -> None:
  rclpy.init(args=args)

  node = StreamNode(
    rgb_topic=DEFAULT_RGB_TOPIC,
    cloud_topic=DEFAULT_CLOUD_TOPIC,
    rgb_buffer_size=60,
    arm_state_cmd_topic=DEFAULT_ARM_STATE_CMD_TOPIC,
    arm_state_result_topic=DEFAULT_ARM_STATE_RESULT_TOPIC,
    base_frame=DEFAULT_BASE_FRAME,
    tool_frame=DEFAULT_TOOL_FRAME,
  )

  node.declare_parameter("ws_url", DEFAULT_WS_URL)
  node.declare_parameter("push_interval_sec", DEFAULT_PUSH_INTERVAL_SEC)
  node.declare_parameter("pose_timeout_sec", 5.0)
  node.declare_parameter("log_level", "INFO")

  ws_url = str(node.get_parameter("ws_url").value)
  push_interval_sec = float(node.get_parameter("push_interval_sec").value)
  pose_timeout_sec = float(node.get_parameter("pose_timeout_sec").value)
  log_level = str(node.get_parameter("log_level").value)

  logging.basicConfig(
    level=getattr(logging, log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)-5s [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
  )

  spin_thread = threading.Thread(target=_spin_node, args=(node,), daemon=True)
  spin_thread.start()

  try:
    asyncio.run(_ws_push_loop(
      node=node,
      ws_url=ws_url,
      push_interval_sec=push_interval_sec,
      pose_timeout_sec=pose_timeout_sec,
    ))
  except KeyboardInterrupt:
    pass
  finally:
    node.destroy_node()
    rclpy.shutdown()
    spin_thread.join(timeout=3.0)


if __name__ == "__main__":
  main()
