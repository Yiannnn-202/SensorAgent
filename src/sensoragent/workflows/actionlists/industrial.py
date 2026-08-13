"""Industrial pick-and-place ActionList definitions."""

from collections.abc import Mapping
from typing import Any

from sensoragent.schemas import ActionList, ActionStep, ActionStepKind
from sensoragent.tools.robot.joint_poses import (
  DEFAULT_PLACE_STAGING_JOINTS,
  optional_configured_joint_pose,
)


PICK_APPROACH_DISTANCE = 0.10
PICK_PREGRASP_DISTANCE = 0.04
PICK_LIFT_HEIGHT = 0.12
PICK_POSITION_OFFSET = [0.0, 0.0, 0.02]
PICK_SPEED = 1.2
PICK_DESCENT_SPEED = 1.2
GRIPPER_CLOSE_OPENING = 0.032
GRIPPER_PICK_FORCE = 1.0

PLACE_CLEARANCE = 0.08
PLACE_SPEED = 1.2
GRIPPER_OPEN_OPENING = 0.0848
GRIPPER_SPEED = 0.5

# Backward-compatible alias for tests and scripts that import the old constant.
PLACE_PRE_APPROACH_JOINTS = DEFAULT_PLACE_STAGING_JOINTS


def place_staging_joints(joint_poses: Mapping[str, Any] | None = None) -> list[float] | None:
  return optional_configured_joint_pose(joint_poses, "place_staging_joints")


def observe_joints(joint_poses: Mapping[str, Any] | None = None) -> list[float] | None:
  return optional_configured_joint_pose(joint_poses, "observe_joints")


def pick_staging_joints(joint_poses: Mapping[str, Any] | None = None) -> list[float] | None:
  return optional_configured_joint_pose(joint_poses, "pick_staging_joints")


def carry_joints(joint_poses: Mapping[str, Any] | None = None) -> list[float] | None:
  return optional_configured_joint_pose(joint_poses, "carry_joints")


def optional_move_joints_step(
  name: str,
  joints: list[float] | None,
  speed: float,
) -> list[ActionStep]:
  if joints is None:
    return []
  return [
    ActionStep(
      name=name,
      kind=ActionStepKind.TOOL,
      target="robot.move_joints",
      input={
        "joints": joints,
        "speed": speed,
        "wait": True,
      },
    )
  ]


def build_industrial_pick_place_actionlist(
  joint_poses: Mapping[str, Any] | None = None,
) -> ActionList:
  """Build the industrial pick → verify_grasp → place → verify_place workflow.

  The place phase is expanded inline rather than delegated to robot.place so
  we can (a) use a joint-space staging move to position the arm gripper-down
  above the bin column before the Cartesian descent, (b) skip an OMPL approach
  waypoint since MoveIt refuses to plan Cartesian OMPL moves while the gripper
  is closed on a payload, (c) tolerate the Robotiq bridge reporting a stall on
  gripper.open once the object is already released, and (d) retreat via a
  joint-space move because move_pose is similarly rejected right after release.
  """
  observe = observe_joints(joint_poses)
  pick_staging = pick_staging_joints(joint_poses)
  carry = carry_joints(joint_poses)
  place_staging = place_staging_joints(joint_poses)

  return ActionList(
    name="industrial.pick_place_actionlist",
    description="Industrial pick-and-place with grasp and place verification.",
    inputs={"object_query": "string", "target": "string"},
    tags=("industrial", "pick-place", "verify"),
    steps=[
      *optional_move_joints_step("observe_before_detect", observe, PICK_SPEED),
      ActionStep(
        name="detect_object",
        kind=ActionStepKind.TOOL,
        target="vision.config_detect",
        input={"query": "{{ object_query }}"},
        save_as="object",
      ),
      ActionStep(
        name="plan_pick",
        kind=ActionStepKind.TOOL,
        target="robot.plan_top_down_pick",
        input={
          "pose_3d": "{{ object.pose_3d }}",
          "position_offset": PICK_POSITION_OFFSET,
          "approach_distance": PICK_APPROACH_DISTANCE,
          "pregrasp_distance": PICK_PREGRASP_DISTANCE,
          "lift_height": PICK_LIFT_HEIGHT,
        },
        save_as="pick_plan",
      ),
      *optional_move_joints_step("pick_staging_joints", pick_staging, PICK_SPEED),
      ActionStep(
        name="pick",
        kind=ActionStepKind.SKILL,
        target="robot.pick",
        input={
          "plan": "{{ pick_plan.plan }}",
          "object_id": "{{ object.object_id }}",
          "speed": PICK_SPEED,
          "descent_speed": PICK_DESCENT_SPEED,
          "close_opening": GRIPPER_CLOSE_OPENING,
          "gripper_force": GRIPPER_PICK_FORCE,
        },
        save_as="pick_result",
      ),
      ActionStep(
        name="verify_grasp",
        kind=ActionStepKind.SKILL,
        target="robot.verify_grasp",
        input={},
        save_as="grasp_check",
      ),
      *optional_move_joints_step("carry_joints", carry, PICK_SPEED),
      ActionStep(
        name="resolve_place_target",
        kind=ActionStepKind.TOOL,
        target="robot.resolve_place_target",
        input={"target": "{{ target }}"},
        save_as="place_target",
      ),
      ActionStep(
        name="plan_place",
        kind=ActionStepKind.TOOL,
        target="robot.plan_place",
        input={
          "place_pose": "{{ place_target.place_pose }}",
          "clearance": PLACE_CLEARANCE,
        },
        save_as="place_plan",
      ),
      *optional_move_joints_step("place_pre_approach_joints", place_staging, PLACE_SPEED),
      ActionStep(
        name="place_move_place",
        kind=ActionStepKind.TOOL,
        target="robot.move_pose",
        input={
          "pose": "{{ place_plan.plan.place }}",
          "speed": PLACE_SPEED,
          "wait": True,
        },
      ),
      ActionStep(
        name="place_open_gripper",
        kind=ActionStepKind.TOOL,
        target="gripper.open",
        input={
          "opening": GRIPPER_OPEN_OPENING,
          "speed": GRIPPER_SPEED,
        },
        stop_on_failure=False,
      ),
      ActionStep(
        name="place_lift_clearance",
        kind=ActionStepKind.TOOL,
        target="robot.move_linear",
        input={
          "pose": "{{ place_plan.plan.retreat }}",
          "speed": PLACE_SPEED,
          "wait": True,
        },
      ),
      *optional_move_joints_step("place_retreat", place_staging, PLACE_SPEED),
      *optional_move_joints_step("observe_after_place", observe, PLACE_SPEED),
      ActionStep(
        name="verify_place",
        kind=ActionStepKind.SKILL,
        target="robot.verify_place",
        input={},
        save_as="place_check",
      ),
    ],
  )


def build_industrial_pick_only_actionlist(
  joint_poses: Mapping[str, Any] | None = None,
) -> ActionList:
  """Pick an object and hold it. No destination is required; the arm ends at the
  lift pose with the gripper closed on the object."""
  observe = observe_joints(joint_poses)
  pick_staging = pick_staging_joints(joint_poses)
  carry = carry_joints(joint_poses)

  return ActionList(
    name="industrial.pick_only_actionlist",
    description="Industrial pick with grasp verification; arm ends holding the object.",
    inputs={
      "object_query": "string",
      "position_offset": "array",
      "approach_distance": "number",
      "pregrasp_distance": "number",
      "lift_height": "number",
      "close_opening": "number",
      "gripper_force": "number",
    },
    input_defaults={
      "position_offset": PICK_POSITION_OFFSET,
      "approach_distance": PICK_APPROACH_DISTANCE,
      "pregrasp_distance": PICK_PREGRASP_DISTANCE,
      "lift_height": PICK_LIFT_HEIGHT,
      "close_opening": GRIPPER_CLOSE_OPENING,
      "gripper_force": GRIPPER_PICK_FORCE,
    },
    tags=("industrial", "pick", "verify"),
    steps=[
      *optional_move_joints_step("observe_before_detect", observe, PICK_SPEED),
      ActionStep(
        name="detect_object",
        kind=ActionStepKind.TOOL,
        target="vision.config_detect",
        input={"query": "{{ object_query }}"},
        save_as="object",
      ),
      ActionStep(
        name="plan_pick",
        kind=ActionStepKind.TOOL,
        target="robot.plan_top_down_pick",
        input={
          "pose_3d": "{{ object.pose_3d }}",
          "position_offset": "{{ position_offset }}",
          "approach_distance": "{{ approach_distance }}",
          "pregrasp_distance": "{{ pregrasp_distance }}",
          "lift_height": "{{ lift_height }}",
        },
        save_as="pick_plan",
      ),
      *optional_move_joints_step("pick_staging_joints", pick_staging, PICK_SPEED),
      ActionStep(
        name="pick",
        kind=ActionStepKind.SKILL,
        target="robot.pick",
        input={
          "plan": "{{ pick_plan.plan }}",
          "object_id": "{{ object.object_id }}",
          "speed": PICK_SPEED,
          "descent_speed": PICK_DESCENT_SPEED,
          "close_opening": "{{ close_opening }}",
          "gripper_force": "{{ gripper_force }}",
        },
        save_as="pick_result",
      ),
      ActionStep(
        name="verify_grasp",
        kind=ActionStepKind.SKILL,
        target="robot.verify_grasp",
        input={},
        save_as="grasp_check",
      ),
      *optional_move_joints_step("carry_joints", carry, PICK_SPEED),
    ],
  )


def build_industrial_place_only_actionlist(
  joint_poses: Mapping[str, Any] | None = None,
) -> ActionList:
  """Place a held object into a named destination. Assumes the arm is already
  gripping the payload (verify_grasp is not run at entry — the caller is
  responsible for ensuring the object is held)."""
  observe = observe_joints(joint_poses)
  carry = carry_joints(joint_poses)
  place_staging = place_staging_joints(joint_poses)

  return ActionList(
    name="industrial.place_only_actionlist",
    description="Industrial place: staging joints → descent → release → retreat, with verify_place.",
    inputs={
      "target": "string",
      "place_offset": "array",
      "clearance": "number",
      "open_opening": "number",
      "gripper_speed": "number",
    },
    input_defaults={
      "place_offset": [0.0, 0.0, 0.0],
      "clearance": PLACE_CLEARANCE,
      "open_opening": GRIPPER_OPEN_OPENING,
      "gripper_speed": GRIPPER_SPEED,
    },
    tags=("industrial", "place", "verify"),
    steps=[
      *optional_move_joints_step("carry_joints", carry, PLACE_SPEED),
      ActionStep(
        name="resolve_place_target",
        kind=ActionStepKind.TOOL,
        target="robot.resolve_place_target",
        input={"target": "{{ target }}", "place_offset": "{{ place_offset }}"},
        save_as="place_target",
      ),
      ActionStep(
        name="plan_place",
        kind=ActionStepKind.TOOL,
        target="robot.plan_place",
        input={
          "place_pose": "{{ place_target.place_pose }}",
          "clearance": "{{ clearance }}",
        },
        save_as="place_plan",
      ),
      *optional_move_joints_step("place_pre_approach_joints", place_staging, PLACE_SPEED),
      ActionStep(
        name="place_move_place",
        kind=ActionStepKind.TOOL,
        target="robot.move_pose",
        input={
          "pose": "{{ place_plan.plan.place }}",
          "speed": PLACE_SPEED,
          "wait": True,
        },
      ),
      ActionStep(
        name="place_open_gripper",
        kind=ActionStepKind.TOOL,
        target="gripper.open",
        input={
          "opening": "{{ open_opening }}",
          "speed": "{{ gripper_speed }}",
        },
        stop_on_failure=False,
      ),
      ActionStep(
        name="place_lift_clearance",
        kind=ActionStepKind.TOOL,
        target="robot.move_linear",
        input={
          "pose": "{{ place_plan.plan.retreat }}",
          "speed": PLACE_SPEED,
          "wait": True,
        },
      ),
      *optional_move_joints_step("place_retreat", place_staging, PLACE_SPEED),
      *optional_move_joints_step("observe_after_place", observe, PLACE_SPEED),
      ActionStep(
        name="verify_place",
        kind=ActionStepKind.SKILL,
        target="robot.verify_place",
        input={},
        save_as="place_check",
      ),
    ],
  )
