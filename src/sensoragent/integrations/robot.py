"""Backend-neutral robot control integration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

import requests

from sensoragent.schemas.robot import RobotPose


@dataclass(frozen=True)
class RobotCommandResult:
  """Normalized result returned by robot backends."""

  success: bool
  error_code: str = "OK"
  message: str = "OK"
  state: dict = field(default_factory=dict)


class RobotControlClient(Protocol):
  """Control surface implemented by simulation and hardware adapters."""

  def get_state(self) -> RobotCommandResult:
    """Return current arm and gripper state."""

  def move_joints(
    self,
    joints: list[float],
    *,
    speed: float,
    wait: bool,
  ) -> RobotCommandResult:
    """Move to an absolute joint target in radians."""

  def move_pose(
    self,
    pose: RobotPose,
    *,
    speed: float,
    linear: bool,
    wait: bool,
    avoid_collisions: bool = True,
  ) -> RobotCommandResult:
    """Move to an absolute Cartesian target."""

  def stop(self) -> RobotCommandResult:
    """Stop active arm and gripper motion."""

  def open_gripper(self, *, opening: float, speed: float) -> RobotCommandResult:
    """Open the gripper to the requested opening in metres."""

  def close_gripper(
    self,
    *,
    opening: float,
    force: float,
    speed: float,
  ) -> RobotCommandResult:
    """Close the gripper to the requested opening in metres."""

  def get_gripper_state(self) -> RobotCommandResult:
    """Return current gripper state."""


class HttpRobotControlClient:
  """Robot backend that calls the separate ROS 2 simulation bridge."""

  def __init__(
    self,
    endpoint: str = "http://127.0.0.1:8765",
    *,
    timeout_seconds: float = 120.0,
    session: requests.Session | None = None,
  ) -> None:
    self._endpoint = endpoint.rstrip("/")
    self._timeout_seconds = timeout_seconds
    self._session = session or requests.Session()

  def _request(
    self,
    method: str,
    path: str,
    payload: dict | None = None,
    *,
    timeout_seconds: float,
    stop_on_timeout: bool = False,
  ) -> RobotCommandResult:
    try:
      response = self._session.request(
        method,
        f"{self._endpoint}{path}",
        json=payload,
        timeout=min(self._timeout_seconds, timeout_seconds),
      )
      response.raise_for_status()
      body = response.json()
    except requests.Timeout as exc:
      if stop_on_timeout:
        self._best_effort_stop()
      return RobotCommandResult(
        success=False,
        error_code="ROBOT_BRIDGE_TIMEOUT",
        message=str(exc),
      )
    except requests.RequestException as exc:
      return RobotCommandResult(
        success=False,
        error_code="ROBOT_BRIDGE_UNAVAILABLE",
        message=str(exc),
      )
    except ValueError as exc:
      return RobotCommandResult(
        success=False,
        error_code="INVALID_BRIDGE_RESPONSE",
        message=str(exc),
      )

    if not isinstance(body, dict) or not isinstance(body.get("success"), bool):
      return RobotCommandResult(
        success=False,
        error_code="INVALID_BRIDGE_RESPONSE",
        message="Robot bridge response must contain a boolean success field.",
      )
    state = body.get("state", {})
    if not isinstance(state, dict):
      return RobotCommandResult(
        success=False,
        error_code="INVALID_BRIDGE_RESPONSE",
        message="Robot bridge state must be an object.",
      )
    return RobotCommandResult(
      success=body["success"],
      error_code=str(body.get("error_code", "OK")),
      message=str(body.get("message", "OK")),
      state=state,
    )

  def _best_effort_stop(self) -> None:
    try:
      self._session.request(
        "POST",
        f"{self._endpoint}/stop",
        json={},
        timeout=min(self._timeout_seconds, 5.0),
      )
    except requests.RequestException:
      pass

  def get_state(self) -> RobotCommandResult:
    return self._request("GET", "/state", timeout_seconds=4.0)

  def move_joints(
    self,
    joints: list[float],
    *,
    speed: float,
    wait: bool,
  ) -> RobotCommandResult:
    return self._request(
      "POST",
      "/move-joints",
      {"joints": joints, "speed": speed, "wait": wait},
      timeout_seconds=110.0,
      stop_on_timeout=True,
    )

  def move_pose(
    self,
    pose: RobotPose,
    *,
    speed: float,
    linear: bool,
    wait: bool,
    avoid_collisions: bool = True,
  ) -> RobotCommandResult:
    payload = {"pose": pose.to_dict(), "speed": speed, "wait": wait}
    if linear:
      payload["avoid_collisions"] = avoid_collisions
    return self._request(
      "POST",
      "/move-linear" if linear else "/move-pose",
      payload,
      timeout_seconds=110.0,
      stop_on_timeout=True,
    )

  def stop(self) -> RobotCommandResult:
    return self._request("POST", "/stop", {}, timeout_seconds=8.0)

  def open_gripper(self, *, opening: float, speed: float) -> RobotCommandResult:
    return self._request(
      "POST",
      "/gripper/open",
      {"opening": opening, "speed": speed},
      timeout_seconds=20.0,
      stop_on_timeout=True,
    )

  def close_gripper(
    self,
    *,
    opening: float,
    force: float,
    speed: float,
  ) -> RobotCommandResult:
    return self._request(
      "POST",
      "/gripper/close",
      {"opening": opening, "force": force, "speed": speed},
      timeout_seconds=20.0,
      stop_on_timeout=True,
    )

  def get_gripper_state(self) -> RobotCommandResult:
    return self._request("GET", "/gripper/state", timeout_seconds=4.0)


class FakeRobotControlClient:
  """Stateful backend for tests and Agent integration development."""

  def __init__(self, *, dof: int = 6, maximum_opening: float = 0.0848) -> None:
    self._dof = dof
    self._maximum_opening = maximum_opening
    self._joints = [0.0] * dof
    self._pose = RobotPose(
      position=(0.0, 0.0, 0.0),
      orientation=(0.0, 0.0, 0.0, 1.0),
    )
    self._arm_status = "idle"
    self._gripper_opening = maximum_opening
    self._gripper_status = "open"
    self._grasped = False

  def _state(self) -> dict:
    return {
      "arm": {
        "status": self._arm_status,
        "joints": list(self._joints),
        "pose": self._pose.to_dict(),
      },
      "gripper": {
        "status": self._gripper_status,
        "opening": self._gripper_opening,
        "grasped": self._grasped,
      },
    }

  def get_state(self) -> RobotCommandResult:
    return RobotCommandResult(success=True, state=self._state())

  def move_joints(
    self,
    joints: list[float],
    *,
    speed: float,
    wait: bool,
  ) -> RobotCommandResult:
    del speed, wait
    if len(joints) != self._dof:
      return RobotCommandResult(
        success=False,
        error_code="INVALID_JOINT_COUNT",
        message=f"Expected {self._dof} joints, received {len(joints)}.",
      )
    self._joints = list(joints)
    self._arm_status = "idle"
    return RobotCommandResult(success=True, state=self._state())

  def move_pose(
    self,
    pose: RobotPose,
    *,
    speed: float,
    linear: bool,
    wait: bool,
    avoid_collisions: bool = True,
  ) -> RobotCommandResult:
    del speed, linear, wait, avoid_collisions
    self._pose = pose
    self._arm_status = "idle"
    return RobotCommandResult(success=True, state=self._state())

  def stop(self) -> RobotCommandResult:
    self._arm_status = "stopped"
    return RobotCommandResult(success=True, message="Motion stopped.", state=self._state())

  def open_gripper(self, *, opening: float, speed: float) -> RobotCommandResult:
    del speed
    if opening < 0.0 or opening > self._maximum_opening:
      return RobotCommandResult(
        success=False,
        error_code="INVALID_GRIPPER_OPENING",
        message=f"Opening must be between 0 and {self._maximum_opening}.",
      )
    self._gripper_opening = opening
    self._gripper_status = "open"
    self._grasped = False
    return RobotCommandResult(success=True, state=self._state())

  def close_gripper(
    self,
    *,
    opening: float,
    force: float,
    speed: float,
  ) -> RobotCommandResult:
    del force, speed
    if opening < 0.0 or opening > self._maximum_opening:
      return RobotCommandResult(
        success=False,
        error_code="INVALID_GRIPPER_OPENING",
        message=f"Opening must be between 0 and {self._maximum_opening}.",
      )
    self._gripper_opening = opening
    self._gripper_status = "closed"
    self._grasped = opening > 0.0
    return RobotCommandResult(success=True, state=self._state())

  def get_gripper_state(self) -> RobotCommandResult:
    return RobotCommandResult(success=True, state=self._state()["gripper"])
