"""RGB-D frame capture tool backed by the ROS capture script.

The capture script imports rclpy, which is only available in the ROS 2 Python
environment. To keep ROS out of the agent process, this tool shells out to the
script and reads back its manifest.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Sequence

from sensoragent.schemas import ToolCall, ToolResult, ToolSpec

DEFAULT_SCRIPT = "scripts/linux/capture_gazebo_rgbd_frame.py"
DEFAULT_OUT_DIR = "logs/vision/latest"
_ROS_PROBE = "import rclpy"


class VisionCaptureFrameTool:
  """Capture one RGB-D frame plus camera intrinsics/extrinsics to disk.

  Returns the manifest emitted by the capture script, whose keys line up with
  the inputs of ``vision.open_vocab_detect`` (image_path, depth_path,
  camera_info_path, T_base_camera, T_world_camera).
  """

  spec = ToolSpec(
    name="vision.capture_frame",
    description="Capture one RGB-D frame and return its manifest of paths and transforms.",
    tags=("vision", "capture", "ros"),
  )

  def __init__(
    self,
    *,
    script: str = DEFAULT_SCRIPT,
    ros_python: str | None = None,
    image_topic: str = "/industrial_camera/image",
    depth_topic: str = "/industrial_camera/depth_image",
    camera_info_topic: str = "/industrial_camera/camera_info",
    base_frame: str = "base_link",
    world_frame: str = "world",
    out_dir: str = DEFAULT_OUT_DIR,
    timeout_seconds: float = 10.0,
    fallback_t_base_camera: Any = None,
  ) -> None:
    self._script = str(script)
    self._ros_python = str(ros_python) if ros_python else None
    self._image_topic = str(image_topic)
    self._depth_topic = str(depth_topic)
    self._camera_info_topic = str(camera_info_topic)
    self._base_frame = str(base_frame)
    self._world_frame = str(world_frame)
    self._out_dir = str(out_dir)
    self._timeout_seconds = float(timeout_seconds)
    self._fallback_t_base_camera = fallback_t_base_camera

  def _python_executable(self) -> str:
    if self._ros_python:
      return self._ros_python
    return _discover_ros_python()

  def _argv(self, out_dir: Path, call: ToolCall) -> list[str]:
    timeout = float(call.input.get("timeout_seconds", self._timeout_seconds))
    return [
      self._python_executable(),
      self._script,
      "--out-dir",
      str(out_dir),
      "--image-topic",
      str(call.input.get("image_topic", self._image_topic)),
      "--depth-topic",
      str(call.input.get("depth_topic", self._depth_topic)),
      "--camera-info-topic",
      str(call.input.get("camera_info_topic", self._camera_info_topic)),
      "--base-frame",
      str(call.input.get("base_frame", self._base_frame)),
      "--world-frame",
      str(call.input.get("world_frame", self._world_frame)),
      "--timeout",
      str(timeout),
    ]

  def run(self, call: ToolCall) -> ToolResult:
    out_dir = Path(str(call.input.get("out_dir", self._out_dir)))
    try:
      out_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
      return ToolResult(
        tool=self.spec.name,
        success=False,
        error=f"CAPTURE_FAILED: cannot create out_dir {out_dir}: {exc}",
      )

    argv = self._argv(out_dir, call)
    process_timeout = float(call.input.get("timeout_seconds", self._timeout_seconds)) + 30.0
    try:
      completed = subprocess.run(
        argv,
        capture_output=True,
        text=True,
        timeout=process_timeout,
      )
    except FileNotFoundError as exc:
      return ToolResult(
        tool=self.spec.name,
        success=False,
        error=f"CAPTURE_FAILED: capture interpreter or script not found: {exc}",
      )
    except subprocess.TimeoutExpired:
      return ToolResult(
        tool=self.spec.name,
        success=False,
        error=f"CAPTURE_FAILED: capture script timed out after {process_timeout:.1f}s",
      )

    if completed.returncode != 0:
      return ToolResult(
        tool=self.spec.name,
        success=False,
        error=(
          f"CAPTURE_FAILED: capture script exited with {completed.returncode}: "
          f"{_tail(completed.stderr)}"
        ),
      )

    manifest_path = out_dir / "manifest.json"
    manifest = _load_manifest(manifest_path, completed.stdout)
    if manifest is None:
      return ToolResult(
        tool=self.spec.name,
        success=False,
        error=f"CAPTURE_FAILED: no readable manifest at {manifest_path}",
      )

    if manifest.get("T_base_camera") is None and self._fallback_t_base_camera is not None:
      manifest["T_base_camera"] = self._fallback_t_base_camera
    manifest["manifest_path"] = str(manifest_path)
    manifest["out_dir"] = str(out_dir)
    return ToolResult(tool=self.spec.name, success=True, output=manifest)


def _discover_ros_python() -> str:
  import os
  import shutil

  candidates: Sequence[str | None] = (
    os.environ.get("SENSORAGENT_ROS_PYTHON"),
    os.environ.get("ROS_PYTHON"),
    "python3",
  )
  for candidate in candidates:
    if not candidate:
      continue
    executable = shutil.which(candidate) or candidate
    try:
      probe = subprocess.run(
        [executable, "-c", _ROS_PROBE],
        capture_output=True,
        text=True,
        timeout=30.0,
      )
    except (OSError, subprocess.SubprocessError):
      continue
    if probe.returncode == 0:
      return executable
  return "python3"


def _load_manifest(manifest_path: Path, stdout: str) -> dict[str, Any] | None:
  try:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
  except (OSError, json.JSONDecodeError):
    payload = None
  if payload is None:
    try:
      payload = json.loads(stdout)
    except (json.JSONDecodeError, TypeError):
      return None
  if not isinstance(payload, dict):
    return None
  return dict(payload)


def _tail(text: str | None, limit: int = 400) -> str:
  if not text:
    return ""
  stripped = text.strip()
  if len(stripped) <= limit:
    return stripped
  return stripped[-limit:]
