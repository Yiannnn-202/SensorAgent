#!/usr/bin/env python3

"""FaceRec Node — real-time face recognition via ArcFace WebSocket + ROS topic.

Subscribes to dep_cam compressed JPEG, sends frames at 2 fps over a WebSocket
to the ArcFace server, and publishes recognition results to
``/vision/face/results`` (``vision_interfaces/msg/FaceResults``).

ROS services:
 /vision/face/register   (vision_interfaces/srv/FaceRegister) — name only
 /vision/face/recognize  (vision_interfaces/srv/FaceRecognize) — one-shot frame
"""

import asyncio
import json
import threading
import time
from typing import Optional

import httpx
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
from sensor_msgs.msg import CompressedImage
from vision_interfaces.msg import FaceResult, FaceResults
from vision_interfaces.srv import FaceRecognize, FaceRegister

try:
  import websockets
except ImportError:
  websockets = None  # type: ignore[assignment]

DEFAULT_SOURCE_TOPIC = "/vision/dep/raw/compressed"
DEFAULT_ARCFACE_HOST = "127.0.0.1"
DEFAULT_ARCFACE_PORT = 20004
DEFAULT_WS_FPS = 0.5


class FaceRecNode(Node):

  def __init__(self):
    super().__init__("facerec")

    self.declare_parameter("source_topic", DEFAULT_SOURCE_TOPIC)
    self.declare_parameter("arcface_host", DEFAULT_ARCFACE_HOST)
    self.declare_parameter("arcface_port", DEFAULT_ARCFACE_PORT)
    self.declare_parameter("ws_fps", DEFAULT_WS_FPS)

    self._source_topic = str(self.get_parameter("source_topic").value).strip()
    host = self.get_parameter("arcface_host").value
    port = self.get_parameter("arcface_port").value
    self._arcface_base = f"http://{host}:{port}"
    self._ws_url = f"ws://{host}:{port}/ws/recognize"
    self._ws_fps = float(self.get_parameter("ws_fps").value)

    self._srv_register = self.create_service(
      FaceRegister, "/vision/face/register", self._on_register
    )
    self._srv_recognize = self.create_service(
      FaceRecognize, "/vision/face/recognize", self._on_recognize
    )

    self._results_pub = self.create_publisher(FaceResults, "/vision/face/results", 10)

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

    self._http_client = httpx.Client(timeout=30.0)

    if websockets is None:
      self.get_logger().error(
        "websockets package not installed — real-time recognition disabled"
      )
    else:
      self._ws_thread = threading.Thread(
        target=self._ws_loop, daemon=True, name="ws-arcface"
      )
      self._ws_thread.start()

    self.get_logger().info(
      f"FaceRec ready. ArcFace WS={self._ws_url} REST={self._arcface_base}; "
      f"frames from {self._source_topic!r} at {self._ws_fps} fps; "
      "services /vision/face/register, /vision/face/recognize"
    )

  def _on_image(self, msg: CompressedImage):
    with self._jpeg_lock:
      self._latest_jpeg = bytes(msg.data)

  def _on_register(self, request: FaceRegister.Request, response: FaceRegister.Response):
    name = request.name.strip()
    if not name:
      response.success = False
      response.message = "Field 'name' is required"
      response.name = ""
      return response

    self.get_logger().info(f"Register service call: name='{name}'")

    jpeg: Optional[bytes] = None
    deadline = time.monotonic() + 2.0
    while jpeg is None and time.monotonic() < deadline:
      with self._jpeg_lock:
        jpeg = self._latest_jpeg
      if jpeg is None:
        time.sleep(0.1)

    if jpeg is None:
      response.success = False
      response.message = "No frame received from dep_cam"
      response.name = ""
      return response

    arc_result = self._arcface_register(jpeg, name)
    if arc_result.get("status") != "success":
      response.success = False
      response.message = arc_result.get("message", "ArcFace register failed")
      response.name = ""
      return response

    response.success = True
    response.message = arc_result.get("message", "Registered successfully")
    response.name = name
    self.get_logger().info(
      f"Register done: name={name!r} success=True message={response.message!r}"
    )
    return response

  def _on_recognize(
    self, request: FaceRecognize.Request, response: FaceRecognize.Response
  ):
    self.get_logger().info("Recognize service call: one-shot recognize from dep_cam")
    jpeg: Optional[bytes] = None
    deadline = time.monotonic() + 2.0
    while jpeg is None and time.monotonic() < deadline:
      with self._jpeg_lock:
        jpeg = self._latest_jpeg
      if jpeg is None:
        time.sleep(0.1)

    if jpeg is None:
      response.success = False
      response.message = "No frame received from dep_cam"
      response.face_count = 0
      response.names = []
      response.scores = []
      response.bboxes = []
      return response

    self.get_logger().info(
      "Recognize service: captured frame, calling ArcFace /api/v1/recognize"
    )
    arc_result = self._arcface_recognize(jpeg)
    out = self._fill_recognize_response(response, arc_result)
    self.get_logger().info(
      f"Recognize done: success={out.success} face_count={out.face_count} "
      f"names={list(out.names)!r} message={out.message!r}"
    )
    return out

  def _arcface_register(self, jpeg_bytes: bytes, name: str) -> dict:
    try:
      resp = self._http_client.post(
        f"{self._arcface_base}/api/v1/register",
        files={"image": ("frame.jpg", jpeg_bytes, "image/jpeg")},
        data={"name": name},
      )
      resp.raise_for_status()
      return resp.json()
    except Exception as e:
      return {"status": "error", "message": str(e)}

  def _arcface_recognize(self, jpeg_bytes: bytes) -> dict:
    try:
      resp = self._http_client.post(
        f"{self._arcface_base}/api/v1/recognize",
        files={"image": ("frame.jpg", jpeg_bytes, "image/jpeg")},
      )
      resp.raise_for_status()
      return resp.json()
    except Exception as e:
      return {"status": "error", "message": str(e)}

  @staticmethod
  def _fill_recognize_response(
    response: FaceRecognize.Response, arc_result: dict
  ) -> FaceRecognize.Response:
    status = arc_result.get("status", "error")
    message = str(arc_result.get("message", "") or "")
    data = arc_result.get("data") or {}
    if status != "success":
      response.success = False
      response.message = message or status
      response.face_count = 0
      response.names = []
      response.scores = []
      response.bboxes = []
      return response

    raw_results = data.get("results") or []
    names: list[str] = []
    scores: list[float] = []
    bboxes: list[float] = []
    for r in raw_results:
      names.append(str(r.get("name", "unknown")))
      scores.append(float(r.get("score", r.get("confidence", 0.0))))
      bbox = r.get("bbox", [0, 0, 0, 0])
      for v in bbox[:4]:
        bboxes.append(float(v))

    response.success = True
    response.message = message or "ok"
    response.face_count = len(names)
    response.names = names
    response.scores = scores
    response.bboxes = bboxes
    return response

  def _ws_loop(self) -> None:
    asyncio.run(self._ws_async_loop())

  async def _ws_async_loop(self) -> None:
    period = 1.0 / max(self._ws_fps, 0.1)
    backoff = 1.0

    while rclpy.ok():
      try:
        async with websockets.connect(
          self._ws_url,
          max_size=None,
          ping_interval=20,
          ping_timeout=30,
        ) as ws:
          self.get_logger().info(f"WebSocket connected to {self._ws_url}")
          backoff = 1.0

          while rclpy.ok():
            jpeg = self._get_latest_jpeg()
            if jpeg is None:
              await asyncio.sleep(0.1)
              continue

            await ws.send(jpeg)
            raw = await ws.recv()

            if isinstance(raw, bytes):
              raw = raw.decode("utf-8")

            try:
              result = json.loads(raw)
            except json.JSONDecodeError:
              self.get_logger().warning("Invalid JSON from ArcFace WS")
              await asyncio.sleep(period)
              continue

            self._publish_result(result)
            await asyncio.sleep(period)

      except (
        websockets.exceptions.ConnectionClosed,
        websockets.exceptions.InvalidStatusCode,
        OSError,
      ) as exc:
        self.get_logger().warning(
          f"WebSocket disconnected ({exc}); reconnecting in {backoff:.1f}s"
        )
        await asyncio.sleep(backoff)
        backoff = min(backoff * 2, 30.0)
      except Exception as exc:
        self.get_logger().error(f"WebSocket error: {exc}")
        await asyncio.sleep(backoff)
        backoff = min(backoff * 2, 30.0)

  def _get_latest_jpeg(self) -> Optional[bytes]:
    with self._jpeg_lock:
      return self._latest_jpeg

  def _publish_result(self, result: dict) -> None:
    status = result.get("status", "error")
    message = result.get("message", "")
    data = result.get("data") or {}
    face_count = data.get("face_count", 0)
    raw_results = data.get("results") or []

    msg = FaceResults()
    msg.success = status == "success"
    msg.message = message if message else ("recognition complete" if msg.success else status)
    msg.face_count = face_count

    for r in raw_results:
      fr = FaceResult()
      fr.name = str(r.get("name", "unknown"))
      fr.score = float(r.get("score", r.get("confidence", 0.0)))
      bbox = r.get("bbox", [0, 0, 0, 0])
      fr.bbox = [float(v) for v in bbox[:4]]
      fr.direction_px = float(r.get("direction_px", 0.0))
      msg.faces.append(fr)

    self._results_pub.publish(msg)

  def destroy_node(self):
    self._http_client.close()
    super().destroy_node()


def main(args=None):
  rclpy.init(args=args)
  node = FaceRecNode()
  try:
    rclpy.spin(node)
  except KeyboardInterrupt:
    pass
  finally:
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
  main()
