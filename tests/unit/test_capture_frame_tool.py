"""Tests for the RGB-D frame capture tool.

The capture script needs rclpy, so these tests stub subprocess and never touch
ROS.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from unittest import TestCase, mock

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
  sys.path.insert(0, str(SRC))

from sensoragent.schemas import ToolCall, TraceContext
from sensoragent.tools.vision import VisionCaptureFrameTool

_T_BASE_CAMERA = [
  [0.0, -1.0, 0.0, 0.34],
  [-1.0, 0.0, 0.0, 0.0],
  [0.0, 0.0, -1.0, 0.88],
  [0.0, 0.0, 0.0, 1.0],
]
_T_WORLD_CAMERA = [
  [0.0, -1.0, 0.0, 0.34],
  [-1.0, 0.0, 0.0, 0.0],
  [0.0, 0.0, -1.0, 1.06],
  [0.0, 0.0, 0.0, 1.0],
]


@dataclass
class _Completed:
  returncode: int = 0
  stdout: str = ""
  stderr: str = ""


def _manifest(
  out_dir: Path,
  t_base_camera=_T_BASE_CAMERA,
  t_world_camera=None,
) -> dict:
  return {
    "image_path": str(out_dir / "rgb.npy"),
    "depth_path": str(out_dir / "depth.npy"),
    "camera_info_path": str(out_dir / "camera_info.json"),
    "camera_frame": "camera_color_optical_frame",
    "T_base_camera": t_base_camera,
    "T_world_camera": t_world_camera,
  }


class VisionCaptureFrameToolTest(TestCase):
  def setUp(self) -> None:
    self._temp = tempfile.TemporaryDirectory()
    self.out_dir = Path(self._temp.name) / "frame"
    self.addCleanup(self._temp.cleanup)

  def _tool(self, **kwargs) -> VisionCaptureFrameTool:
    defaults = {
      "script": "scripts/linux/capture_gazebo_rgbd_frame.py",
      "ros_python": "/usr/bin/python3",
      "out_dir": str(self.out_dir),
    }
    return VisionCaptureFrameTool(**{**defaults, **kwargs})

  def _call(self, **input_data) -> ToolCall:
    return ToolCall(tool="vision.capture_frame", input=input_data, trace=TraceContext())

  def _write_manifest(self, payload: dict) -> None:
    self.out_dir.mkdir(parents=True, exist_ok=True)
    (self.out_dir / "manifest.json").write_text(json.dumps(payload), encoding="utf-8")

  def test_builds_expected_argv(self) -> None:
    tool = self._tool(
      image_topic="/cam/image",
      depth_topic="/cam/depth",
      camera_info_topic="/cam/info",
      base_frame="base_link",
      world_frame="world",
      timeout_seconds=7.5,
    )

    def fake_run(argv, **_kwargs):
      self._write_manifest(_manifest(self.out_dir))
      fake_run.argv = argv
      return _Completed()

    with mock.patch("subprocess.run", side_effect=fake_run):
      result = tool.run(self._call())

    self.assertTrue(result.success, msg=result.error)
    argv = fake_run.argv
    self.assertEqual(argv[0], "/usr/bin/python3")
    self.assertEqual(argv[1], "scripts/linux/capture_gazebo_rgbd_frame.py")
    self.assertEqual(argv[argv.index("--out-dir") + 1], str(self.out_dir))
    self.assertEqual(argv[argv.index("--image-topic") + 1], "/cam/image")
    self.assertEqual(argv[argv.index("--depth-topic") + 1], "/cam/depth")
    self.assertEqual(argv[argv.index("--camera-info-topic") + 1], "/cam/info")
    self.assertEqual(argv[argv.index("--base-frame") + 1], "base_link")
    self.assertEqual(argv[argv.index("--world-frame") + 1], "world")
    self.assertEqual(argv[argv.index("--timeout") + 1], "7.5")
    self.assertNotIn("--camera-frame", argv)

  def test_returns_manifest_fields_used_by_the_detector(self) -> None:
    tool = self._tool()
    payload = _manifest(self.out_dir)

    def fake_run(argv, **_kwargs):
      self._write_manifest(payload)
      return _Completed()

    with mock.patch("subprocess.run", side_effect=fake_run):
      result = tool.run(self._call())

    self.assertTrue(result.success, msg=result.error)
    self.assertEqual(result.output["image_path"], payload["image_path"])
    self.assertEqual(result.output["depth_path"], payload["depth_path"])
    self.assertEqual(result.output["camera_info_path"], payload["camera_info_path"])
    self.assertEqual(result.output["T_base_camera"], _T_BASE_CAMERA)
    self.assertEqual(result.output["out_dir"], str(self.out_dir))

  def test_out_dir_override_is_honoured(self) -> None:
    tool = self._tool()
    override = Path(self._temp.name) / "other"

    def fake_run(argv, **_kwargs):
      override.mkdir(parents=True, exist_ok=True)
      (override / "manifest.json").write_text(json.dumps(_manifest(override)), encoding="utf-8")
      fake_run.argv = argv
      return _Completed()

    with mock.patch("subprocess.run", side_effect=fake_run):
      result = tool.run(self._call(out_dir=str(override)))

    self.assertTrue(result.success, msg=result.error)
    self.assertEqual(fake_run.argv[fake_run.argv.index("--out-dir") + 1], str(override))
    self.assertTrue(result.output["image_path"].startswith(str(override)))

  def test_missing_transform_falls_back_to_configured_matrix(self) -> None:
    tool = self._tool(
      fallback_t_base_camera=_T_BASE_CAMERA,
      fallback_t_world_camera=_T_WORLD_CAMERA,
    )

    def fake_run(argv, **_kwargs):
      self._write_manifest(
        _manifest(self.out_dir, t_base_camera=None, t_world_camera=None)
      )
      return _Completed()

    with mock.patch("subprocess.run", side_effect=fake_run):
      result = tool.run(self._call())

    self.assertTrue(result.success, msg=result.error)
    self.assertEqual(result.output["T_base_camera"], _T_BASE_CAMERA)
    self.assertEqual(result.output["T_world_camera"], _T_WORLD_CAMERA)

  def test_non_zero_exit_reports_stderr(self) -> None:
    tool = self._tool()

    with mock.patch(
      "subprocess.run",
      return_value=_Completed(returncode=1, stderr="ModuleNotFoundError: rclpy"),
    ):
      result = tool.run(self._call())

    self.assertFalse(result.success)
    self.assertIn("CAPTURE_FAILED", result.error)
    self.assertIn("rclpy", result.error)

  def test_timeout_is_reported_as_capture_failure(self) -> None:
    tool = self._tool()

    with mock.patch(
      "subprocess.run",
      side_effect=subprocess.TimeoutExpired(cmd="capture", timeout=40.0),
    ):
      result = tool.run(self._call())

    self.assertFalse(result.success)
    self.assertIn("CAPTURE_FAILED", result.error)
    self.assertIn("timed out", result.error)

  def test_missing_manifest_reports_capture_failure(self) -> None:
    tool = self._tool()

    with mock.patch("subprocess.run", return_value=_Completed(stdout="not json")):
      result = tool.run(self._call())

    self.assertFalse(result.success)
    self.assertIn("CAPTURE_FAILED", result.error)

  def test_manifest_is_read_from_stdout_when_file_is_absent(self) -> None:
    tool = self._tool()
    payload = _manifest(self.out_dir)

    with mock.patch("subprocess.run", return_value=_Completed(stdout=json.dumps(payload))):
      result = tool.run(self._call())

    self.assertTrue(result.success, msg=result.error)
    self.assertEqual(result.output["image_path"], payload["image_path"])

  def test_missing_interpreter_reports_capture_failure(self) -> None:
    tool = self._tool()

    with mock.patch("subprocess.run", side_effect=FileNotFoundError("no python")):
      result = tool.run(self._call())

    self.assertFalse(result.success)
    self.assertIn("CAPTURE_FAILED", result.error)
