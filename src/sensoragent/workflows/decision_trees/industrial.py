"""Industrial DecisionTree workflows with classified recovery branches."""

from sensoragent.schemas import (
  ConditionOperator,
  DecisionCondition,
  DecisionNode,
  DecisionNodeKind,
  DecisionTree,
)
from sensoragent.workflows.actionlists.industrial import (
  GRIPPER_OPEN_OPENING,
  GRIPPER_SPEED,
  PICK_APPROACH_DISTANCE,
  PICK_DESCENT_SPEED,
  PICK_LIFT_HEIGHT,
  PICK_POSITION_OFFSET,
  PICK_PREGRASP_DISTANCE,
  PICK_SPEED,
  PLACE_CLEARANCE,
  PLACE_PRE_APPROACH_JOINTS,
  PLACE_SPEED,
)


def build_industrial_recovery_pick_place_tree(
  *,
  detect_tool: str = "vision.config_detect",
  capture_tool: str | None = None,
  live_verify: bool = False,
  spatial_constraint_input: bool = False,
) -> DecisionTree:
  """Build an industrial pick/place tree with typed failure recovery.

  The tree keeps the nominal flow explicit and routes all recoverable failures
  through recovery.classify_failure -> recovery.plan -> typed branches. Recovery
  actions are intentionally bounded: each recovery branch performs one local
  repair and then rejoins the main workflow or terminates.

  Args:
    detect_tool: Tool used for object detection. Defaults to the deterministic
      config catalog; pass ``vision.open_vocab_detect`` for real perception.
    capture_tool: When set (e.g. ``vision.capture_frame``), a fresh RGB-D frame
      is captured before every detection so the detector sees current world
      state instead of a caller-supplied frame.
    live_verify: When True, post-place verification re-detects the object in a
      newly captured frame instead of echoing the commanded release pose.
    spatial_constraint_input: When True, detections forward the request's
      ``spatial_constraint`` input to the detector.
  """

  detect_nodes = _detect_sequence(
    detect_tool=detect_tool,
    capture_tool=capture_tool,
    spatial_constraint_input=spatial_constraint_input,
    capture_node="capture_initial",
    detect_node="detect_object",
    frame_key="initial_frame",
    save_as="object",
    out_dir="logs/vision/recovery/initial",
    max_retries=1,
    on_success="plan_pick",
    on_failure="classify_failure",
  )
  redetect_nodes = _detect_sequence(
    detect_tool=detect_tool,
    capture_tool=capture_tool,
    spatial_constraint_input=spatial_constraint_input,
    capture_node="capture_redetect",
    detect_node="recover_redetect",
    frame_key="redetect_frame",
    save_as="object",
    out_dir="logs/vision/recovery/redetect",
    max_retries=1,
    on_success="plan_pick",
    on_failure="failure",
  )
  verify_nodes = _verify_in_bin_sequence(
    detect_tool=detect_tool,
    capture_tool=capture_tool,
    live_verify=live_verify,
    spatial_constraint_input=spatial_constraint_input,
    capture_node="recapture_post_place",
    redetect_node="redetect_post_place",
    verify_node="verify_object_in_bin",
    frame_key="post_place_frame",
    observed_key="observed_object",
    out_dir="logs/vision/recovery/post_place",
    commanded_pose="{{ place_target.place_pose.position }}",
    save_as="bin_check",
    on_success="success",
    on_failure="classify_failure",
  )
  recovered_verify_nodes = _verify_in_bin_sequence(
    detect_tool=detect_tool,
    capture_tool=capture_tool,
    live_verify=live_verify,
    spatial_constraint_input=spatial_constraint_input,
    capture_node="recapture_recovered_place",
    redetect_node="redetect_recovered_place",
    verify_node="verify_recovered_object_in_bin",
    frame_key="recovered_place_frame",
    observed_key="observed_recovered_object",
    out_dir="logs/vision/recovery/recovered_post_place",
    commanded_pose="{{ recovered_place.place_target.place_pose.position }}",
    save_as="bin_check",
    on_success="success",
    on_failure="failure",
  )

  inputs = {
    "object_query": "string",
    "target": "string",
    "max_recovery_attempts": "integer",
  }
  if spatial_constraint_input:
    inputs["spatial_constraint"] = "object"

  return DecisionTree(
    name="industrial.recovery_pick_place_tree",
    description="Industrial pick-place DecisionTree with classified local recovery branches.",
    inputs=inputs,
    tags=("industrial", "pick-place", "recovery", "decision-tree"),
    start=detect_nodes[0].name,
    nodes=[
      *detect_nodes,
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
        on_success="pick",
        on_failure="classify_failure",
      ),
      DecisionNode(
        name="pick",
        kind=DecisionNodeKind.SKILL,
        target="robot.pick",
        input={
          "plan": "{{ pick_plan.plan }}",
          "object_id": "{{ object.object_id }}",
          "speed": PICK_SPEED,
          "descent_speed": PICK_DESCENT_SPEED,
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
        on_success="resolve_place_target",
        on_failure="classify_failure",
      ),
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
        on_success="place_pre_approach_joints",
        on_failure="classify_failure",
      ),
      DecisionNode(
        name="place_pre_approach_joints",
        kind=DecisionNodeKind.TOOL,
        target="robot.move_joints",
        input={
          "joints": PLACE_PRE_APPROACH_JOINTS,
          "speed": PLACE_SPEED,
          "wait": True,
        },
        on_success="place_move_place",
        on_failure="classify_failure",
      ),
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
        on_success="place_retreat",
        on_failure="classify_failure",
      ),
      DecisionNode(
        name="place_retreat",
        kind=DecisionNodeKind.TOOL,
        target="robot.move_joints",
        input={
          "joints": PLACE_PRE_APPROACH_JOINTS,
          "speed": PLACE_SPEED,
          "wait": True,
        },
        on_success="verify_place",
        on_failure="classify_failure",
      ),
      DecisionNode(
        name="verify_place",
        kind=DecisionNodeKind.SKILL,
        target="robot.verify_place",
        input={},
        save_as="place_check",
        on_success=verify_nodes[0].name,
        on_failure="classify_failure",
      ),
      *verify_nodes,
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
      _failure_type_check("is_object_not_found", "OBJECT_NOT_FOUND", redetect_nodes[0].name, "is_low_confidence"),
      _failure_type_check("is_low_confidence", "LOW_CONFIDENCE", redetect_nodes[0].name, "is_pose_invalid"),
      _failure_type_check("is_pose_invalid", "POSE_INVALID", redetect_nodes[0].name, "is_pick_plan_failed"),
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
      *redetect_nodes,
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
        on_success=recovered_verify_nodes[0].name,
        on_failure="failure",
      ),
      *recovered_verify_nodes,
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
        on_success=redetect_nodes[0].name,
        on_failure="failure",
      ),
      DecisionNode(name="success", kind=DecisionNodeKind.TERMINAL, terminal_success=True),
      DecisionNode(name="failure", kind=DecisionNodeKind.TERMINAL, terminal_success=False),
    ],
  )


def _detect_sequence(
  *,
  detect_tool: str,
  capture_tool: str | None,
  spatial_constraint_input: bool,
  capture_node: str,
  detect_node: str,
  frame_key: str,
  save_as: str,
  out_dir: str,
  max_retries: int,
  on_success: str,
  on_failure: str,
) -> list[DecisionNode]:
  """Build [capture?, detect] for one detection point in the tree."""

  nodes: list[DecisionNode] = []
  if capture_tool:
    nodes.append(
      DecisionNode(
        name=capture_node,
        kind=DecisionNodeKind.TOOL,
        target=capture_tool,
        input={"out_dir": out_dir},
        save_as=frame_key,
        max_retries=max_retries,
        on_success=detect_node,
        on_failure=on_failure,
      )
    )
  nodes.append(
    DecisionNode(
      name=detect_node,
      kind=DecisionNodeKind.TOOL,
      target=detect_tool,
      input=_detect_input(
        detect_tool=detect_tool,
        frame_key=frame_key if capture_tool else None,
        spatial_constraint_input=spatial_constraint_input,
      ),
      save_as=save_as,
      max_retries=max_retries,
      on_success=on_success,
      on_failure=on_failure,
    )
  )
  return nodes


def _detect_input(
  *,
  detect_tool: str,
  frame_key: str | None,
  spatial_constraint_input: bool,
) -> dict:
  detect_input: dict = {"query": "{{ object_query }}"}
  if frame_key:
    detect_input.update(
      {
        "image_path": f"{{{{ {frame_key}.image_path }}}}",
        "depth_path": f"{{{{ {frame_key}.depth_path }}}}",
        "camera_info_path": f"{{{{ {frame_key}.camera_info_path }}}}",
        "T_base_camera": f"{{{{ {frame_key}.T_base_camera }}}}",
        "T_world_camera": f"{{{{ {frame_key}.T_world_camera }}}}",
      }
    )
  if spatial_constraint_input:
    detect_input["spatial_constraint"] = "{{ spatial_constraint }}"
  return detect_input


def _verify_in_bin_sequence(
  *,
  detect_tool: str,
  capture_tool: str | None,
  live_verify: bool,
  spatial_constraint_input: bool,
  capture_node: str,
  redetect_node: str,
  verify_node: str,
  frame_key: str,
  observed_key: str,
  out_dir: str,
  commanded_pose: str,
  save_as: str,
  on_success: str,
  on_failure: str,
) -> list[DecisionNode]:
  """Build post-place verification nodes.

  Without ``live_verify`` the verification echoes the commanded release pose,
  which keeps deterministic runs green but cannot observe a wrong bin. With
  ``live_verify`` a fresh frame is captured and the object re-detected, so the
  verified position is a real observation.
  """

  if not (live_verify and capture_tool):
    return [
      DecisionNode(
        name=verify_node,
        kind=DecisionNodeKind.TOOL,
        target="vision.verify_object_in_bin",
        input={
          "target": "{{ target }}",
          # Until a post-place detector updates world state, use the commanded
          # release pose as the expected observation in deterministic tests.
          "pose_3d": commanded_pose,
        },
        save_as=save_as,
        on_success=on_success,
        on_failure=on_failure,
      )
    ]

  return [
    DecisionNode(
      name=capture_node,
      kind=DecisionNodeKind.TOOL,
      target=capture_tool,
      input={"out_dir": out_dir},
      save_as=frame_key,
      max_retries=1,
      on_success=redetect_node,
      on_failure=on_failure,
    ),
    DecisionNode(
      name=redetect_node,
      kind=DecisionNodeKind.TOOL,
      target=detect_tool,
      input=_detect_input(
        detect_tool=detect_tool,
        frame_key=frame_key,
        spatial_constraint_input=spatial_constraint_input,
      ),
      save_as=observed_key,
      max_retries=1,
      on_success=verify_node,
      on_failure=on_failure,
    ),
    DecisionNode(
      name=verify_node,
      kind=DecisionNodeKind.TOOL,
      target="vision.verify_object_in_bin",
      input={
        "target": "{{ target }}",
        "object_pose": f"{{{{ {observed_key} }}}}",
      },
      save_as=save_as,
      on_success=on_success,
      on_failure=on_failure,
    ),
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
