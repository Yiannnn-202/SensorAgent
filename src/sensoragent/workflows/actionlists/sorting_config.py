"""Configuration-driven pick-and-place for the industrial sorting scene."""

from collections.abc import Mapping
from typing import Any

from sensoragent.schemas import ActionList, ActionStep, ActionStepKind
from sensoragent.tools.robot.joint_poses import optional_configured_joint_pose


def build_sorting_config_pick_place_actionlist(
  joint_poses: Mapping[str, Any] | None = None,
) -> ActionList:
  """Build the verified config-detection route for the sorting scene."""
  pick_staging = optional_configured_joint_pose(joint_poses, "pick_staging_joints")
  place_staging = optional_configured_joint_pose(joint_poses, "place_staging_joints")

  return ActionList(
    name="industrial.sorting_config_pick_place_actionlist",
    description="Config-detected sorting-scene pick and center-bin placement.",
    inputs={"object_query": "string", "target": "string"},
    tags=("industrial", "sorting", "config-detect", "pick-place"),
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
          "orientation": "{{ object.grasp_orientation }}",
          # Keep the gripper fingers clear of the tabletop in Gazebo.
          "position_offset": [0.0, 0.0, "{{ object.pick_offset_z }}"],
          "approach_distance": 0.10,
          "pregrasp_distance": 0.04,
          "lift_height": 0.12,
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
          "pre_approach_joints": pick_staging,
          "speed": 0.35,
          "descent_speed": 0.25,
          "open_opening": "{{ object.release_opening }}",
          "close_opening": 0.032,
          "gripper_force": 1.0,
        },
        save_as="pick_result",
      ),
      ActionStep(
        name="verify_grasp",
        kind=ActionStepKind.SKILL,
        target="robot.verify_grasp",
        input={},
      ),
      ActionStep(
        name="resolve_place_target",
        kind=ActionStepKind.TOOL,
        target="robot.resolve_place_target",
        input={"target": "{{ target }}", "release_z": "{{ object.release_z }}"},
        save_as="place_target",
      ),
      ActionStep(
        name="plan_place",
        kind=ActionStepKind.TOOL,
        target="robot.plan_place",
        input={
          "place_pose": "{{ place_target.place_pose }}",
          "clearance": 0.04,
        },
        save_as="place_plan",
      ),
      ActionStep(
        name="place",
        kind=ActionStepKind.SKILL,
        target="robot.place",
        input={
          "object_id": "{{ object.object_id }}",
          "target": "{{ target }}",
          "plan": "{{ place_plan.plan }}",
          "pre_approach_joints": place_staging,
          "retreat_joints": place_staging,
          "linear_approach": False,
          "speed": 0.35,
          "open_opening": "{{ object.release_opening }}",
          "gripper_speed": 0.5,
        },
        save_as="place_result",
      ),
      ActionStep(
        name="verify_place",
        kind=ActionStepKind.SKILL,
        target="robot.verify_place",
        input={},
      ),
    ],
  )
