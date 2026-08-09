"""Tests for backend-neutral robot tools and skills."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest import TestCase
from unittest.mock import Mock

import requests

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
  sys.path.insert(0, str(SRC))

from sensoragent.agent.bootstrap import build_agent_from_config
from sensoragent.config import load_config
from sensoragent.contracts import ContractValidator
from sensoragent.integrations.robot import FakeRobotControlClient, HttpRobotControlClient
from sensoragent.logger import TaskLogger
from sensoragent.schemas import RobotPose, TraceContext
from sensoragent.schemas import ToolResult
from sensoragent.skills.base import SkillContext
from sensoragent.skills import SkillRegistry, SkillRuntime
from sensoragent.skills.robot import (
  RobotPickSkill,
  RobotPlaceSkill,
  build_oriented_pick_plan_from_points,
  build_place_plan,
  build_top_down_pick_plan,
)
from sensoragent.tools import ToolRegistry, ToolRuntime
from sensoragent.tools.robot import (
  GripperCloseTool,
  GripperGetStateTool,
  GripperOpenTool,
  RobotPlanOrientedPickTool,
  RobotPlanPlaceTool,
  RobotPlanTopDownPickTool,
  RobotGetStateTool,
  RobotMoveJointsTool,
  RobotMoveLinearTool,
  RobotMovePoseTool,
  RobotStopTool,
)


def _build_runtime():
  client = FakeRobotControlClient()
  registry = ToolRegistry()
  for tool in (
    RobotMoveJointsTool(client),
    RobotMovePoseTool(client),
    RobotMoveLinearTool(client),
    GripperOpenTool(client),
    GripperCloseTool(client),
  ):
    registry.register(tool)
  logger = TaskLogger()
  tool_runtime = ToolRuntime(registry, logger, ContractValidator(ROOT / "contracts"))
  skill_registry = SkillRegistry()
  skill_registry.register(RobotPickSkill())
  skill_registry.register(RobotPlaceSkill())
  return client, SkillRuntime(skill_registry, tool_runtime, logger)


class RobotControlTest(TestCase):
  def test_pick_and_place_skills_execute_precomputed_plans(self) -> None:
    client, runtime = _build_runtime()
    trace = TraceContext()
    grasp = RobotPose(
      position=(0.42, 0.10, 0.32),
      orientation=(0.0, 1.0, 0.0, 0.0),
    )
    place = RobotPose(
      position=(0.50, -0.20, 0.36),
      orientation=(0.0, 1.0, 0.0, 0.0),
    )

    pick_result = runtime.invoke(
      "robot.pick",
      {
        "object_id": "roller_01",
        "plan": build_top_down_pick_plan(grasp).to_dict(),
        "close_opening": 0.02,
      },
      trace,
    )
    place_result = runtime.invoke(
      "robot.place",
      {
        "object_id": "roller_01",
        "target": "bin_2_3",
        "plan": build_place_plan(place).to_dict(),
      },
      trace,
    )

    self.assertTrue(pick_result.success)
    self.assertTrue(place_result.success)
    state = client.get_state().state
    self.assertEqual(state["arm"]["pose"], build_place_plan(place).retreat.to_dict())
    self.assertEqual(state["gripper"]["status"], "open")

  def test_pick_skill_falls_back_to_planned_lift_when_cartesian_lift_fails(self) -> None:
    trace = TraceContext()
    grasp = RobotPose(
      position=(0.42, 0.10, 0.32),
      orientation=(0.0, 1.0, 0.0, 0.0),
    )
    plan = build_top_down_pick_plan(grasp)

    class StubToolRuntime:
      def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

      def invoke(self, name: str, input_data: dict, trace_context: TraceContext) -> ToolResult:
        del trace_context
        self.calls.append((name, input_data))
        if (
          name == "robot.move_linear"
          and input_data.get("pose", {}).get("position") == plan.lift.to_dict()["position"]
        ):
          return ToolResult(
            tool=name,
            success=False,
            error="INCOMPLETE_CARTESIAN_PATH: Cartesian path fraction 0.667 is below 0.980.",
          )
        return ToolResult(tool=name, success=True, output={"completed": True})

    tool_runtime = StubToolRuntime()
    result = RobotPickSkill().run(
      call=Mock(
        input={
          "object_id": "roller_01",
          "plan": plan.to_dict(),
          "close_opening": 0.02,
        },
        trace=trace,
      ),
      context=SkillContext(tool_runtime=tool_runtime, logger=TaskLogger()),
    )

    self.assertTrue(result.success, msg=result.error)
    self.assertIn(("robot.move_pose", {"pose": plan.lift.to_dict(), "speed": 0.2}), tool_runtime.calls)

  def test_pick_skill_falls_back_to_planned_waypoints_for_all_sorting_objects(self) -> None:
    trace = TraceContext()
    config = load_config(ROOT / "configs" / "robot_sorting_sim.yaml")

    for object_name, pose_3d in config.scene.objects.items():
      with self.subTest(object_name=object_name):
        profile = {
          **config.scene.release_profiles.get("default", {}),
          **config.scene.release_profiles.get(object_name, {}),
        }
        pick_offset_z = float(profile.get("pick_offset_z", 0.04))
        grasp_orientation = tuple(
          float(value)
          for value in profile.get("grasp_orientation", [0.0, 1.0, 0.0, 0.0])
        )
        grasp = RobotPose(
          position=(
            float(pose_3d[0]),
            float(pose_3d[1]),
            float(pose_3d[2]) + pick_offset_z,
          ),
          orientation=grasp_orientation,
        )
        plan = build_top_down_pick_plan(grasp, pregrasp_distance=0.04)

        class StubToolRuntime:
          def __init__(self) -> None:
            self.calls: list[tuple[str, dict]] = []

          def invoke(self, name: str, input_data: dict, trace_context: TraceContext) -> ToolResult:
            del trace_context
            self.calls.append((name, input_data))
            position = input_data.get("pose", {}).get("position")
            if (
              name == "robot.move_linear"
              and tuple(position or ())
              in {
                tuple(plan.pregrasp.to_dict()["position"]),
                tuple(plan.grasp.to_dict()["position"]),
              }
            ):
              return ToolResult(
                tool=name,
                success=False,
                error="INCOMPLETE_CARTESIAN_PATH: Cartesian path fraction 0.143 is below 0.980.",
              )
            return ToolResult(tool=name, success=True, output={"completed": True})

        tool_runtime = StubToolRuntime()
        result = RobotPickSkill().run(
          call=Mock(
            input={
              "object_id": object_name,
              "plan": plan.to_dict(),
              "close_opening": 0.02,
            },
            trace=trace,
          ),
          context=SkillContext(tool_runtime=tool_runtime, logger=TaskLogger()),
        )

        self.assertTrue(result.success, msg=result.error)
        self.assertIn(
          ("robot.move_pose", {"pose": plan.pregrasp.to_dict(), "speed": 0.2}),
          tool_runtime.calls,
        )
        self.assertIn(
          ("robot.move_pose", {"pose": plan.grasp.to_dict(), "speed": 0.2}),
          tool_runtime.calls,
        )
        self.assertTrue(
          any(stage["step"] == "move_pregrasp_cartesian" for stage in result.output["stages"])
        )
        self.assertTrue(
          any(stage["step"] == "move_grasp_cartesian" for stage in result.output["stages"])
        )

  def test_pick_skill_tolerates_open_gripper_failure_when_already_open(self) -> None:
    trace = TraceContext()
    grasp = RobotPose(
      position=(0.42, 0.10, 0.32),
      orientation=(0.0, 1.0, 0.0, 0.0),
    )
    plan = build_top_down_pick_plan(grasp)

    class StubToolRuntime:
      def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

      def invoke(self, name: str, input_data: dict, trace_context: TraceContext) -> ToolResult:
        del trace_context
        self.calls.append((name, input_data))
        if name == "gripper.open":
          return ToolResult(
            tool=name,
            success=False,
            error="GRIPPER_FAILED: Gripper did not reach the target or detect contact.",
          )
        if name == "gripper.get_state":
          return ToolResult(tool=name, success=True, output={"state": {"opening": 0.0847}})
        return ToolResult(tool=name, success=True, output={"completed": True})

    tool_runtime = StubToolRuntime()
    result = RobotPickSkill().run(
      call=Mock(
        input={
          "object_id": "roller_01",
          "plan": plan.to_dict(),
          "close_opening": 0.02,
        },
        trace=trace,
      ),
      context=SkillContext(tool_runtime=tool_runtime, logger=TaskLogger()),
    )

    self.assertTrue(result.success, msg=result.error)
    self.assertIn(("gripper.get_state", {}), tool_runtime.calls)

  def test_pick_skill_tolerates_close_timeout_when_gripper_state_is_held(self) -> None:
    trace = TraceContext()
    grasp = RobotPose(
      position=(0.42, 0.10, 0.32),
      orientation=(0.0, 1.0, 0.0, 0.0),
    )
    plan = build_top_down_pick_plan(grasp)

    class StubToolRuntime:
      def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

      def invoke(self, name: str, input_data: dict, trace_context: TraceContext) -> ToolResult:
        del trace_context
        self.calls.append((name, input_data))
        if name == "gripper.close":
          return ToolResult(
            tool=name,
            success=False,
            error="MOTION_TIMEOUT: MOTION_TIMEOUT",
          )
        if name == "gripper.get_state":
          return ToolResult(
            tool=name,
            success=True,
            output={"state": {"opening": 0.0398, "grasped": True}},
          )
        return ToolResult(tool=name, success=True, output={"completed": True})

    tool_runtime = StubToolRuntime()
    result = RobotPickSkill().run(
      call=Mock(
        input={
          "object_id": "block",
          "plan": plan.to_dict(),
          "close_opening": 0.032,
          "gripper_force": 1.0,
        },
        trace=trace,
      ),
      context=SkillContext(tool_runtime=tool_runtime, logger=TaskLogger()),
    )

    self.assertTrue(result.success, msg=result.error)
    self.assertIn(("gripper.get_state", {}), tool_runtime.calls)
    self.assertEqual(result.output["plan"], plan.to_dict())
    self.assertTrue(
      any(stage["step"] == "close_gripper_state_check" for stage in result.output["stages"])
    )

  def test_robot_tools_register_from_project_configuration(self) -> None:
    bundle = build_agent_from_config(ROOT / "configs" / "robot_mock.yaml")

    self.assertIn("robot.move_pose", bundle.tool_registry.names())
    self.assertIn("robot.plan_top_down_pick", bundle.tool_registry.names())
    self.assertIn("robot.plan_oriented_pick", bundle.tool_registry.names())
    self.assertIn("robot.plan_place", bundle.tool_registry.names())
    self.assertIn("gripper.close", bundle.tool_registry.names())
    self.assertIn("robot.pick", bundle.skill_registry.names())
    self.assertIn("robot.place", bundle.skill_registry.names())

  def test_place_skill_accepts_pre_approach_joints(self) -> None:
    client, runtime = _build_runtime()
    trace = TraceContext()
    place = RobotPose(
      position=(0.50, -0.20, 0.36),
      orientation=(0.0, 1.0, 0.0, 0.0),
    )

    result = runtime.invoke(
      "robot.place",
      {
        "object_id": "roller_01",
        "target": "bin_2_3",
        "plan": build_place_plan(place).to_dict(),
        "pre_approach_joints": [0.2, 0.0, 0.0, 0.0, 0.0, 0.0],
      },
      trace,
    )

    self.assertTrue(result.success)
    self.assertEqual(
      result.output["completed_steps"],
      [
        "move_pre_approach_joints",
        "move_approach",
        "move_place",
        "open_gripper",
        "retreat",
      ],
    )
    state = client.get_state().state
    self.assertEqual(state["arm"]["pose"], build_place_plan(place).retreat.to_dict())
    self.assertEqual(state["arm"]["joints"], [0.2, 0.0, 0.0, 0.0, 0.0, 0.0])

  def test_http_backend_maps_pose_motion_to_bridge_request(self) -> None:
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {
      "success": True,
      "error_code": "OK",
      "message": "Motion completed.",
      "state": {"arm": {"status": "idle"}},
    }
    session = Mock()
    session.request.return_value = response
    client = HttpRobotControlClient(
      "http://bridge:8765/",
      timeout_seconds=10.0,
      session=session,
    )
    pose = RobotPose(
      position=(0.4, 0.1, 0.3),
      orientation=(0.0, 1.0, 0.0, 0.0),
    )

    result = client.move_pose(pose, speed=0.3, linear=True, wait=True)

    self.assertTrue(result.success)
    session.request.assert_called_once_with(
      "POST",
      "http://bridge:8765/move-linear",
      json={"pose": pose.to_dict(), "speed": 0.3, "wait": True},
      timeout=10.0,
    )

  def test_http_motion_timeout_requests_safety_stop(self) -> None:
    session = Mock()
    session.request.side_effect = [
      requests.Timeout("motion timed out"),
      Mock(),
    ]
    client = HttpRobotControlClient(
      "http://bridge:8765",
      timeout_seconds=120.0,
      session=session,
    )

    result = client.move_joints(
      [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
      speed=0.2,
      wait=True,
    )

    self.assertFalse(result.success)
    self.assertEqual(result.error_code, "ROBOT_BRIDGE_TIMEOUT")
    self.assertEqual(session.request.call_count, 2)
    self.assertEqual(session.request.call_args_list[1].args, ("POST", "http://bridge:8765/stop"))
    self.assertEqual(session.request.call_args_list[1].kwargs["timeout"], 5.0)

  def test_atomic_robot_tools_share_one_backend_state(self) -> None:
    client = FakeRobotControlClient()
    registry = ToolRegistry()
    for tool in (
      RobotGetStateTool(client),
      RobotMoveJointsTool(client),
      RobotStopTool(client),
      GripperGetStateTool(client),
    ):
      registry.register(tool)
    runtime = ToolRuntime(
      registry,
      TaskLogger(),
      ContractValidator(ROOT / "contracts"),
    )
    trace = TraceContext()

    move = runtime.invoke(
      "robot.move_joints",
      {"joints": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6]},
      trace,
    )
    state = runtime.invoke("robot.get_state", {}, trace)
    stop = runtime.invoke("robot.stop", {}, trace)
    gripper = runtime.invoke("gripper.get_state", {}, trace)

    self.assertTrue(move.success)
    self.assertEqual(
      state.output["state"]["arm"]["joints"],
      [0.1, 0.2, 0.3, 0.4, 0.5, 0.6],
    )
    self.assertEqual(stop.output["state"]["arm"]["status"], "stopped")
    self.assertEqual(gripper.output["state"]["status"], "open")

  def test_planning_helpers_preserve_frame_and_orientation(self) -> None:
    pose = RobotPose(
      position=(0.4, 0.1, 0.2),
      orientation=(0.0, 0.0, 0.0, 1.0),
      frame_id="world",
    )

    pick = build_top_down_pick_plan(pose, approach_distance=0.2)
    place = build_place_plan(pose, clearance=0.1)

    self.assertEqual(pick.approach.position, (0.4, 0.1, 0.4))
    self.assertEqual(pick.approach.orientation, pose.orientation)
    self.assertEqual(place.retreat.frame_id, "world")

  def test_top_down_pick_and_place_planning_tools_emit_plans(self) -> None:
    registry = ToolRegistry()
    registry.register(RobotPlanTopDownPickTool())
    registry.register(RobotPlanPlaceTool())
    runtime = ToolRuntime(registry, TaskLogger(), ContractValidator(ROOT / "contracts"))
    trace = TraceContext()
    pose = {
      "position": [0.4, 0.1, 0.2],
      "orientation": [0.0, 0.0, 0.0, 1.0],
      "frame_id": "base_link",
    }

    pick = runtime.invoke(
      "robot.plan_top_down_pick",
      {"grasp_pose": pose, "approach_distance": 0.2},
      trace,
    )
    place = runtime.invoke(
      "robot.plan_place",
      {"place_pose": pose, "clearance": 0.1},
      trace,
    )

    self.assertTrue(pick.success)
    self.assertEqual(pick.output["plan"]["approach"]["position"], [0.4, 0.1, 0.4])
    self.assertTrue(place.success)
    self.assertEqual(place.output["plan"]["retreat"]["position"], [0.4, 0.1, 0.30000000000000004])

  def test_top_down_pick_tool_accepts_vision_pose_3d(self) -> None:
    registry = ToolRegistry()
    registry.register(RobotPlanTopDownPickTool())
    runtime = ToolRuntime(registry, TaskLogger(), ContractValidator(ROOT / "contracts"))

    result = runtime.invoke(
      "robot.plan_top_down_pick",
      {
        "pose_3d": [0.42, -0.13, 0.08, 0.0, 0.0, 1.57],
        "position_offset": [0.0, 0.0, 0.02],
      },
      TraceContext(),
    )

    self.assertTrue(result.success)
    self.assertEqual(result.output["grasp_pose"]["position"], [0.42, -0.13, 0.1])
    self.assertEqual(result.output["grasp_pose"]["orientation"], [0.0, 1.0, 0.0, 0.0])
    self.assertEqual(result.output["plan"]["pregrasp"]["position"], [0.42, -0.13, 0.13])

  def test_oriented_pick_planner_builds_plan_from_point_cloud(self) -> None:
    points = []
    for y in [index * 0.01 for index in range(-20, 21)]:
      radius = 0.03 if y >= 0 else 0.01
      points.extend(
        [
          [0.4 + radius, y, 0.2],
          [0.4 - radius, y, 0.2],
          [0.4, y, 0.2 + radius],
          [0.4, y, 0.2 - radius],
        ]
      )

    plan = build_oriented_pick_plan_from_points(points)

    self.assertGreater(plan.grasp.position[1], -0.01)
    self.assertEqual(plan.grasp.frame_id, "base_link")

    registry = ToolRegistry()
    registry.register(RobotPlanOrientedPickTool())
    runtime = ToolRuntime(registry, TaskLogger(), ContractValidator(ROOT / "contracts"))
    result = runtime.invoke("robot.plan_oriented_pick", {"points": points}, TraceContext())

    self.assertTrue(result.success)
    self.assertIn("plan", result.output)
    self.assertEqual(set(result.output["plan"]), {"approach", "pregrasp", "grasp", "lift"})
