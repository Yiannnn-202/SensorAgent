"""Physical-hardware pick ActionList."""

from collections.abc import Mapping
from typing import Any

from sensoragent.schemas import ActionList, ActionStep, ActionStepKind
from sensoragent.workflows.actionlists.industrial import (
  GRIPPER_CLOSE_OPENING,
  PICK_DESCENT_SPEED,
  PICK_SPEED,
  observe_joints,
  optional_move_joints_step,
)


def build_hardware_pick_object_actionlist(
  joint_poses: Mapping[str, Any] | None = None,
) -> ActionList:
  """Capture, segment, select a configured profile, pick, verify, and observe."""
  observe = observe_joints(joint_poses)
  observe_pose = (joint_poses or {}).get("observe_pose")
  observe_before_steps = []
  if observe is not None:
    observe_before_steps = [
      ActionStep(
        name="ensure_observe_before_capture",
        kind=ActionStepKind.TOOL,
        target="robot.ensure_observe_pose",
        input={
          "joints": observe,
          "pose": observe_pose,
          "position_tolerance": 0.015,
          "speed": PICK_SPEED,
          "wait": True,
        },
      )
    ]
  return ActionList(
    name="hardware.pick_object_actionlist",
    description="Physical RGB-D pick using Grounded SAM2 and a configured pick profile.",
    inputs={"object_query": "string", "pick_profile": "string", "spatial_constraint": "object"},
    tags=("hardware", "pick", "grounded-sam2", "spatial", "verify"),
    steps=[
      *observe_before_steps,
      ActionStep(name="capture_frame", kind=ActionStepKind.TOOL, target="vision.capture_frame", input={}, save_as="frame"),
      ActionStep(
        name="detect_object", kind=ActionStepKind.TOOL, target="vision.grounded_sam2",
        input={"query": "{{ object_query }}", "image_path": "{{ frame.png_path }}", "cloud_path": "{{ frame.cloud_path }}", "T_base_camera": "{{ frame.T_base_camera }}", "spatial_constraint": "{{ spatial_constraint }}"}, save_as="object",
      ),
      ActionStep(name="select_pick_profile", kind=ActionStepKind.TOOL, target="robot.select_pick_profile", input={"label": "{{ object.label }}", "profile": "{{ pick_profile }}"}, save_as="pick_profile_selected"),
    ActionStep(
        name="plan_pick", kind=ActionStepKind.TOOL, target="{{ pick_profile_selected.planner }}",
        input={"pose_3d": "{{ object.pose_3d }}", "cloud_path": "{{ frame.cloud_path }}", "mask_polygons": "{{ object.mask_polygons }}", "center_px": "{{ object.center_px }}", "T_base_camera": "{{ frame.T_base_camera }}", "orientation": "{{ pick_profile_selected.orientation }}", "position_offset": "{{ pick_profile_selected.position_offset }}", "approach_distance": "{{ pick_profile_selected.approach_distance }}", "pregrasp_distance": "{{ pick_profile_selected.pregrasp_distance }}", "lift_height": "{{ pick_profile_selected.lift_height }}", "tcp_offset": "{{ pick_profile_selected.tcp_offset }}", "headward_offset": "{{ pick_profile_selected.headward_offset }}", "camera_left_offset_px": "{{ pick_profile_selected.camera_left_offset_px }}", "camera_left_offset_m": "{{ pick_profile_selected.camera_left_offset_m }}", "minimum_safe_z": "{{ pick_profile_selected.minimum_safe_z }}", "workspace_min": "{{ pick_profile_selected.workspace_min }}", "workspace_max": "{{ pick_profile_selected.workspace_max }}"}, save_as="pick_plan",
      ),
      ActionStep(name="pick", kind=ActionStepKind.SKILL, target="robot.pick", input={"plan": "{{ pick_plan.plan }}", "object_id": "{{ object.object_id }}", "speed": "{{ pick_profile_selected.motion_speed }}", "descent_speed": "{{ pick_profile_selected.descent_speed }}", "lift_speed": "{{ pick_profile_selected.lift_speed }}", "open_opening": "{{ pick_profile_selected.open_opening }}", "close_opening": "{{ pick_profile_selected.close_opening }}", "gripper_force": "{{ pick_profile_selected.gripper_force }}", "gripper_speed": "{{ pick_profile_selected.gripper_speed }}", "fallback_move_pose_on_grasp_failure": False}, save_as="pick_result"),
      ActionStep(name="verify_grasp", kind=ActionStepKind.SKILL, target="robot.verify_grasp", input={}, save_as="grasp_check"),
      *optional_move_joints_step("observe_after_pick", observe, PICK_SPEED),
    ],
  )
