#!/usr/bin/env python3
"""HTTP-to-ROS 2 bridge for RM65-B MoveIt and Robotiq simulation control."""

from __future__ import annotations

import json
import math
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import rclpy
from action_msgs.msg import GoalStatus
from control_msgs.action import GripperCommand
from geometry_msgs.msg import Pose
from moveit_msgs.action import ExecuteTrajectory, MoveGroup
from moveit_msgs.msg import (
    Constraints,
    CollisionObject,
    JointConstraint,
    MoveItErrorCodes,
    OrientationConstraint,
    PlanningScene,
    PositionConstraint,
)
from moveit_msgs.srv import GetCartesianPath
from rclpy.action import ActionClient
from rclpy.duration import Duration
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.qos import QoSDurabilityPolicy, QoSProfile
from rclpy.time import Time
from sensor_msgs.msg import JointState
from shape_msgs.msg import SolidPrimitive
from tf2_ros import Buffer, TransformException, TransformListener

from sensoragent_robot_bridge.gripper_mapping import (
    closure_to_opening,
    opening_to_closure,
)
from sensoragent_robot_bridge.scene_obstacles import camera_rig_collision_objects
from sensoragent_robot_bridge.trajectory_scaling import (
    MAX_SPEED,
    scale_joint_trajectory_speed,
)


MOVEIT_MAX_SCALING_FACTOR = 1.0


def _response(
    success: bool,
    *,
    error_code: str = "OK",
    message: str = "OK",
    state: dict | None = None,
) -> dict:
    return {
        "success": success,
        "error_code": error_code,
        "message": message,
        "state": state or {},
    }


class RobotBridgeNode(Node):
    """Controls MoveIt and the simulated gripper for HTTP callers."""

    def __init__(self) -> None:
        super().__init__("sensoragent_robot_bridge")

        self.declare_parameter("bind_host", "127.0.0.1")
        self.declare_parameter("bind_port", 8765)
        self.declare_parameter("base_frame", "base_link")
        self.declare_parameter("end_effector_link", "robotiq_85_tcp")
        self.declare_parameter("move_group", "rm_group")
        self.declare_parameter(
            "joint_names",
            ["joint1", "joint2", "joint3", "joint4", "joint5", "joint6"],
        )
        self.declare_parameter(
            "left_gripper_joint",
            "robotiq_85_left_knuckle_joint",
        )
        self.declare_parameter(
            "right_gripper_joint",
            "robotiq_85_right_knuckle_joint",
        )
        self.declare_parameter("maximum_gripper_opening", 0.0848)
        self.declare_parameter("maximum_gripper_effort", 20.0)
        self.declare_parameter("planning_attempts", 10)
        self.declare_parameter("planning_time", 10.0)
        self.declare_parameter("motion_timeout", 90.0)
        self.declare_parameter("gripper_timeout", 15.0)
        self.declare_parameter("cartesian_max_step", 0.01)
        self.declare_parameter("cartesian_min_fraction", 0.98)
        self.declare_parameter("position_tolerance", 0.005)
        self.declare_parameter("orientation_tolerance", 0.20)

        self._bind_host = str(self.get_parameter("bind_host").value)
        self._bind_port = int(self.get_parameter("bind_port").value)
        self._base_frame = str(self.get_parameter("base_frame").value)
        self._end_effector_link = str(
            self.get_parameter("end_effector_link").value
        )
        self._move_group_name = str(self.get_parameter("move_group").value)
        self._joint_names = list(self.get_parameter("joint_names").value)
        self._left_gripper_joint = str(
            self.get_parameter("left_gripper_joint").value
        )
        self._right_gripper_joint = str(
            self.get_parameter("right_gripper_joint").value
        )
        self._maximum_gripper_opening = float(
            self.get_parameter("maximum_gripper_opening").value
        )
        self._maximum_gripper_effort = float(
            self.get_parameter("maximum_gripper_effort").value
        )
        self._planning_attempts = int(
            self.get_parameter("planning_attempts").value
        )
        self._planning_time = float(self.get_parameter("planning_time").value)
        self._motion_timeout = float(self.get_parameter("motion_timeout").value)
        self._gripper_timeout = float(
            self.get_parameter("gripper_timeout").value
        )
        self._cartesian_max_step = float(
            self.get_parameter("cartesian_max_step").value
        )
        self._cartesian_min_fraction = float(
            self.get_parameter("cartesian_min_fraction").value
        )
        self._position_tolerance = float(
            self.get_parameter("position_tolerance").value
        )
        self._orientation_tolerance = float(
            self.get_parameter("orientation_tolerance").value
        )

        self._move_group_client = ActionClient(self, MoveGroup, "/move_action")
        self._execute_client = ActionClient(
            self,
            ExecuteTrajectory,
            "/execute_trajectory",
        )
        self._gripper_client = ActionClient(
            self,
            GripperCommand,
            "/robotiq_gripper_controller/gripper_cmd",
        )
        self._cartesian_client = self.create_client(
            GetCartesianPath,
            "/compute_cartesian_path",
        )
        planning_scene_qos = QoSProfile(
            depth=10,
            durability=QoSDurabilityPolicy.TRANSIENT_LOCAL,
        )
        self._planning_scene_pub = self.create_publisher(
            PlanningScene,
            "/planning_scene",
            planning_scene_qos,
        )

        self._tf_buffer = Buffer()
        self._tf_listener = TransformListener(self._tf_buffer, self)
        self.create_subscription(JointState, "/joint_states", self._on_joint_state, 20)

        self._state_lock = threading.Lock()
        self._active_lock = threading.Lock()
        self._command_lock = threading.Lock()
        self._joint_positions: dict[str, float] = {}
        self._arm_status = "idle"
        self._gripper_status = "unknown"
        self._gripper_grasped = False
        self._active_goals: dict[str, tuple[Any, Any]] = {}
        self._pending_actions: set[str] = set()
        self._cancel_requested: set[str] = set()
        self._http_server: ThreadingHTTPServer | None = None
        self._http_thread: threading.Thread | None = None

    def _on_joint_state(self, message: JointState) -> None:
        with self._state_lock:
            for index, name in enumerate(message.name):
                if index < len(message.position):
                    self._joint_positions[name] = float(message.position[index])

    @staticmethod
    def _wait_future(future, timeout: float):
        completed = threading.Event()
        future.add_done_callback(lambda _: completed.set())
        if not completed.wait(timeout):
            return None
        return future.result()

    def _set_arm_status(self, status: str) -> None:
        with self._state_lock:
            self._arm_status = status

    def _set_pending_action(self, key: str) -> None:
        with self._active_lock:
            self._pending_actions.add(key)

    def _clear_pending_action(
        self,
        key: str,
        *,
        clear_cancel_request: bool = False,
    ) -> None:
        with self._active_lock:
            self._pending_actions.discard(key)
            if clear_cancel_request:
                self._cancel_requested.discard(key)

    def _set_active_goal(self, key: str, goal_handle, result_future) -> None:
        with self._active_lock:
            self._pending_actions.discard(key)
            self._active_goals[key] = (goal_handle, result_future)

    def _clear_active_goal(self, key: str, goal_handle=None) -> None:
        with self._active_lock:
            current = self._active_goals.get(key)
            if goal_handle is None or (
                current is not None and current[0] is goal_handle
            ):
                self._active_goals.pop(key, None)
                self._cancel_requested.discard(key)

    def _has_active_goal(self) -> bool:
        with self._active_lock:
            return bool(self._active_goals or self._pending_actions)

    def _cancellation_finished(self, key: str, goal_handle, future) -> None:
        try:
            future.result()
        except Exception as exc:  # ROS callback boundary
            self.get_logger().error(f"Canceled action result failed: {exc}")
        if key == "arm":
            self._set_arm_status("stopped")
        else:
            with self._state_lock:
                self._gripper_status = "stopped"
        self._clear_active_goal(key, goal_handle)

    def _cancel_goal(
        self,
        key: str,
        goal_handle,
        result_future,
        timeout: float = 5.0,
    ) -> bool:
        cancel_response = self._wait_future(
            goal_handle.cancel_goal_async(),
            min(timeout, 3.0),
        )
        if cancel_response is None or not cancel_response.goals_canceling:
            if result_future.done():
                try:
                    result_future.result()
                finally:
                    self._clear_active_goal(key, goal_handle)
                return True
            return False

        result_response = self._wait_future(result_future, timeout)
        if result_response is None:
            result_future.add_done_callback(
                lambda future: self._cancellation_finished(
                    key,
                    goal_handle,
                    future,
                )
            )
            return False

        if key == "arm":
            self._set_arm_status("stopped")
        else:
            with self._state_lock:
                self._gripper_status = "stopped"
        self._clear_active_goal(key, goal_handle)
        return result_response.status == GoalStatus.STATUS_CANCELED

    @staticmethod
    def _result_status_error(status: int) -> str | None:
        if status == GoalStatus.STATUS_SUCCEEDED:
            return None
        if status == GoalStatus.STATUS_CANCELED:
            return "ACTION_CANCELED"
        if status == GoalStatus.STATUS_ABORTED:
            return "ACTION_ABORTED"
        return f"ACTION_STATUS_{status}"

    def _send_action(
        self,
        client: ActionClient,
        goal,
        *,
        key: str,
        timeout: float,
    ):
        self._set_pending_action(key)
        if not client.wait_for_server(timeout_sec=min(timeout, 15.0)):
            self._clear_pending_action(key, clear_cancel_request=True)
            return None, "ACTION_SERVER_UNAVAILABLE"

        goal_future = client.send_goal_async(goal)
        goal_handle = self._wait_future(goal_future, 5.0)
        if goal_handle is None:
            self._clear_pending_action(key, clear_cancel_request=True)
            return None, "GOAL_RESPONSE_TIMEOUT"
        if not goal_handle.accepted:
            self._clear_pending_action(key, clear_cancel_request=True)
            return None, "GOAL_REJECTED"

        result_future = goal_handle.get_result_async()
        self._set_active_goal(key, goal_handle, result_future)
        with self._active_lock:
            cancel_requested = key in self._cancel_requested
        if cancel_requested:
            canceled = self._cancel_goal(
                key,
                goal_handle,
                result_future,
            )
            return None, "ACTION_CANCELED" if canceled else "CANCEL_PENDING"

        result_response = self._wait_future(result_future, timeout)
        if result_response is None:
            canceled = self._cancel_goal(
                key,
                goal_handle,
                result_future,
            )
            return None, "MOTION_TIMEOUT" if canceled else "CANCEL_PENDING"

        self._clear_active_goal(key, goal_handle)
        status_error = self._result_status_error(result_response.status)
        if status_error is not None:
            return result_response.result, status_error
        return result_response.result, None

    def _pose_from_payload(self, value: Any) -> tuple[Pose, str]:
        if not isinstance(value, dict):
            raise ValueError("pose must be an object")
        position = value.get("position")
        orientation = value.get("orientation")
        if not isinstance(position, list) or len(position) != 3:
            raise ValueError("pose.position must contain three values")
        if not isinstance(orientation, list) or len(orientation) != 4:
            raise ValueError("pose.orientation must contain four values")
        values = position + orientation
        if not all(
            isinstance(item, (int, float)) and not isinstance(item, bool)
            for item in values
        ):
            raise ValueError("pose values must be numeric")

        quaternion_norm = math.sqrt(sum(float(item) ** 2 for item in orientation))
        if quaternion_norm < 1e-9:
            raise ValueError("pose.orientation must be a non-zero quaternion")

        pose = Pose()
        pose.position.x = float(position[0])
        pose.position.y = float(position[1])
        pose.position.z = float(position[2])
        pose.orientation.x = float(orientation[0]) / quaternion_norm
        pose.orientation.y = float(orientation[1]) / quaternion_norm
        pose.orientation.z = float(orientation[2]) / quaternion_norm
        pose.orientation.w = float(orientation[3]) / quaternion_norm
        frame_id = value.get("frame_id", self._base_frame)
        if not isinstance(frame_id, str) or not frame_id:
            raise ValueError("pose.frame_id must be a non-empty string")
        return pose, frame_id

    @staticmethod
    def _speed(value: Any) -> float:
        speed = float(value)
        if speed <= 0.0 or speed > MAX_SPEED:
            raise ValueError(f"speed must be greater than 0 and at most {MAX_SPEED:g}")
        return speed

    def _camera_rig_collision_objects(self) -> list[CollisionObject]:
        return camera_rig_collision_objects(frame_id=self._base_frame)

    def get_scene_obstacles(self) -> dict:
        objects = []
        for collision in self._camera_rig_collision_objects():
            primitive = collision.primitives[0]
            pose = collision.primitive_poses[0]
            objects.append(
                {
                    "id": collision.id,
                    "frame_id": collision.header.frame_id,
                    "center": [
                        pose.position.x,
                        pose.position.y,
                        pose.position.z,
                    ],
                    "size": list(primitive.dimensions),
                }
            )
        return _response(
            True,
            message="MoveIt static scene obstacles configured.",
            state={"collision_objects": objects},
        )

    def _publish_static_obstacles(self) -> None:
        scene = PlanningScene()
        scene.is_diff = True
        scene.world.collision_objects = self._camera_rig_collision_objects()
        self._planning_scene_pub.publish(scene)

    def _move_group_goal(
        self,
        constraints: Constraints,
        speed: float,
    ) -> MoveGroup.Goal:
        goal = MoveGroup.Goal()
        goal.request.group_name = self._move_group_name
        goal.request.start_state.is_diff = True
        goal.request.goal_constraints = [constraints]
        goal.request.num_planning_attempts = self._planning_attempts
        goal.request.allowed_planning_time = self._planning_time
        goal.request.max_velocity_scaling_factor = min(speed, MOVEIT_MAX_SCALING_FACTOR)
        goal.request.max_acceleration_scaling_factor = min(speed, MOVEIT_MAX_SCALING_FACTOR)
        goal.planning_options.plan_only = False
        goal.planning_options.look_around = False
        goal.planning_options.replan = True
        goal.planning_options.replan_attempts = 2
        goal.planning_options.replan_delay = 0.2
        goal.planning_options.planning_scene_diff.is_diff = True
        goal.planning_options.planning_scene_diff.robot_state.is_diff = True
        goal.planning_options.planning_scene_diff.world.collision_objects = (
            self._camera_rig_collision_objects()
        )
        return goal

    def _run_move_group(
        self,
        constraints: Constraints,
        *,
        speed: float,
    ) -> dict:
        self._set_arm_status("moving")
        self._publish_static_obstacles()
        result, error = self._send_action(
            self._move_group_client,
            self._move_group_goal(constraints, speed),
            key="arm",
            timeout=self._motion_timeout,
        )
        if error is not None:
            if error == "ACTION_CANCELED":
                self._set_arm_status("stopped")
            elif error == "CANCEL_PENDING":
                self._set_arm_status("canceling")
            else:
                self._set_arm_status("error")
            if result is not None and hasattr(result, "error_code"):
                return _response(
                    False,
                    error_code=f"MOVEIT_{result.error_code.val}",
                    message=f"{error}: MoveIt planning or execution failed.",
                    state=self._state(),
                )
            return _response(False, error_code=error, message=error)
        if result.error_code.val != MoveItErrorCodes.SUCCESS:
            self._set_arm_status("error")
            return _response(
                False,
                error_code=f"MOVEIT_{result.error_code.val}",
                message="MoveIt planning or execution failed.",
                state=self._state(),
            )
        self._set_arm_status("idle")
        return _response(True, message="Motion completed.", state=self._state())

    def move_joints(self, payload: dict) -> dict:
        joints = payload.get("joints")
        if not isinstance(joints, list) or len(joints) != len(self._joint_names):
            raise ValueError(
                f"joints must contain {len(self._joint_names)} values"
            )
        if not all(
            isinstance(item, (int, float)) and not isinstance(item, bool)
            for item in joints
        ):
            raise ValueError("joints must contain numeric values")
        speed = self._speed(payload.get("speed", 0.2))
        wait = payload.get("wait", True)
        if not isinstance(wait, bool):
            raise ValueError("wait must be boolean")
        if not wait:
            raise ValueError("wait=false is not supported by the simulation bridge")

        constraints = Constraints()
        constraints.name = "sensoragent_joint_goal"
        for name, position in zip(self._joint_names, joints):
            joint = JointConstraint()
            joint.joint_name = name
            joint.position = float(position)
            joint.tolerance_above = 0.001
            joint.tolerance_below = 0.001
            joint.weight = 1.0
            constraints.joint_constraints.append(joint)

        if not self._command_lock.acquire(blocking=False):
            return _response(False, error_code="ROBOT_BUSY", message="Robot is busy.")
        try:
            if self._has_active_goal():
                return _response(
                    False,
                    error_code="ROBOT_BUSY",
                    message="Robot already has an active goal.",
                )
            return self._run_move_group(constraints, speed=speed)
        finally:
            self._command_lock.release()

    def move_pose(self, payload: dict) -> dict:
        pose, frame_id = self._pose_from_payload(payload.get("pose"))
        speed = self._speed(payload.get("speed", 0.2))
        wait = payload.get("wait", True)
        if not isinstance(wait, bool):
            raise ValueError("wait must be boolean")
        if not wait:
            raise ValueError("wait=false is not supported by the simulation bridge")

        constraints = Constraints()
        constraints.name = "sensoragent_pose_goal"

        position = PositionConstraint()
        position.header.frame_id = frame_id
        position.link_name = self._end_effector_link
        position.weight = 1.0
        primitive = SolidPrimitive()
        primitive.type = SolidPrimitive.SPHERE
        primitive.dimensions = [self._position_tolerance]
        region_pose = Pose()
        region_pose.position = pose.position
        region_pose.orientation.w = 1.0
        position.constraint_region.primitives.append(primitive)
        position.constraint_region.primitive_poses.append(region_pose)
        constraints.position_constraints.append(position)

        orientation = OrientationConstraint()
        orientation.header.frame_id = frame_id
        orientation.link_name = self._end_effector_link
        orientation.orientation = pose.orientation
        orientation.absolute_x_axis_tolerance = self._orientation_tolerance
        orientation.absolute_y_axis_tolerance = self._orientation_tolerance
        orientation.absolute_z_axis_tolerance = self._orientation_tolerance
        orientation.weight = 1.0
        constraints.orientation_constraints.append(orientation)

        if not self._command_lock.acquire(blocking=False):
            return _response(False, error_code="ROBOT_BUSY", message="Robot is busy.")
        try:
            if self._has_active_goal():
                return _response(
                    False,
                    error_code="ROBOT_BUSY",
                    message="Robot already has an active goal.",
                )
            return self._run_move_group(constraints, speed=speed)
        finally:
            self._command_lock.release()

    def move_linear(self, payload: dict) -> dict:
        pose, frame_id = self._pose_from_payload(payload.get("pose"))
        speed = self._speed(payload.get("speed", 0.2))
        wait = payload.get("wait", True)
        if not isinstance(wait, bool):
            raise ValueError("wait must be boolean")
        if not wait:
            raise ValueError("wait=false is not supported by the simulation bridge")

        if not self._command_lock.acquire(blocking=False):
            return _response(False, error_code="ROBOT_BUSY", message="Robot is busy.")
        try:
            if self._has_active_goal():
                return _response(
                    False,
                    error_code="ROBOT_BUSY",
                    message="Robot already has an active goal.",
                )
            if not self._cartesian_client.wait_for_service(timeout_sec=5.0):
                return _response(
                    False,
                    error_code="CARTESIAN_SERVICE_UNAVAILABLE",
                    message="MoveIt Cartesian path service is unavailable.",
                )

            request = GetCartesianPath.Request()
            request.header.frame_id = frame_id
            request.start_state.is_diff = True
            request.group_name = self._move_group_name
            request.link_name = self._end_effector_link
            request.waypoints = [pose]
            request.max_step = self._cartesian_max_step
            request.jump_threshold = 0.0
            request.prismatic_jump_threshold = 0.0
            request.revolute_jump_threshold = 0.0
            request.avoid_collisions = True

            self._publish_static_obstacles()
            self._set_arm_status("planning")
            service_result = self._wait_future(
                self._cartesian_client.call_async(request),
                self._planning_time + 5.0,
            )
            if service_result is None:
                self._set_arm_status("error")
                return _response(
                    False,
                    error_code="CARTESIAN_PLANNING_TIMEOUT",
                    message="Cartesian path planning timed out.",
                )
            if service_result.error_code.val != MoveItErrorCodes.SUCCESS:
                self._set_arm_status("error")
                return _response(
                    False,
                    error_code=f"MOVEIT_{service_result.error_code.val}",
                    message="MoveIt Cartesian planning failed.",
                )
            if service_result.fraction < self._cartesian_min_fraction:
                self._set_arm_status("error")
                return _response(
                    False,
                    error_code="INCOMPLETE_CARTESIAN_PATH",
                    message=(
                        "Cartesian path fraction "
                        f"{service_result.fraction:.3f} is below "
                        f"{self._cartesian_min_fraction:.3f}."
                    ),
                )

            goal = ExecuteTrajectory.Goal()
            scale_joint_trajectory_speed(
                service_result.solution.joint_trajectory,
                speed,
            )
            goal.trajectory = service_result.solution
            self._set_arm_status("moving")
            result, error = self._send_action(
                self._execute_client,
                goal,
                key="arm",
                timeout=self._motion_timeout,
            )
            if error is not None:
                if error == "ACTION_CANCELED":
                    self._set_arm_status("stopped")
                elif error == "CANCEL_PENDING":
                    self._set_arm_status("canceling")
                else:
                    self._set_arm_status("error")
                return _response(False, error_code=error, message=error)
            if result.error_code.val != MoveItErrorCodes.SUCCESS:
                self._set_arm_status("error")
                return _response(
                    False,
                    error_code=f"MOVEIT_{result.error_code.val}",
                    message="Cartesian trajectory execution failed.",
                    state=self._state(),
                )
            self._set_arm_status("idle")
            return _response(
                True,
                message="Linear motion completed.",
                state=self._state(),
            )
        finally:
            self._command_lock.release()

    def command_gripper(self, payload: dict, *, closing: bool) -> dict:
        opening = float(
            payload.get(
                "opening",
                0.0 if closing else self._maximum_gripper_opening,
            )
        )
        if opening < 0.0 or opening > self._maximum_gripper_opening:
            raise ValueError(
                "opening must be between 0 and "
                f"{self._maximum_gripper_opening}"
            )
        force = float(payload.get("force", 0.5 if closing else 0.2))
        speed = float(payload.get("speed", 0.5))
        if force < 0.0 or force > 1.0:
            raise ValueError("force must be between 0 and 1")
        if speed <= 0.0 or speed > MAX_SPEED:
            raise ValueError(f"speed must be greater than 0 and at most {MAX_SPEED:g}")

        if not self._command_lock.acquire(blocking=False):
            return _response(False, error_code="ROBOT_BUSY", message="Robot is busy.")
        try:
            if self._has_active_goal():
                return _response(
                    False,
                    error_code="ROBOT_BUSY",
                    message="Robot already has an active goal.",
                )
            closure = opening_to_closure(
                opening,
                self._maximum_gripper_opening,
            )
            goal = GripperCommand.Goal()
            goal.command.position = closure
            goal.command.max_effort = max(
                0.1,
                force * self._maximum_gripper_effort,
            )
            with self._state_lock:
                self._gripper_status = "closing" if closing else "opening"
                self._gripper_grasped = False

            result, error = self._send_action(
                self._gripper_client,
                goal,
                key="gripper",
                timeout=self._gripper_timeout,
            )
            if error is not None:
                with self._state_lock:
                    if error == "ACTION_CANCELED":
                        self._gripper_status = "stopped"
                    elif error == "CANCEL_PENDING":
                        self._gripper_status = "canceling"
                    else:
                        self._gripper_status = "error"
                return _response(False, error_code=error, message=error)

            with self._state_lock:
                self._gripper_grasped = bool(closing and result.stalled)
                if result.stalled:
                    self._gripper_status = "grasped" if closing else "stalled"
                elif result.reached_goal:
                    self._gripper_status = "closed" if closing else "open"
                else:
                    self._gripper_status = "error"

            success = bool(result.reached_goal or (closing and result.stalled))
            return _response(
                success,
                error_code="OK" if success else "GRIPPER_FAILED",
                message=(
                    "Gripper command completed."
                    if success
                    else "Gripper did not reach the target or detect contact."
                ),
                state=self._state(),
            )
        finally:
            self._command_lock.release()

    def stop(self) -> dict:
        with self._active_lock:
            pending = set(self._pending_actions)
            active = list(self._active_goals.items())
            self._cancel_requested.update(pending)

        if pending:
            with self._state_lock:
                self._arm_status = "canceling"
                if self._gripper_status in ("opening", "closing"):
                    self._gripper_status = "canceling"
            return _response(
                False,
                error_code="CANCEL_PENDING",
                message="Cancellation queued while the action goal is being submitted.",
                state=self._state(),
            )

        canceled = True
        for key, active_goal in active:
            goal_handle, result_future = active_goal
            if not self._cancel_goal(key, goal_handle, result_future):
                canceled = False

        with self._state_lock:
            if canceled:
                self._arm_status = "stopped"
                if self._gripper_status in (
                    "opening",
                    "closing",
                    "canceling",
                ):
                    self._gripper_status = "stopped"
            else:
                self._arm_status = "canceling"
                if self._gripper_status in ("opening", "closing"):
                    self._gripper_status = "canceling"
        return _response(
            canceled,
            error_code="OK" if canceled else "CANCEL_PENDING",
            message=(
                "Active motions canceled."
                if canceled
                else "Cancellation was requested but has not reached a terminal state."
            ),
            state=self._state(),
        )

    def _pose_state(self) -> dict | None:
        try:
            transform = self._tf_buffer.lookup_transform(
                self._base_frame,
                self._end_effector_link,
                Time(),
                timeout=Duration(seconds=0.2),
            )
        except TransformException:
            return None
        translation = transform.transform.translation
        rotation = transform.transform.rotation
        return {
            "position": [translation.x, translation.y, translation.z],
            "orientation": [rotation.x, rotation.y, rotation.z, rotation.w],
            "frame_id": self._base_frame,
        }

    def _gripper_state(self) -> dict:
        with self._state_lock:
            left = self._joint_positions.get(self._left_gripper_joint, 0.0)
            right = self._joint_positions.get(self._right_gripper_joint, 0.0)
            return {
                "status": self._gripper_status,
                "opening": closure_to_opening(
                    left + right,
                    self._maximum_gripper_opening,
                ),
                "grasped": self._gripper_grasped,
            }

    def _state(self) -> dict:
        with self._state_lock:
            arm_status = self._arm_status
            joints = [
                self._joint_positions.get(name, 0.0)
                for name in self._joint_names
            ]
        return {
            "arm": {
                "status": arm_status,
                "joints": joints,
                "pose": self._pose_state(),
            },
            "gripper": self._gripper_state(),
        }

    def get_state(self) -> dict:
        return _response(True, state=self._state())

    def get_gripper_state(self) -> dict:
        return _response(True, state=self._gripper_state())

    def get_ready(self) -> dict:
        state = {
            "move_action": self._move_group_client.server_is_ready(),
            "execute_trajectory": self._execute_client.server_is_ready(),
            "gripper_cmd": self._gripper_client.server_is_ready(),
            "cartesian_path": self._cartesian_client.service_is_ready(),
        }
        return _response(
            all(state.values()),
            error_code="OK" if all(state.values()) else "ROS_INTERFACE_UNAVAILABLE",
            message=(
                "All ROS interfaces are ready."
                if all(state.values())
                else "One or more ROS interfaces are not ready."
            ),
            state=state,
        )

    def start_http_server(self) -> None:
        handler = self._build_http_handler()
        self._http_server = ThreadingHTTPServer(
            (self._bind_host, self._bind_port),
            handler,
        )
        self._http_server.daemon_threads = True
        self._http_thread = threading.Thread(
            target=self._http_server.serve_forever,
            name="sensoragent-robot-http",
            daemon=True,
        )
        self._http_thread.start()
        self.get_logger().info(
            f"Robot HTTP bridge listening on http://{self._bind_host}:{self._bind_port}"
        )

    def stop_http_server(self) -> None:
        if self._http_server is not None:
            self._http_server.shutdown()
            self._http_server.server_close()
            self._http_server = None
        if self._http_thread is not None:
            self._http_thread.join(timeout=2.0)
            self._http_thread = None

    def _build_http_handler(self):
        bridge = self

        class RobotHttpHandler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def _write_json(self, status: int, body: dict) -> None:
                payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def _read_json(self) -> dict:
                content_length = int(self.headers.get("Content-Length", "0"))
                if content_length > 1024 * 1024:
                    raise ValueError("request body is too large")
                raw = self.rfile.read(content_length) if content_length else b"{}"
                value = json.loads(raw.decode("utf-8"))
                if not isinstance(value, dict):
                    raise ValueError("request body must be a JSON object")
                return value

            def do_GET(self) -> None:
                if self.path == "/health":
                    self._write_json(
                        200,
                        _response(True, message="Robot bridge is running."),
                    )
                    return
                if self.path == "/state":
                    self._write_json(200, bridge.get_state())
                    return
                if self.path == "/ready":
                    self._write_json(200, bridge.get_ready())
                    return
                if self.path == "/scene/obstacles":
                    self._write_json(200, bridge.get_scene_obstacles())
                    return
                if self.path == "/gripper/state":
                    self._write_json(200, bridge.get_gripper_state())
                    return
                self._write_json(
                    404,
                    _response(False, error_code="NOT_FOUND", message="Unknown endpoint."),
                )

            def do_POST(self) -> None:
                try:
                    payload = self._read_json()
                    if self.path == "/move-joints":
                        result = bridge.move_joints(payload)
                    elif self.path == "/move-pose":
                        result = bridge.move_pose(payload)
                    elif self.path == "/move-linear":
                        result = bridge.move_linear(payload)
                    elif self.path == "/stop":
                        result = bridge.stop()
                    elif self.path == "/gripper/open":
                        result = bridge.command_gripper(payload, closing=False)
                    elif self.path == "/gripper/close":
                        result = bridge.command_gripper(payload, closing=True)
                    else:
                        self._write_json(
                            404,
                            _response(
                                False,
                                error_code="NOT_FOUND",
                                message="Unknown endpoint.",
                            ),
                        )
                        return
                    self._write_json(200, result)
                except (ValueError, json.JSONDecodeError) as exc:
                    self._write_json(
                        200,
                        _response(
                            False,
                            error_code="INVALID_REQUEST",
                            message=str(exc),
                        ),
                    )
                except Exception as exc:  # HTTP boundary
                    bridge.get_logger().error(f"Robot bridge request failed: {exc}")
                    self._write_json(
                        500,
                        _response(
                            False,
                            error_code="INTERNAL_ERROR",
                            message="Robot bridge request failed.",
                        ),
                    )

            def log_message(self, format_string: str, *args) -> None:
                bridge.get_logger().debug(format_string % args)

        return RobotHttpHandler


def main(args=None) -> None:
    rclpy.init(args=args)
    node = RobotBridgeNode()
    executor = MultiThreadedExecutor(num_threads=4)
    executor.add_node(node)
    node.start_http_server()
    try:
        executor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        node.stop_http_server()
        node.stop()
        executor.shutdown()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
