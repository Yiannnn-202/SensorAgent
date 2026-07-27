"""RGB-D frame capture tool backed by the ROS capture script.

The capture script imports rclpy, which lives in the ROS 2 environment rather
than the agent's virtualenv. To keep ROS out of the agent process, this tool
shells out to the script -- sourcing the ROS setup script first, since rclpy
needs the PYTHONPATH and library paths it exports -- and reads back the manifest.
"""

from __future__ import annotations

import json
import shlex
import subprocess
from pathlib import Path
from typing import Any

from sensoragent.schemas import ToolCall, ToolResult, ToolSpec

DEFAULT_SCRIPT = "scripts/linux/capture_gazebo_rgbd_frame.py"
DEFAULT_OUT_DIR = "logs/vision/latest"
_ROS_SETUP_CANDIDATES = (
  "/opt/ros/humble/setup.bash",
  "/opt/ros/jazzy/setup.bash",
  "/opt/ros/iron/setup.bash",
)


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
    ros_setup: str | None = None,
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
    self._ros_setup = str(ros_setup) if ros_setup else None
    self._image_topic = str(image_topic)
    self._depth_topic = str(depth_topic)
    self._camera_info_topic = str(camera_info_topic)
    self._base_frame = str(base_frame)
    self._world_frame = str(world_frame)
    self._out_dir = str(out_dir)
    self._timeout_seconds = float(timeout_seconds)
    self._fallback_t_base_camera = fallback_t_base_camera

  def _python_executable(self) -> str:
    return self._ros_python or "python3"

  def _setup_script(self) -> str | None:
    """Path to the ROS setup script to source, if one is needed and available."""

    if self._ros_setup:
      return self._ros_setup
    return _discover_ros_setup()

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

  def _command(self, out_dir: Path, call: ToolCall) -> tuple[list[str], bool]:
    """Return the command to run and whether it must go through a shell.

    rclpy needs the PYTHONPATH and library paths exported by the ROS setup
    script, so unless the caller pinned an interpreter that already has them the
    command is wrapped in a shell that sources the setup first. The agent's own
    PYTHONPATH is cleared so it cannot shadow the ROS packages.
    """

    argv = self._argv(out_dir, call)
    setup = self._setup_script()
    if setup is None:
      return argv, False
    quoted = " ".join(shlex.quote(item) for item in argv)
    return [
      "bash",
      "-c",
      f"unset PYTHONHOME PYTHONPATH; . {shlex.quote(setup)} >/dev/null 2>&1 && exec {quoted}",
    ], True

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

    command, _via_shell = self._command(out_dir, call)
    process_timeout = float(call.input.get("timeout_seconds", self._timeout_seconds)) + 30.0
    try:
      completed = subprocess.run(
        command,
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


def _discover_ros_setup() -> str | None:
  """Find a ROS setup script to source, or None to run the command as-is.

  ``SENSORAGENT_ROS_SETUP`` overrides discovery. Note that an inherited
  ``AMENT_PREFIX_PATH`` is not treated as "ROS is ready": the variable often
  survives into environments where rclpy is still unimportable (a virtualenv on
  a different Python minor version, or a cleared PYTHONPATH), so the setup
  script is sourced whenever one is available.
  """

  import os

  override = os.environ.get("SENSORAGENT_ROS_SETUP")
  if override:
    return override if Path(override).is_file() else None
  for candidate in _ROS_SETUP_CANDIDATES:
    if Path(candidate).is_file():
      return candidate
  return None


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
