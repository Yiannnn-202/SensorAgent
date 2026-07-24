"""Industrial pick-and-place ActionList definitions."""

from sensoragent.schemas import ActionList, ActionStep, ActionStepKind


PICK_APPROACH_DISTANCE = 0.10
PICK_PREGRASP_DISTANCE = 0.04
PICK_LIFT_HEIGHT = 0.12
PICK_POSITION_OFFSET = [0.0, 0.0, 0.03]
PICK_SPEED = 2.0
PICK_DESCENT_SPEED = 1.5
GRIPPER_CLOSE_OPENING = 0.02

PLACE_CLEARANCE = 0.15
PLACE_SPEED = 2.0
GRIPPER_OPEN_OPENING = 0.0848
GRIPPER_SPEED = 0.5

# Joint-space staging pose inserted before the place approach. Chosen to put
# the arm in a "hover over workbench, gripper pointing down" configuration
# whose J6=0, so OMPL doesn't need to twist the wrist by more than half a
# revolution when planning to the Cartesian bin approach. J1 is biased toward
# -Y to match the industrial bin_cell_* column (Y ≈ -0.06 to -0.30). Values in
# radians for the RM65-B DOF order [J1..J6].
PLACE_PRE_APPROACH_JOINTS = [-0.17, -0.57, -0.61, 0.0, -1.96, 0.0]


def build_industrial_pick_place_actionlist() -> ActionList:
  """Build the industrial pick → verify_grasp → place → verify_place workflow.

  The place phase is expanded inline rather than delegated to robot.place so
  we can (a) use a joint-space staging move to position the arm gripper-down
  above the bin column before the Cartesian descent, (b) skip an OMPL approach
  waypoint since MoveIt refuses to plan Cartesian OMPL moves while the gripper
  is closed on a payload, (c) tolerate the Robotiq bridge reporting a stall on
  gripper.open once the object is already released, and (d) retreat via a
  joint-space move because move_pose is similarly rejected right after release.
  """

  return ActionList(
    name="industrial.pick_place_actionlist",
    description="Industrial pick-and-place with grasp and place verification.",
    inputs={"object_query": "string", "target": "string"},
    tags=("industrial", "pick-place", "verify"),
    steps=[
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
      ActionStep(
        name="place_pre_approach_joints",
        kind=ActionStepKind.TOOL,
        target="robot.move_joints",
        input={
          "joints": PLACE_PRE_APPROACH_JOINTS,
          "speed": PLACE_SPEED,
          "wait": True,
        },
      ),
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
        name="place_retreat",
        kind=ActionStepKind.TOOL,
        target="robot.move_joints",
        input={
          "joints": PLACE_PRE_APPROACH_JOINTS,
          "speed": PLACE_SPEED,
          "wait": True,
        },
      ),
      ActionStep(
        name="verify_place",
        kind=ActionStepKind.SKILL,
        target="robot.verify_place",
        input={},
        save_as="place_check",
      ),
    ],
  )


def build_industrial_pick_only_actionlist() -> ActionList:
  """Pick an object and hold it. No destination is required; the arm ends at the
  lift pose with the gripper closed on the object."""

  return ActionList(
    name="industrial.pick_only_actionlist",
    description="Industrial pick with grasp verification; arm ends holding the object.",
    inputs={"object_query": "string"},
    tags=("industrial", "pick", "verify"),
    steps=[
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
    ],
  )


def build_industrial_place_only_actionlist() -> ActionList:
  """Place a held object into a named destination. Assumes the arm is already
  gripping the payload (verify_grasp is not run at entry — the caller is
  responsible for ensuring the object is held)."""

  return ActionList(
    name="industrial.place_only_actionlist",
    description="Industrial place: staging joints → descent → release → retreat, with verify_place.",
    inputs={"target": "string"},
    tags=("industrial", "place", "verify"),
    steps=[
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
      ActionStep(
        name="place_pre_approach_joints",
        kind=ActionStepKind.TOOL,
        target="robot.move_joints",
        input={
          "joints": PLACE_PRE_APPROACH_JOINTS,
          "speed": PLACE_SPEED,
          "wait": True,
        },
      ),
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
        name="place_retreat",
        kind=ActionStepKind.TOOL,
        target="robot.move_joints",
        input={
          "joints": PLACE_PRE_APPROACH_JOINTS,
          "speed": PLACE_SPEED,
          "wait": True,
        },
      ),
      ActionStep(
        name="verify_place",
        kind=ActionStepKind.SKILL,
        target="robot.verify_place",
        input={},
        save_as="place_check",
      ),
    ],
  )
