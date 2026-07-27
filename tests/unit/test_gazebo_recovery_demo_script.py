"""Smoke tests for the Gazebo recovery demo runner.

The demo can be run without Gazebo when --execute is omitted; this keeps the
failure-injection plumbing testable on Windows and CI.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "linux" / "run_gazebo_recovery_demo.py"


def _load_demo_module():
  spec = importlib.util.spec_from_file_location("run_gazebo_recovery_demo", SCRIPT)
  module = importlib.util.module_from_spec(spec)
  assert spec is not None and spec.loader is not None
  spec.loader.exec_module(module)
  return module


class GazeboRecoveryDemoScriptTest(TestCase):
  def test_wrong_bin_demo_runs_without_gazebo(self) -> None:
    module = _load_demo_module()
    output = ROOT / "logs" / "tasks" / "test_recovery_demo_script.json"
    argv = [
      str(SCRIPT),
      "--failure",
      "wrong-bin",
      "--object-query",
      "block",
      "--target",
      "bin_cell_3",
      "--wrong-target",
      "bin_cell_2",
      "--json-out",
      str(output),
    ]

    with patch.object(sys, "argv", argv):
      exit_code = module.main()

    self.assertEqual(exit_code, 0)
    data = json.loads(output.read_text(encoding="utf-8"))
    self.assertTrue(data["success"])
    self.assertEqual(data["classification"]["failure_type"], "WRONG_BIN")
    self.assertEqual(data["recovery"]["strategy"], "repick_from_observed_pose")
    self.assertIn("recover_pick", [node["node"] for node in data["nodes"]])
    self.assertEqual(
      data["result"]["recovered_pick"]["pick_plan"]["grasp_pose"]["orientation"],
      data["failure_injection"]["misplaced_pose"]["orientation"],
    )
    self.assertEqual(
      data["failure_injection"]["recovery_pick_distances"],
      {"approach_distance": 0.03, "pregrasp_distance": 0.015, "lift_height": 0.08},
    )
    self.assertAlmostEqual(
      data["result"]["recovered_pick"]["pick_plan"]["plan"]["approach"]["position"][2],
      0.29,
    )

  def test_wrong_table_demo_runs_without_gazebo(self) -> None:
    module = _load_demo_module()
    output = ROOT / "logs" / "tasks" / "test_recovery_table_demo_script.json"
    argv = [
      str(SCRIPT),
      "--failure",
      "wrong-table",
      "--object-query",
      "block",
      "--target",
      "bin_cell_3",
      "--json-out",
      str(output),
    ]

    with patch.object(sys, "argv", argv):
      exit_code = module.main()

    self.assertEqual(exit_code, 0)
    data = json.loads(output.read_text(encoding="utf-8"))
    self.assertTrue(data["success"])
    self.assertEqual(data["classification"]["failure_type"], "WRONG_BIN")
    self.assertEqual(data["failure_injection"]["wrong_target"], "tabletop")
    self.assertEqual(
      data["result"]["recovered_pick"]["object"]["pose_3d"],
      module.TABLETOP_OBJECT_POSE_3D,
    )
    wrong_table_checks = [
      node
      for node in data["nodes"]
      if node["node"] == "verify_object_in_bin" and node["success"] is False
    ]
    self.assertTrue(wrong_table_checks)
    self.assertEqual(
      wrong_table_checks[0]["output"]["object_position"],
      module.TABLETOP_PLACE_POSE["position"],
    )
    self.assertEqual(
      data["result"]["recovered_pick"]["pick_plan"]["grasp_pose"]["orientation"],
      module.TABLETOP_PLACE_POSE["orientation"],
    )
    self.assertEqual(
      data["failure_injection"]["recovery_pick_distances"],
      {"approach_distance": 0.08, "pregrasp_distance": 0.03, "lift_height": 0.1},
    )
    self.assertEqual(data["failure_injection"]["recovery_pick_position_offset"], [0.0, 0.0, 0.02])
    self.assertIn("recover_pick", [node["node"] for node in data["nodes"]])

  def test_wrong_table_recovery_relocalizes_with_yoloe(self) -> None:
    module = _load_demo_module()
    state = {
      "failure": "wrong-table",
      "wrong_bin_detected": True,
      "misplaced_pose": module.TABLETOP_PLACE_POSE,
    }

    class WrappedConfigDetect:
      spec = SimpleNamespace(name="vision.config_detect")

      def run(self, call):
        raise AssertionError("live recovery should not use config_detect fallback")

    class YoloeOpenVocab:
      spec = SimpleNamespace(name="vision.open_vocab_detect")

      def __init__(self) -> None:
        self.calls = []

      def run(self, call):
        self.calls.append(call.input)
        return module.ToolResult(
          tool=self.spec.name,
          success=True,
          output={
            "found": True,
            "label": call.input["query"],
            "confidence": 0.91,
            "pose_3d": [0.31, 0.10, 0.145, 0.0, 0.0, 0.0],
            "source": "yoloe",
          },
        )

    open_vocab = YoloeOpenVocab()
    tool = module._RecoveryConfigDetectTool(
      WrappedConfigDetect(),
      state=state,
      open_vocab_tool=open_vocab,
      frame_dir=ROOT / "logs" / "vision" / "test_recovery",
      config=SimpleNamespace(integrations=SimpleNamespace(vision={"backend": "yoloe"})),
      use_live_vision=True,
    )
    manifest = {
      "image_path": "rgb.npy",
      "depth_path": "depth.npy",
      "camera_info_path": "camera_info.json",
      "T_base_camera": [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]],
    }

    with patch.object(module, "_capture_frame", return_value=manifest):
      result = tool.run(
        module.ToolCall(
          tool="vision.config_detect",
          input={"query": "roller"},
          trace=module.TraceContext(),
        )
      )

    self.assertTrue(result.success, msg=result.error)
    self.assertEqual(result.output["pose_3d"], [0.31, 0.10, 0.145, 0.0, 0.0, 0.0])
    self.assertEqual(result.output["source"], "live_recovery_vision")
    self.assertEqual(state["recovery_vision_backend"], "yoloe")
    self.assertEqual(state["recovery_vision"]["backend"], "yoloe")
    self.assertEqual(open_vocab.calls[0]["query"], "roller")
    self.assertEqual(open_vocab.calls[0]["image_path"], "rgb.npy")

  def test_wrong_table_post_release_move_joints_failure_is_tolerated(self) -> None:
    module = _load_demo_module()
    state = {
      "failure": "wrong-table",
      "wrong_target": "tabletop",
      "misplaced_pose": module.TABLETOP_PLACE_POSE,
      "wrong_table_released": True,
    }

    class FailingMoveJoints:
      spec = SimpleNamespace(name="robot.move_joints")

      def run(self, call):
        return module.ToolResult(
          tool=self.spec.name,
          success=False,
          error="MOVEIT_-2: ACTION_ABORTED: MoveIt planning or execution failed.",
        )

    tool = module._WrongTablePostReleaseMoveJointsTool(
      FailingMoveJoints(),
      state=state,
    )

    result = tool.run(
      module.ToolCall(
        tool="robot.move_joints",
        input={"joints": [0.0] * 6, "speed": module.ARM_MOTION_SPEED, "wait": True},
        trace=module.TraceContext(),
      )
    )

    self.assertTrue(result.success, msg=result.error)
    self.assertIn("Tolerated post-release", result.output["message"])
    self.assertEqual(
      state["post_release_move_joints_failures_tolerated"][0]["error"],
      "MOVEIT_-2: ACTION_ABORTED: MoveIt planning or execution failed.",
    )

  def test_summary_serializer_handles_recursive_outputs(self) -> None:
    module = _load_demo_module()
    recursive_output = {"status": "ok"}
    recursive_output["self"] = recursive_output

    serialized = module._json_safe({"output": recursive_output})

    self.assertEqual(serialized["output"]["status"], "ok")
    self.assertEqual(serialized["output"]["self"], "<recursive dict>")
    json.dumps(serialized)
