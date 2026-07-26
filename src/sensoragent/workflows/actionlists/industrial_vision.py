"""Industrial pick-and-place ActionList backed by open-vocabulary vision."""

from sensoragent.schemas import ActionList, ActionStep, ActionStepKind
from sensoragent.workflows.actionlists.industrial import (
  GRIPPER_CLOSE_OPENING,
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


def build_industrial_vision_pick_place_actionlist() -> ActionList:
  """Build an industrial pick-place workflow using vision.open_vocab_detect."""

  return ActionList(
    name="industrial.vision_pick_place_actionlist",
    description="Industrial pick-and-place using open-vocabulary RGB-D detection.",
    inputs={
      "object_query": "string",
      "target": "string",
      "image_path": "string",
      "depth_path": "string",
      "camera_info_path": "string",
      "T_base_camera": "array",
      "spatial_constraint": "object",
    },
    tags=("industrial", "pick-place", "vision", "verify"),
    steps=[
      ActionStep(
        name="detect_object",
        kind=ActionStepKind.TOOL,
        target="vision.open_vocab_detect",
        input={
          "query": "{{ object_query }}",
          "image_path": "{{ image_path }}",
          "depth_path": "{{ depth_path }}",
          "camera_info_path": "{{ camera_info_path }}",
          "T_base_camera": "{{ T_base_camera }}",
          "spatial_constraint": "{{ spatial_constraint }}",
        },
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
