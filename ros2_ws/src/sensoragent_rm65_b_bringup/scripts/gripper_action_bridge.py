#!/usr/bin/env python3

import threading

import rclpy
from control_msgs.action import GripperCommand
from rclpy.action import ActionServer, CancelResponse, GoalResponse
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from sensor_msgs.msg import JointState
from std_msgs.msg import Float64MultiArray


class GripperActionBridge(Node):
    LEFT_JOINT = "robotiq_85_left_knuckle_joint"
    RIGHT_JOINT = "robotiq_85_right_knuckle_joint"

    def __init__(self):
        super().__init__("robotiq_gripper_action_bridge")

        self.declare_parameter("control_rate", 100.0)
        self.declare_parameter("kp", 1000.0)
        self.declare_parameter("kd", 10.0)
        self.declare_parameter("default_max_effort", 20.0)
        self.declare_parameter("joint_effort_limit", 40.0)
        self.declare_parameter("maximum_position", 0.0848)
        self.declare_parameter("goal_tolerance", 0.001)
        self.declare_parameter("stall_velocity_threshold", 0.001)
        self.declare_parameter("stall_timeout", 1.0)
        self.declare_parameter("joint_state_timeout", 5.0)

        self._kp = self.get_parameter("kp").value
        self._kd = self.get_parameter("kd").value
        self._default_max_effort = self.get_parameter(
            "default_max_effort"
        ).value
        self._joint_effort_limit = self.get_parameter(
            "joint_effort_limit"
        ).value
        self._maximum_position = self.get_parameter("maximum_position").value
        self._goal_tolerance = self.get_parameter("goal_tolerance").value
        self._stall_velocity_threshold = self.get_parameter(
            "stall_velocity_threshold"
        ).value
        self._stall_timeout = self.get_parameter("stall_timeout").value
        self._joint_state_timeout = self.get_parameter(
            "joint_state_timeout"
        ).value

        self._lock = threading.Lock()
        self._positions = {}
        self._velocities = {}
        self._active_goal = None
        self._hold_target = None
        self._hold_effort = self._default_max_effort

        self._command_publisher = self.create_publisher(
            Float64MultiArray,
            "/robotiq_gripper_effort_controller/commands",
            10,
        )
        self.create_subscription(
            JointState,
            "/joint_states",
            self._joint_state_callback,
            10,
        )

        callback_group = ReentrantCallbackGroup()
        self._action_server = ActionServer(
            self,
            GripperCommand,
            "/robotiq_gripper_controller/gripper_cmd",
            execute_callback=self._execute_callback,
            goal_callback=self._goal_callback,
            cancel_callback=self._cancel_callback,
            callback_group=callback_group,
        )

        control_rate = self.get_parameter("control_rate").value
        self.create_timer(1.0 / control_rate, self._control_callback)

    def _now_seconds(self):
        return self.get_clock().now().nanoseconds / 1e9

    def _joint_state_callback(self, message):
        with self._lock:
            for index, name in enumerate(message.name):
                if name not in (self.LEFT_JOINT, self.RIGHT_JOINT):
                    continue
                if index < len(message.position):
                    self._positions[name] = message.position[index]
                if index < len(message.velocity):
                    self._velocities[name] = message.velocity[index]

    def _goal_callback(self, goal_request):
        position = goal_request.command.position
        if position < 0.0 or position > self._maximum_position:
            self.get_logger().error(
                f"Rejecting gripper position {position}; expected 0.0 to "
                f"{self._maximum_position}"
            )
            return GoalResponse.REJECT
        return GoalResponse.ACCEPT

    def _cancel_callback(self, goal_handle):
        with self._lock:
            state = self._active_goal
            if state is not None and state["goal_handle"] == goal_handle:
                state["canceled"] = True
                state["event"].set()
                self._hold_current_position()
        return CancelResponse.ACCEPT

    def _execute_callback(self, goal_handle):
        command = goal_handle.request.command
        requested_effort = abs(command.max_effort)
        if requested_effort == 0.0:
            requested_effort = self._default_max_effort
        max_effort = min(requested_effort, self._joint_effort_limit)

        now = self._now_seconds()
        state = {
            "goal_handle": goal_handle,
            "target": (command.position / 2.0, command.position / 2.0),
            "max_effort": max_effort,
            "last_motion": [now, now],
            "started": now,
            "event": threading.Event(),
            "result": GripperCommand.Result(),
            "canceled": False,
            "preempted": False,
        }

        with self._lock:
            previous = self._active_goal
            if previous is not None and not previous["event"].is_set():
                previous["preempted"] = True
                previous["goal_handle"].abort()
                previous["event"].set()
            self._active_goal = state
            self._hold_target = state["target"]
            self._hold_effort = max_effort

        state["event"].wait()

        with self._lock:
            if self._active_goal is state:
                self._active_goal = None

        if state["canceled"]:
            goal_handle.canceled()
        elif not state["preempted"]:
            goal_handle.succeed()

        return state["result"]

    def _hold_current_position(self):
        if self.LEFT_JOINT in self._positions and self.RIGHT_JOINT in self._positions:
            self._hold_target = (
                self._positions[self.LEFT_JOINT],
                self._positions[self.RIGHT_JOINT],
            )
            self._hold_effort = self._default_max_effort

    @staticmethod
    def _clamp(value, limit):
        return max(-limit, min(limit, value))

    def stop(self):
        with self._lock:
            state = self._active_goal
            if state is not None and not state["event"].is_set():
                state["preempted"] = True
                state["goal_handle"].abort()
                state["event"].set()
        message = Float64MultiArray()
        message.data = [0.0, 0.0]
        self._command_publisher.publish(message)

    def _control_callback(self):
        with self._lock:
            if (
                self.LEFT_JOINT not in self._positions
                or self.RIGHT_JOINT not in self._positions
            ):
                self._check_joint_state_timeout()
                return

            positions = (
                self._positions[self.LEFT_JOINT],
                self._positions[self.RIGHT_JOINT],
            )
            velocities = (
                self._velocities.get(self.LEFT_JOINT, 0.0),
                self._velocities.get(self.RIGHT_JOINT, 0.0),
            )

            state = self._active_goal
            target = state["target"] if state is not None else self._hold_target
            if target is None:
                efforts = (0.0, 0.0)
            else:
                max_effort = (
                    state["max_effort"]
                    if state is not None
                    else self._hold_effort
                )
                efforts = tuple(
                    self._clamp(
                        self._kp * (target[index] - positions[index])
                        - self._kd * velocities[index],
                        max_effort,
                    )
                    for index in range(2)
                )

            message = Float64MultiArray()
            message.data = list(efforts)
            self._command_publisher.publish(message)

            if state is not None:
                self._update_goal(state, positions, velocities, efforts)

    def _check_joint_state_timeout(self):
        state = self._active_goal
        if state is None:
            return
        if self._now_seconds() - state["started"] <= self._joint_state_timeout:
            return

        self.get_logger().error(
            "Gripper joint states were not received before the timeout"
        )
        state["goal_handle"].abort()
        state["preempted"] = True
        state["event"].set()

    def _update_goal(self, state, positions, velocities, efforts):
        now = self._now_seconds()
        reached = []
        stalled = []

        for index in range(2):
            error = state["target"][index] - positions[index]
            joint_reached = abs(error) < self._goal_tolerance
            if abs(velocities[index]) > self._stall_velocity_threshold:
                state["last_motion"][index] = now
            joint_stalled = (
                not joint_reached
                and now - state["last_motion"][index] > self._stall_timeout
            )
            reached.append(joint_reached)
            stalled.append(joint_stalled)

        feedback = GripperCommand.Feedback()
        feedback.position = positions[0] + positions[1]
        feedback.effort = max(abs(efforts[0]), abs(efforts[1]))
        feedback.reached_goal = all(reached)
        feedback.stalled = any(stalled)
        state["goal_handle"].publish_feedback(feedback)

        if not all(reached[index] or stalled[index] for index in range(2)):
            return

        result = state["result"]
        result.position = feedback.position
        result.effort = feedback.effort
        result.reached_goal = feedback.reached_goal
        result.stalled = feedback.stalled
        state["event"].set()


def main(args=None):
    rclpy.init(args=args)
    node = GripperActionBridge()
    executor = MultiThreadedExecutor(num_threads=2)
    executor.add_node(node)
    try:
        executor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        node.stop()
        executor.shutdown()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
