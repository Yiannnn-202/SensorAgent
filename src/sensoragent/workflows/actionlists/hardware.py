"""Physical-hardware pick ActionList."""

from collections.abc import Mapping
from typing import Any

from sensoragent.schemas import ActionList, ActionStep, ActionStepKind
from sensoragent.workflows.actionlists.industrial import (
  PLACE_CLEARANCE,
  carry_joints,
  observe_joints,
  optional_move_joints_step,
  place_staging_joints,
)

HARDWARE_PLACE_RELEASE_OPENING = 0.040
HARDWARE_TRAVEL_SPEED = 1.0
HARDWARE_GRIPPER_SPEED = 0.75
# The gripper is clear of the bin immediately after release, so lift at max speed.
HARDWARE_POST_RELEASE_LIFT_SPEED = 1.0


def build_hardware_roller_approach_calibration_actionlist(
  joint_poses: Mapping[str, Any] | None = None,
  detect_tool: str = "vision.dual_branch_detect",
) -> ActionList:
  """Move above a detected roller for calibration without attempting a grasp."""

  observe = observe_joints(joint_poses)
  observe_pose = (joint_poses or {}).get("observe_pose")
  observe_steps = []
  if observe is not None:
    observe_steps = [
      ActionStep(
        name="ensure_observe_before_capture",
        kind=ActionStepKind.TOOL,
        target="robot.ensure_observe_pose",
        input={
          "joints": observe,
          "pose": observe_pose,
          "position_tolerance": 0.015,
          "speed": HARDWARE_TRAVEL_SPEED,
          "wait": True,
        },
      )
    ]
  return ActionList(
    name="hardware.calibrate_roller_approach_actionlist",
    description=(
      "Detect a roller and move only to its high approach pose for calibration; "
      "this workflow never descends, closes the gripper, or lifts an object."
    ),
    inputs={"object_query": "string", "spatial_constraint": "object"},
    tags=("hardware", "calibration", "roller", "approach-only", "vision"),
    steps=[
      *observe_steps,
      ActionStep(
        name="capture_frame",
        kind=ActionStepKind.TOOL,
        target="vision.capture_frame",
        input={},
        save_as="frame",
      ),
      ActionStep(
        name="detect_roller",
        kind=ActionStepKind.TOOL,
        target=detect_tool,
        input={
          "query": "{{ object_query }}",
          "image_path": "{{ frame.png_path }}",
          "cloud_path": "{{ frame.cloud_path }}",
          "T_base_camera": "{{ frame.T_base_camera }}",
          "spatial_constraint": "{{ spatial_constraint }}",
        },
        save_as="object",
      ),
      ActionStep(
        name="select_calibration_profile",
        kind=ActionStepKind.TOOL,
        target="robot.select_pick_profile",
        input={"label": "{{ object.label }}", "profile": "roller_calibration"},
        save_as="pick_profile_selected",
      ),
      ActionStep(
        name="plan_roller_approach",
        kind=ActionStepKind.TOOL,
        target="{{ pick_profile_selected.planner }}",
        input={"pose_3d": "{{ object.pose_3d }}", "cloud_path": "{{ frame.cloud_path }}", "mask_polygons": "{{ object.mask_polygons }}", "center_px": "{{ object.center_px }}", "T_base_camera": "{{ frame.T_base_camera }}", "orientation": "{{ pick_profile_selected.orientation }}", "position_offset": "{{ pick_profile_selected.position_offset }}", "approach_distance": "{{ pick_profile_selected.approach_distance }}", "pregrasp_distance": "{{ pick_profile_selected.pregrasp_distance }}", "lift_height": "{{ pick_profile_selected.lift_height }}", "tcp_offset": "{{ pick_profile_selected.tcp_offset }}", "grasp_point_mode": "{{ pick_profile_selected.grasp_point_mode }}", "headward_offset": "{{ pick_profile_selected.headward_offset }}", "camera_left_offset_px": "{{ pick_profile_selected.camera_left_offset_px }}", "camera_left_offset_m": "{{ pick_profile_selected.camera_left_offset_m }}", "minimum_safe_z": "{{ pick_profile_selected.minimum_safe_z }}", "lock_orientation": "{{ pick_profile_selected.lock_orientation }}", "orientation_mode": "{{ pick_profile_selected.orientation_mode }}", "workspace_min": "{{ pick_profile_selected.workspace_min }}", "workspace_max": "{{ pick_profile_selected.workspace_max }}"},
        save_as="pick_plan",
      ),
      ActionStep(
        name="move_roller_approach_only",
        kind=ActionStepKind.TOOL,
        target="robot.move_pose",
        input={"pose": "{{ pick_plan.plan.approach }}", "speed": 0.5, "wait": True},
      ),
    ],
  )


def build_hardware_roller_pregrasp_calibration_actionlist(
  joint_poses: Mapping[str, Any] | None = None,
  detect_tool: str = "vision.dual_branch_detect",
) -> ActionList:
  """Open safely above a roller, then move to its pregrasp pose."""

  approach = build_hardware_roller_approach_calibration_actionlist(
    joint_poses,
    detect_tool,
  )
  return ActionList(
    name="hardware.calibrate_roller_pregrasp_actionlist",
    description=(
      "Detect a roller, open the gripper at a high approach pose, then move "
      "only to its pregrasp pose; this workflow never reaches the grasp pose."
    ),
    inputs=approach.inputs,
    tags=("hardware", "calibration", "roller", "pregrasp-only", "vision"),
    steps=[
      *approach.steps,
      ActionStep(
        name="open_gripper_at_safe_approach",
        kind=ActionStepKind.TOOL,
        target="gripper.open",
        input={"opening": 0.120, "speed": 0.5},
      ),
      ActionStep(
        name="move_roller_pregrasp_only",
        kind=ActionStepKind.TOOL,
        target="robot.move_pose",
        input={"pose": "{{ pick_plan.plan.pregrasp }}", "speed": 0.35, "wait": True},
      ),
    ],
  )


def build_hardware_hex_nut_approach_calibration_actionlist(
  joint_poses: Mapping[str, Any] | None = None,
  detect_tool: str = "vision.dual_branch_detect",
) -> ActionList:
  """Move above a detected hex nut for calibration without attempting a grasp."""

  roller = build_hardware_roller_approach_calibration_actionlist(
    joint_poses,
    detect_tool,
  )
  return ActionList(
    name="hardware.calibrate_hex_nut_approach_actionlist",
    description=(
      "Detect a hex nut and move only to its high approach pose for calibration; "
      "this workflow never descends or operates the gripper."
    ),
    inputs=roller.inputs,
    tags=("hardware", "calibration", "hex-nut", "approach-only", "vision"),
    steps=[
      *roller.steps[:2],
      ActionStep(
        name="detect_hex_nut",
        kind=ActionStepKind.TOOL,
        target=detect_tool,
        input={"query": "{{ object_query }}", "image_path": "{{ frame.png_path }}", "cloud_path": "{{ frame.cloud_path }}", "T_base_camera": "{{ frame.T_base_camera }}", "spatial_constraint": "{{ spatial_constraint }}"},
        save_as="object",
      ),
      ActionStep(
        name="select_hex_nut_calibration_profile",
        kind=ActionStepKind.TOOL,
        target="robot.select_pick_profile",
        input={"label": "{{ object.label }}", "profile": "hex_nut_calibration"},
        save_as="pick_profile_selected",
      ),
      ActionStep(
        name="plan_hex_nut_approach",
        kind=ActionStepKind.TOOL,
        target="{{ pick_profile_selected.planner }}",
        input={"pose_3d": "{{ object.pose_3d }}", "cloud_path": "{{ frame.cloud_path }}", "mask_polygons": "{{ object.mask_polygons }}", "center_px": "{{ object.center_px }}", "T_base_camera": "{{ frame.T_base_camera }}", "orientation": "{{ pick_profile_selected.orientation }}", "position_offset": "{{ pick_profile_selected.position_offset }}", "approach_distance": "{{ pick_profile_selected.approach_distance }}", "pregrasp_distance": "{{ pick_profile_selected.pregrasp_distance }}", "lift_height": "{{ pick_profile_selected.lift_height }}", "tcp_offset": "{{ pick_profile_selected.tcp_offset }}", "grasp_point_mode": "{{ pick_profile_selected.grasp_point_mode }}", "headward_offset": "{{ pick_profile_selected.headward_offset }}", "camera_left_offset_px": "{{ pick_profile_selected.camera_left_offset_px }}", "camera_left_offset_m": "{{ pick_profile_selected.camera_left_offset_m }}", "minimum_safe_z": "{{ pick_profile_selected.minimum_safe_z }}", "lock_orientation": "{{ pick_profile_selected.lock_orientation }}", "orientation_mode": "{{ pick_profile_selected.orientation_mode }}", "workspace_min": "{{ pick_profile_selected.workspace_min }}", "workspace_max": "{{ pick_profile_selected.workspace_max }}"},
        save_as="pick_plan",
      ),
      ActionStep(
        name="move_hex_nut_approach_only",
        kind=ActionStepKind.TOOL,
        target="robot.move_pose",
        input={"pose": "{{ pick_plan.plan.approach }}", "speed": 0.5, "wait": True},
      ),
    ],
  )


def build_hardware_pick_object_actionlist(
  joint_poses: Mapping[str, Any] | None = None,
  detect_tool: str = "vision.dual_branch_detect",
) -> ActionList:
  """Capture, detect, select a configured profile, pick, verify, and observe."""
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
          "speed": HARDWARE_TRAVEL_SPEED,
          "wait": True,
        },
      )
    ]
  observe_after_steps = optional_move_joints_step("observe_after_pick", observe, HARDWARE_TRAVEL_SPEED)
  if observe is not None and observe_pose is not None:
    observe_after_steps = [
      ActionStep(
        name="observe_after_pick",
        kind=ActionStepKind.TOOL,
        target="robot.ensure_observe_pose",
        input={
          "joints": observe,
          "pose": observe_pose,
          "position_tolerance": 0.015,
          "speed": HARDWARE_TRAVEL_SPEED,
          "wait": True,
        },
      )
    ]
  return ActionList(
    name="hardware.pick_object_actionlist",
    description="Physical RGB-D pick using the configured detector and pick profile.",
    inputs={"object_query": "string", "pick_profile": "string", "spatial_constraint": "object"},
    tags=("hardware", "pick", "vision", "spatial", "verify"),
    steps=[
      *observe_before_steps,
      ActionStep(name="capture_frame", kind=ActionStepKind.TOOL, target="vision.capture_frame", input={}, save_as="frame"),
      ActionStep(
        name="detect_object",
        kind=ActionStepKind.TOOL,
        target=detect_tool,
        input={
          "query": "{{ object_query }}",
          "image_path": "{{ frame.png_path }}",
          "cloud_path": "{{ frame.cloud_path }}",
          "T_base_camera": "{{ frame.T_base_camera }}",
          "spatial_constraint": "{{ spatial_constraint }}",
        },
        save_as="object",
      ),
      ActionStep(name="select_pick_profile", kind=ActionStepKind.TOOL, target="robot.select_pick_profile", input={"label": "{{ object.label }}", "profile": "{{ pick_profile }}"}, save_as="pick_profile_selected"),
      ActionStep(
        name="plan_pick", kind=ActionStepKind.TOOL, target="{{ pick_profile_selected.planner }}",
        input={"pose_3d": "{{ object.pose_3d }}", "cloud_path": "{{ frame.cloud_path }}", "mask_polygons": "{{ object.mask_polygons }}", "center_px": "{{ object.center_px }}", "T_base_camera": "{{ frame.T_base_camera }}", "orientation": "{{ pick_profile_selected.orientation }}", "position_offset": "{{ pick_profile_selected.position_offset }}", "approach_distance": "{{ pick_profile_selected.approach_distance }}", "pregrasp_distance": "{{ pick_profile_selected.pregrasp_distance }}", "lift_height": "{{ pick_profile_selected.lift_height }}", "tcp_offset": "{{ pick_profile_selected.tcp_offset }}", "grasp_point_mode": "{{ pick_profile_selected.grasp_point_mode }}", "headward_offset": "{{ pick_profile_selected.headward_offset }}", "camera_left_offset_px": "{{ pick_profile_selected.camera_left_offset_px }}", "camera_left_offset_m": "{{ pick_profile_selected.camera_left_offset_m }}", "minimum_safe_z": "{{ pick_profile_selected.minimum_safe_z }}", "lock_orientation": "{{ pick_profile_selected.lock_orientation }}", "orientation_mode": "{{ pick_profile_selected.orientation_mode }}", "workspace_min": "{{ pick_profile_selected.workspace_min }}", "workspace_max": "{{ pick_profile_selected.workspace_max }}"}, save_as="pick_plan",
      ),
      ActionStep(name="pick", kind=ActionStepKind.SKILL, target="robot.pick", input={"plan": "{{ pick_plan.plan }}", "object_id": "{{ object.object_id }}", "speed": "{{ pick_profile_selected.motion_speed }}", "descent_speed": "{{ pick_profile_selected.descent_speed }}", "lift_speed": "{{ pick_profile_selected.lift_speed }}", "open_opening": "{{ pick_profile_selected.open_opening }}", "open_min_opening": "{{ pick_profile_selected.open_min_opening }}", "close_opening": "{{ pick_profile_selected.close_opening }}", "max_grasp_opening": "{{ pick_profile_selected.max_grasp_opening }}", "gripper_force": "{{ pick_profile_selected.gripper_force }}", "gripper_speed": "{{ pick_profile_selected.gripper_speed }}", "require_grasp_confirmation": "{{ pick_profile_selected.require_grasp_confirmation }}", "fallback_move_pose_on_grasp_failure": False}, save_as="pick_result"),
      ActionStep(name="verify_grasp", kind=ActionStepKind.SKILL, target="robot.verify_grasp", input={}, save_as="grasp_check"),
      *observe_after_steps,
    ],
  )


def build_hardware_pick_place_actionlist(
  joint_poses: Mapping[str, Any] | None = None,
  detect_tool: str = "vision.dual_branch_detect",
) -> ActionList:
  """Pick with the configured vision/profile path, then place into a configured cell."""

  observe = observe_joints(joint_poses)
  observe_pose = (joint_poses or {}).get("observe_pose")
  carry = carry_joints(joint_poses)
  place_staging = place_staging_joints(joint_poses)
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
          "speed": HARDWARE_TRAVEL_SPEED,
          "wait": True,
        },
      )
    ]
  observe_after_steps = optional_move_joints_step("observe_after_place", observe, HARDWARE_TRAVEL_SPEED)
  if observe is not None and observe_pose is not None:
    observe_after_steps = [
      ActionStep(
        name="observe_after_place",
        kind=ActionStepKind.TOOL,
        target="robot.ensure_observe_pose",
        input={
          "joints": observe,
          "pose": observe_pose,
          "position_tolerance": 0.015,
          "speed": HARDWARE_TRAVEL_SPEED,
          "wait": True,
        },
      )
    ]
  observe_after_pick_steps = optional_move_joints_step("observe_after_pick", observe, HARDWARE_TRAVEL_SPEED)
  if observe is not None and observe_pose is not None:
    observe_after_pick_steps = [
      ActionStep(
        name="observe_after_pick",
        kind=ActionStepKind.TOOL,
        target="robot.ensure_observe_pose",
        input={
          "joints": observe,
          "pose": observe_pose,
          "position_tolerance": 0.015,
          "speed": HARDWARE_TRAVEL_SPEED,
          "wait": True,
        },
      )
    ]
  return ActionList(
    name="hardware.pick_place_actionlist",
    description="Physical RGB-D pick using the configured detector, followed by bin placement.",
    inputs={"object_query": "string", "pick_profile": "string", "target": "string", "spatial_constraint": "object"},
    tags=("hardware", "pick-place", "vision", "spatial", "verify"),
    steps=[
      *observe_before_steps,
      ActionStep(name="capture_frame", kind=ActionStepKind.TOOL, target="vision.capture_frame", input={}, save_as="frame"),
      ActionStep(
        name="detect_object",
        kind=ActionStepKind.TOOL,
        target=detect_tool,
        input={
          "query": "{{ object_query }}",
          "image_path": "{{ frame.png_path }}",
          "cloud_path": "{{ frame.cloud_path }}",
          "T_base_camera": "{{ frame.T_base_camera }}",
          "spatial_constraint": "{{ spatial_constraint }}",
        },
        save_as="object",
      ),
      ActionStep(name="select_pick_profile", kind=ActionStepKind.TOOL, target="robot.select_pick_profile", input={"label": "{{ object.label }}", "profile": "{{ pick_profile }}"}, save_as="pick_profile_selected"),
      ActionStep(
        name="plan_pick", kind=ActionStepKind.TOOL, target="{{ pick_profile_selected.planner }}",
        input={"pose_3d": "{{ object.pose_3d }}", "cloud_path": "{{ frame.cloud_path }}", "mask_polygons": "{{ object.mask_polygons }}", "center_px": "{{ object.center_px }}", "T_base_camera": "{{ frame.T_base_camera }}", "orientation": "{{ pick_profile_selected.orientation }}", "position_offset": "{{ pick_profile_selected.position_offset }}", "approach_distance": "{{ pick_profile_selected.approach_distance }}", "pregrasp_distance": "{{ pick_profile_selected.pregrasp_distance }}", "lift_height": "{{ pick_profile_selected.lift_height }}", "tcp_offset": "{{ pick_profile_selected.tcp_offset }}", "grasp_point_mode": "{{ pick_profile_selected.grasp_point_mode }}", "headward_offset": "{{ pick_profile_selected.headward_offset }}", "camera_left_offset_px": "{{ pick_profile_selected.camera_left_offset_px }}", "camera_left_offset_m": "{{ pick_profile_selected.camera_left_offset_m }}", "minimum_safe_z": "{{ pick_profile_selected.minimum_safe_z }}", "lock_orientation": "{{ pick_profile_selected.lock_orientation }}", "orientation_mode": "{{ pick_profile_selected.orientation_mode }}", "workspace_min": "{{ pick_profile_selected.workspace_min }}", "workspace_max": "{{ pick_profile_selected.workspace_max }}"}, save_as="pick_plan",
      ),
      ActionStep(name="pick", kind=ActionStepKind.SKILL, target="robot.pick", input={"plan": "{{ pick_plan.plan }}", "object_id": "{{ object.object_id }}", "speed": "{{ pick_profile_selected.motion_speed }}", "descent_speed": "{{ pick_profile_selected.descent_speed }}", "lift_speed": "{{ pick_profile_selected.lift_speed }}", "open_opening": "{{ pick_profile_selected.open_opening }}", "open_min_opening": "{{ pick_profile_selected.open_min_opening }}", "close_opening": "{{ pick_profile_selected.close_opening }}", "max_grasp_opening": "{{ pick_profile_selected.max_grasp_opening }}", "gripper_force": "{{ pick_profile_selected.gripper_force }}", "gripper_speed": "{{ pick_profile_selected.gripper_speed }}", "require_grasp_confirmation": "{{ pick_profile_selected.require_grasp_confirmation }}", "fallback_move_pose_on_grasp_failure": False}, save_as="pick_result"),
      ActionStep(name="verify_grasp", kind=ActionStepKind.SKILL, target="robot.verify_grasp", input={}, save_as="grasp_check"),
      *observe_after_pick_steps,
      *optional_move_joints_step("carry_joints", carry, HARDWARE_TRAVEL_SPEED),
      ActionStep(name="resolve_place_target", kind=ActionStepKind.TOOL, target="robot.resolve_place_target", input={"target": "{{ target }}"}, save_as="place_target"),
      ActionStep(name="plan_place", kind=ActionStepKind.TOOL, target="robot.plan_place", input={"place_pose": "{{ place_target.place_pose }}", "clearance": PLACE_CLEARANCE}, save_as="place_plan"),
      *optional_move_joints_step("place_pre_approach_joints", place_staging, HARDWARE_TRAVEL_SPEED),
      ActionStep(name="place_move_approach", kind=ActionStepKind.TOOL, target="robot.move_pose", input={"pose": "{{ place_plan.plan.approach }}", "speed": HARDWARE_TRAVEL_SPEED, "wait": True}),
      ActionStep(name="place_move_place", kind=ActionStepKind.TOOL, target="robot.move_pose", input={"pose": "{{ place_plan.plan.place }}", "speed": HARDWARE_TRAVEL_SPEED, "wait": True}),
      ActionStep(name="place_open_gripper", kind=ActionStepKind.TOOL, target="gripper.open", input={"opening": HARDWARE_PLACE_RELEASE_OPENING, "speed": HARDWARE_GRIPPER_SPEED, "release": True}),
      ActionStep(name="place_lift_clearance", kind=ActionStepKind.TOOL, target="robot.move_linear", input={"pose": "{{ place_plan.plan.retreat }}", "speed": HARDWARE_POST_RELEASE_LIFT_SPEED, "wait": True}),
      ActionStep(name="place_close_gripper", kind=ActionStepKind.TOOL, target="gripper.close", input={"opening": 0.0, "force": 0.5, "speed": HARDWARE_GRIPPER_SPEED, "require_contact": False}),
      *optional_move_joints_step("place_retreat", place_staging, HARDWARE_TRAVEL_SPEED),
      *observe_after_steps,
    ],
  )
