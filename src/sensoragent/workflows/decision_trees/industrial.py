"""Industrial DecisionTree workflows with classified recovery branches."""

from collections.abc import Mapping
from typing import Any

from sensoragent.schemas import (
  ConditionOperator,
  DecisionCondition,
  DecisionNode,
  DecisionNodeKind,
  DecisionTree,
)
from sensoragent.workflows.actionlists.industrial import (
  GRIPPER_CLOSE_OPENING,
  GRIPPER_PICK_FORCE,
  GRIPPER_OPEN_OPENING,
  GRIPPER_SPEED,
  PICK_APPROACH_DISTANCE,
  PICK_DESCENT_SPEED,
  PICK_LIFT_HEIGHT,
  PICK_POSITION_OFFSET,
  PICK_PREGRASP_DISTANCE,
  PICK_SPEED,
  PLACE_CLEARANCE,
  PLACE_SPEED,
  carry_joints,
  observe_joints,
  place_staging_joints,
  pick_staging_joints,
)


def build_industrial_recovery_pick_place_tree(
  joint_poses: Mapping[str, Any] | None = None,
) -> DecisionTree:
  """Build an industrial pick/place tree with typed failure recovery.

  The tree keeps the nominal flow explicit and routes all recoverable failures
  through recovery.classify_failure -> recovery.plan -> typed branches. Recovery
  actions are intentionally bounded: each recovery branch performs one local
  repair and then rejoins the main workflow or terminates.
  """
  observe = observe_joints(joint_poses)
  pick_staging = pick_staging_joints(joint_poses)
  carry = carry_joints(joint_poses)
  place_staging = place_staging_joints(joint_poses)
  start = "observe_before_detect" if observe is not None else "detect_object"
  after_plan_pick = "pick_staging_joints" if pick_staging is not None else "pick"
  after_verify_grasp = "carry_joints" if carry is not None else "resolve_place_target"
  after_place_retreat = "observe_after_place" if observe is not None else "verify_place"
  after_plan_place = "place_pre_approach_joints" if place_staging is not None else "place_move_place"
  after_place_lift = "place_retreat" if place_staging is not None else after_place_retreat
  recover_redetect_target = (
    "recover_observe_before_redetect" if observe is not None else "recover_redetect"
  )

  return DecisionTree(
    name="industrial.recovery_pick_place_tree",
    description="Industrial pick-place DecisionTree with classified local recovery branches.",
    inputs={
      "object_query": "string",
      "target": "string",
      "max_recovery_attempts": "integer",
    },
    tags=("industrial", "pick-place", "recovery", "decision-tree"),
    start=start,
    nodes=[
      *_move_joints_node("observe_before_detect", observe, PICK_SPEED, "detect_object"),
      DecisionNode(
        name="detect_object",
        kind=DecisionNodeKind.TOOL,
        target="vision.config_detect",
        input={"query": "{{ object_query }}"},
        save_as="object",
        max_retries=1,
        on_success="plan_pick",
        on_failure="classify_failure",
      ),
      DecisionNode(
        name="plan_pick",
        kind=DecisionNodeKind.TOOL,
        target="robot.plan_top_down_pick",
        input={
          "pose_3d": "{{ object.pose_3d }}",
          "position_offset": PICK_POSITION_OFFSET,
          "approach_distance": PICK_APPROACH_DISTANCE,
          "pregrasp_distance": PICK_PREGRASP_DISTANCE,
          "lift_height": PICK_LIFT_HEIGHT,
        },
        save_as="pick_plan",
        on_success=after_plan_pick,
        on_failure="classify_failure",
      ),
      *_move_joints_node("pick_staging_joints", pick_staging, PICK_SPEED, "pick"),
      DecisionNode(
        name="pick",
        kind=DecisionNodeKind.SKILL,
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
        on_success="verify_grasp",
        on_failure="classify_failure",
      ),
      DecisionNode(
        name="verify_grasp",
        kind=DecisionNodeKind.SKILL,
        target="robot.verify_grasp",
        input={},
        save_as="grasp_check",
        on_success=after_verify_grasp,
        on_failure="classify_failure",
      ),
      *_move_joints_node("carry_joints", carry, PICK_SPEED, "resolve_place_target"),
      DecisionNode(
        name="resolve_place_target",
        kind=DecisionNodeKind.TOOL,
        target="robot.resolve_place_target",
        input={"target": "{{ target }}"},
        save_as="place_target",
        on_success="plan_place",
        on_failure="classify_failure",
      ),
      DecisionNode(
        name="plan_place",
        kind=DecisionNodeKind.TOOL,
        target="robot.plan_place",
        input={
          "place_pose": "{{ place_target.place_pose }}",
          "clearance": PLACE_CLEARANCE,
        },
        save_as="place_plan",
        on_success=after_plan_place,
        on_failure="classify_failure",
      ),
      *_move_joints_node("place_pre_approach_joints", place_staging, PLACE_SPEED, "place_move_place"),
      DecisionNode(
        name="place_move_place",
        kind=DecisionNodeKind.TOOL,
        target="robot.move_pose",
        input={
          "pose": "{{ place_plan.plan.place }}",
          "speed": PLACE_SPEED,
          "wait": True,
        },
        on_success="place_open_gripper",
        on_failure="classify_failure",
      ),
      DecisionNode(
        name="place_open_gripper",
        kind=DecisionNodeKind.TOOL,
        target="gripper.open",
        input={
          "opening": GRIPPER_OPEN_OPENING,
          "speed": GRIPPER_SPEED,
        },
        on_success="place_lift_clearance",
        on_failure="classify_failure",
      ),
      DecisionNode(
        name="place_lift_clearance",
        kind=DecisionNodeKind.TOOL,
        target="robot.move_linear",
        input={
          "pose": "{{ place_plan.plan.retreat }}",
          "speed": PLACE_SPEED,
          "wait": True,
        },
        on_success=after_place_lift,
        on_failure="classify_failure",
      ),
      *_move_joints_node("place_retreat", place_staging, PLACE_SPEED, after_place_retreat),
      *_move_joints_node("observe_after_place", observe, PLACE_SPEED, "verify_place"),
      DecisionNode(
        name="verify_place",
        kind=DecisionNodeKind.SKILL,
        target="robot.verify_place",
        input={},
        save_as="place_check",
        on_success="verify_object_in_bin",
        on_failure="classify_failure",
      ),
      DecisionNode(
        name="verify_object_in_bin",
        kind=DecisionNodeKind.TOOL,
        target="vision.verify_object_in_bin",
        input={
          "target": "{{ target }}",
          # Until a post-place detector updates world state, use the commanded
          # release pose as the expected observation in deterministic tests.
          "pose_3d": "{{ place_target.place_pose.position }}",
        },
        save_as="bin_check",
        on_success="success",
        on_failure="classify_failure",
      ),
      DecisionNode(
        name="classify_failure",
        kind=DecisionNodeKind.TOOL,
        target="recovery.classify_failure",
        input={"evidence": "{{ last_failure }}"},
        save_as="classification",
        on_success="plan_recovery",
        on_failure="failure",
      ),
      DecisionNode(
        name="plan_recovery",
        kind=DecisionNodeKind.TOOL,
        target="recovery.plan",
        input={"classification": "{{ classification }}"},
        save_as="recovery",
        on_success="is_recovery_retryable",
        on_failure="failure",
      ),
      DecisionNode(
        name="is_recovery_retryable",
        kind=DecisionNodeKind.CONDITION,
        condition=DecisionCondition(
          path="recovery.retryable",
          operator=ConditionOperator.TRUTHY,
        ),
        on_success="is_object_not_found",
        on_failure="failure",
      ),
      _failure_type_check("is_object_not_found", "OBJECT_NOT_FOUND", recover_redetect_target, "is_low_confidence"),
      _failure_type_check("is_low_confidence", "LOW_CONFIDENCE", recover_redetect_target, "is_pose_invalid"),
      _failure_type_check("is_pose_invalid", "POSE_INVALID", recover_redetect_target, "is_pick_plan_failed"),
      _failure_type_check("is_pick_plan_failed", "PICK_PLAN_FAILED", "recover_pick", "is_pick_exec_failed"),
      _failure_type_check("is_pick_exec_failed", "PICK_EXEC_FAILED", "recover_pick", "is_grasp_empty"),
      _failure_type_check("is_grasp_empty", "GRASP_EMPTY", "recover_pick", "is_dropped_object"),
      _failure_type_check("is_dropped_object", "DROPPED_OBJECT", "recover_pick", "is_wrong_bin"),
      _failure_type_check("is_wrong_bin", "WRONG_BIN", "recover_pick", "is_place_plan_failed"),
      _failure_type_check("is_place_plan_failed", "PLACE_PLAN_FAILED", "recover_place", "is_place_exec_failed"),
      _failure_type_check("is_place_exec_failed", "PLACE_EXEC_FAILED", "recover_place", "is_release_failed"),
      _failure_type_check("is_release_failed", "RELEASE_FAILED", "recover_release", "is_gripper_failed"),
      _failure_type_check("is_gripper_failed", "GRIPPER_FAILED", "recover_release", "is_bridge_error"),
      _failure_type_check("is_bridge_error", "BRIDGE_ERROR", "recover_bridge", "is_robot_not_ready"),
      _failure_type_check("is_robot_not_ready", "ROBOT_NOT_READY", "recover_bridge", "failure"),
      *_move_joints_node(
        "recover_observe_before_redetect",
        observe,
        PICK_SPEED,
        "recover_redetect",
        on_failure="failure",
      ),
      DecisionNode(
        name="recover_redetect",
        kind=DecisionNodeKind.TOOL,
        target="vision.config_detect",
        input={"query": "{{ object_query }}"},
        save_as="object",
        max_retries=1,
        on_success="plan_pick",
        on_failure="failure",
      ),
      DecisionNode(
        name="recover_pick",
        kind=DecisionNodeKind.ACTIONLIST,
        target="industrial.pick_only_actionlist",
        input={"object_query": "{{ object_query }}"},
        save_as="recovered_pick",
        max_retries=1,
        on_success="resolve_place_target",
        on_failure="failure",
      ),
      DecisionNode(
        name="recover_place",
        kind=DecisionNodeKind.ACTIONLIST,
        target="industrial.place_only_actionlist",
        input={"target": "{{ target }}"},
        save_as="recovered_place",
        max_retries=1,
        on_success="verify_recovered_object_in_bin",
        on_failure="failure",
      ),
      DecisionNode(
        name="verify_recovered_object_in_bin",
        kind=DecisionNodeKind.TOOL,
        target="vision.verify_object_in_bin",
        input={
          "target": "{{ target }}",
          "pose_3d": "{{ recovered_place.place_target.place_pose.position }}",
        },
        save_as="bin_check",
        on_success="success",
        on_failure="failure",
      ),
      DecisionNode(
        name="recover_release",
        kind=DecisionNodeKind.TOOL,
        target="gripper.open",
        input={
          "opening": GRIPPER_OPEN_OPENING,
          "speed": 0.3,
        },
        max_retries=1,
        on_success="place_lift_clearance",
        on_failure="failure",
      ),
      DecisionNode(
        name="recover_bridge",
        kind=DecisionNodeKind.TOOL,
        target="robot.stop",
        input={},
        max_retries=1,
        on_success="recover_redetect",
        on_failure="failure",
      ),
      DecisionNode(name="success", kind=DecisionNodeKind.TERMINAL, terminal_success=True),
      DecisionNode(name="failure", kind=DecisionNodeKind.TERMINAL, terminal_success=False),
    ],
  )


def _move_joints_node(
  name: str,
  joints: list[float] | None,
  speed: float,
  on_success: str,
  *,
  on_failure: str = "classify_failure",
) -> list[DecisionNode]:
  if joints is None:
    return []
  return [
    DecisionNode(
      name=name,
      kind=DecisionNodeKind.TOOL,
      target="robot.move_joints",
      input={
        "joints": joints,
        "speed": speed,
        "wait": True,
      },
      on_success=on_success,
      on_failure=on_failure,
    )
  ]


def _failure_type_check(
  name: str,
  failure_type: str,
  on_success: str,
  on_failure: str,
) -> DecisionNode:
  return DecisionNode(
    name=name,
    kind=DecisionNodeKind.CONDITION,
    condition=DecisionCondition(
      path="classification.failure_type",
      operator=ConditionOperator.EQUALS,
      value=failure_type,
    ),
    on_success=on_success,
    on_failure=on_failure,
  )
