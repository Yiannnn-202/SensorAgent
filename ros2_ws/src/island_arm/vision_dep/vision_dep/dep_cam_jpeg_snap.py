#!/usr/bin/env python3

"""Service that returns the latest JPEG from ``dep_cam`` compressed color topic."""

from __future__ import annotations

import threading
from typing import Optional

import rclpy
from rclpy.node import Node
from rclpy.qos import HistoryPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import CompressedImage
from vision_interfaces.srv import DepCamJpegSnap

DEFAULT_TOPIC = '/vision/dep/raw/compressed'
DEFAULT_SERVICE = '/vision/dep/jpeg_snap'


class DepCamJpegSnapNode(Node):
  """Exposes `/vision/dep/jpeg_snap`: latest JPEG from dep_cam compressed stream."""

  def __init__(self) -> None:
    super().__init__('dep_cam_jpeg_snap')

    self.declare_parameter('source_topic', DEFAULT_TOPIC)
    self.declare_parameter('service_name', DEFAULT_SERVICE)

    topic = str(self.get_parameter('source_topic').value).strip() or DEFAULT_TOPIC
    srv_name = str(self.get_parameter('service_name').value).strip() or DEFAULT_SERVICE

    self._source_topic = topic
    self._cam_qos = QoSProfile(
      reliability=ReliabilityPolicy.BEST_EFFORT,
      history=HistoryPolicy.KEEP_LAST,
      depth=1,
    )

    self._latest_jpeg: Optional[bytes] = None
    self._jpeg_lock = threading.Lock()
    self._cam_sub = self.create_subscription(
      CompressedImage,
      self._source_topic,
      self._on_image,
      self._cam_qos,
    )

    self._srv = self.create_service(DepCamJpegSnap, srv_name, self._on_snap)

    self.get_logger().info(
      f'dep_cam_jpeg_snap ready: JPEG from {topic!r} → service {srv_name!r}'
    )

  def _on_image(self, msg: CompressedImage) -> None:
    with self._jpeg_lock:
      self._latest_jpeg = bytes(msg.data)

  def _on_snap(
    self, _request: DepCamJpegSnap.Request, response: DepCamJpegSnap.Response
  ) -> DepCamJpegSnap.Response:
    self.get_logger().info(
      f'RECEIVED DepCamJpegSnap service call topic={self._source_topic!r} '
      f'(returning latest dep_cam JPEG)'
    )
    with self._jpeg_lock:
      jpeg = self._latest_jpeg

    if not jpeg:
      response.success = False
      response.message = f'No frame yet from dep_cam on {self._source_topic!r}'
      response.data = []
      self.get_logger().warning(response.message)
      return response

    response.success = True
    response.message = f'{len(jpeg)} bytes jpeg'
    response.data = list(jpeg)
    self.get_logger().info(
      f'DepCamJpegSnap returning frame: {response.message}'
    )
    return response


def main() -> None:
  rclpy.init()
  node = DepCamJpegSnapNode()
  try:
    rclpy.spin(node)
  finally:
    node.destroy_node()
    rclpy.shutdown()


__all__ = ['DepCamJpegSnapNode', 'main']
