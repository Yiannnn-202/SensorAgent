"""RGB-D frame capture tool backed by the ROS capture script.

The capture script imports rclpy, which is only available in the ROS 2 Python
environment. To keep ROS out of the agent process, this tool shells out to the
script and reads back its manifest.
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Any, Sequence

from sensoragent.schemas import ToolCall, ToolResult, ToolSpec

DEFAULT_SCRIPT = "scripts/linux/capture_gazebo_rgbd_frame.py"
DEFAULT_OUT_DIR = "logs/vision/latest"
_ROS_PROBE = "import numpy, rclpy; from sensor_msgs.msg import CameraInfo, Image"
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
    cloud_topic: str | None = None,
    base_frame: str = "base_link",
    world_frame: str = "world",
    out_dir: str = DEFAULT_OUT_DIR,
    timeout_seconds: float = 10.0,
    fallback_t_base_camera: Any = None,
    fallback_t_world_camera: Any = None,
  ) -> None:
    self._script = str(script)
    self._ros_python = str(ros_python) if ros_python else None
    self._ros_setup = str(ros_setup) if ros_setup else None
    self._image_topic = str(image_topic)
    self._depth_topic = str(depth_topic)
    self._camera_info_topic = str(camera_info_topic)
    self._cloud_topic = str(cloud_topic) if cloud_topic else None
    self._base_frame = str(base_frame)
    self._world_frame = str(world_frame)
    self._out_dir = str(out_dir)
    self._timeout_seconds = float(timeout_seconds)
    self._fallback_t_base_camera = fallback_t_base_camera
    self._fallback_t_world_camera = fallback_t_world_camera

  def _setup_script(self) -> str | None:
    """Return an explicit or discovered ROS setup script."""

    if self._ros_setup:
      return self._ros_setup
    return _discover_ros_setup()

  def _python_executable(self) -> tuple[str, dict[str, str] | None]:
    if self._ros_python:
      if _python_can_capture(self._ros_python):
        return self._ros_python, None
      ros_env = _sourced_ros_environment()
      if ros_env is not None and _python_can_capture(self._ros_python, env=ros_env):
        return self._ros_python, ros_env
      return self._ros_python, None
    return _discover_ros_python()

  def _argv_and_env(
    self,
    out_dir: Path,
    call: ToolCall,
  ) -> tuple[list[str], dict[str, str] | None]:
    timeout = float(call.input.get("timeout_seconds", self._timeout_seconds))
    setup = self._setup_script()
    if setup is not None:
      python_executable = (
        self._ros_python
        or os.environ.get("SENSORAGENT_ROS_PYTHON")
        or os.environ.get("ROS_PYTHON")
        or "python3"
      )
      argv = self._argv(python_executable, out_dir, call, timeout)
      quoted = " ".join(shlex.quote(item) for item in argv)
      setup_command = f". {_shell_path(setup)} >/dev/null 2>&1"
      workspace_setup = Path("ros2_ws/install/setup.bash")
      if workspace_setup.is_file():
        setup_command += f" && . {_shell_path(str(workspace_setup))} >/dev/null 2>&1"
      return [
        "bash",
        "-c",
        f"unset PYTHONHOME PYTHONPATH; {setup_command} && exec {quoted}",
      ], None

    python_executable, env = self._python_executable()
    return self._argv(python_executable, out_dir, call, timeout), env

  def _argv(
    self,
    python_executable: str,
    out_dir: Path,
    call: ToolCall,
    timeout: float,
  ) -> list[str]:
    if self._cloud_topic:
      return [
        python_executable,
        self._script,
        "--out-dir", str(out_dir),
        "--image-topic", str(call.input.get("image_topic", self._image_topic)),
        "--cloud-topic", str(call.input.get("cloud_topic", self._cloud_topic)),
        "--base-frame", str(call.input.get("base_frame", self._base_frame)),
        "--timeout", str(timeout),
      ]
    return [
      python_executable,
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

    try:
      argv, env = self._argv_and_env(out_dir, call)
    except RuntimeError as exc:
      return ToolResult(
        tool=self.spec.name,
        success=False,
        error=f"CAPTURE_FAILED: {exc}",
      )
    process_timeout = float(call.input.get("timeout_seconds", self._timeout_seconds)) + 30.0
    try:
      completed = subprocess.run(
        argv,
        capture_output=True,
        text=True,
        timeout=process_timeout,
        env=env,
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
    if manifest.get("T_world_camera") is None and self._fallback_t_world_camera is not None:
      manifest["T_world_camera"] = self._fallback_t_world_camera
    manifest["manifest_path"] = str(manifest_path)
    manifest["out_dir"] = str(out_dir)
    return ToolResult(tool=self.spec.name, success=True, output=manifest)


def _candidate_python_executables() -> list[str]:
  candidates: Sequence[str | None] = (
    os.environ.get("SENSORAGENT_ROS_PYTHON"),
    os.environ.get("ROS_PYTHON"),
    "/usr/bin/python3",
    "python3",
    str(
      Path.home()
      / "micromamba"
      / "envs"
      / "sensoragent-ros-humble"
      / "bin"
      / "python"
    ),
    str(
      Path("/home")
      / os.environ.get("USER", "")
      / "snap"
      / "copilot-cli"
      / "common"
      / "micromamba"
      / "envs"
      / "sensoragent-ros-humble"
      / "bin"
      / "python"
    ),
  )
  result: list[str] = []
  seen: set[str] = set()
  for candidate in candidates:
    if not candidate:
      continue
    executable = shutil.which(candidate) or candidate
    if executable in seen:
      continue
    seen.add(executable)
    result.append(executable)
  return result


def _discover_ros_setup() -> str | None:
  """Find a setup script whose environment makes ROS Python imports available."""

  override = os.environ.get("SENSORAGENT_ROS_SETUP")
  if override:
    return override if Path(override).is_file() else None
  for candidate in _ROS_SETUP_CANDIDATES:
    if Path(candidate).is_file():
      return candidate
  return None


def _shell_path(value: str) -> str:
  """Quote setup paths only when the shell requires it."""

  if any(character.isspace() or character in "'\"$`;&|<>()" for character in value):
    return shlex.quote(value)
  return value


def _python_can_capture(executable: str, env: dict[str, str] | None = None) -> bool:
  try:
    probe = subprocess.run(
      [executable, "-c", _ROS_PROBE],
      capture_output=True,
      text=True,
      timeout=30.0,
      env=env,
    )
  except (OSError, subprocess.SubprocessError):
    return False
  return probe.returncode == 0


def _sourced_ros_environment() -> dict[str, str] | None:
  ros_distro = os.environ.get("ROS_DISTRO", "humble")
  ros_setup = Path(f"/opt/ros/{ros_distro}/setup.bash")
  if not ros_setup.is_file():
    return None

  setup_commands = [f"source {sh_quote(str(ros_setup))}"]
  workspace_setup = Path("ros2_ws/install/setup.bash")
  if workspace_setup.is_file():
    setup_commands.append(f"source {sh_quote(str(workspace_setup))}")
  command = "set -e; " + "; ".join(setup_commands) + "; env -0"
  try:
    completed = subprocess.run(
      ["bash", "-lc", command],
      capture_output=True,
      timeout=30.0,
    )
  except (OSError, subprocess.SubprocessError):
    return None
  if completed.returncode != 0:
    return None
  env = dict(os.environ)
  for entry in completed.stdout.split(b"\0"):
    if not entry or b"=" not in entry:
      continue
    key, value = entry.split(b"=", 1)
    env[key.decode("utf-8", "surrogateescape")] = value.decode(
      "utf-8",
      "surrogateescape",
    )
  return env


def sh_quote(value: str) -> str:
  return "'" + value.replace("'", "'\"'\"'") + "'"


def _discover_ros_python() -> tuple[str, dict[str, str] | None]:
  candidates = _candidate_python_executables()
  for executable in candidates:
    if _python_can_capture(executable):
      return executable, None

  ros_env = _sourced_ros_environment()
  if ros_env is not None:
    for executable in candidates:
      if _python_can_capture(executable, env=ros_env):
        return executable, ros_env

  checked = ", ".join(candidates)
  raise RuntimeError(
    "No Python interpreter with numpy, rclpy, and sensor_msgs was found, even "
    "after sourcing ROS/workspace setup files. Set SENSORAGENT_ROS_PYTHON to a "
    "ROS-capable Python or set configs/robot_sim.yaml "
    f"integrations.vision.capture.ros_python. Checked: {checked}"
  )


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
