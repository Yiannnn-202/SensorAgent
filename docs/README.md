# Documentation

The documentation set is organized around one architecture source, durable
operation guides, and a small number of project planning records.

## Primary documents

- [Architecture](architecture.md) — the single source for repository design,
  ownership boundaries, runtime structure, configuration, logging, audio, and
  robotics simulation.
- [Layered technical-report view](../architecture.md) — the derived
  perception / decision / execution presentation of the same system, kept for
  the competition report. `docs/architecture.md` wins on any disagreement.
- [Development backlog](../TODO.md) — the single source for planned and incomplete
  work.
- [Root README](../README.md) — entry point, quick start, CLI surface, and
  common commands.

## Package and interface documents

- [Python package layout and registered targets](../src/sensoragent/README.md)
- [Cross-module contracts](../contracts/README.md)

## Team documents

- [Conventions](team/convention.md)
- [中文约定](team/convention_cn.md)
- [团队总览](team/general_cn.md)
- [视觉模块阶段交接](team/vision_handoff_cn.md)
- [8 月 10 日视觉交付计划](team/vision_aug10_delivery_cn.md)

## Operational guides

- [Testing](guides/testing.md)
- [Audio](guides/audio.md)
- [Voice to Gazebo pick/place with vision verification](guides/audio_robot_sim_voice_pipeline.md)
- [RM65-B + Robotiq 2F-85 Gazebo quickstart](guides/rm65_b_gazebo_quickstart_cn.md)
- [RM65-B named joint pose tuning](guides/rm65_b_named_joint_poses.md)
- [SensorAgent simulation robot HTTP bridge](guides/robot_sim_bridge_cn.md)
- [Industrial tabletop Gazebo environment](guides/industrial_gazebo_environment_cn.md)
- [Industrial intent to ActionList workflow](guides/intent_to_actionlist_cn.md)
- [Failure detection and recovery planning](guides/failure_recovery_cn.md)
- [Gazebo failure recovery demo](guides/gazebo_recovery_demo_cn.md)
- [Open-vocabulary vision Tool](guides/vision_open_vocab_cn.md)
- [Public vision datasets and licenses](guides/vision_public_datasets_cn.md)
- [SAM3 适配性评估](guides/vision_sam3_assessment_cn.md)
- [Gazebo vision VM setup](guides/gazebo_vision_vm_setup.md)
- [Gazebo RGB-D vision ActionList test](guides/gazebo_vision_actionlist_test.md)
- [Gazebo pick pipeline test script](guides/gazebo_pick_pipeline_test.md)
- [Gazebo pick and place pipeline test scripts](guides/gazebo_pick_place_pipeline_test.md)
- [Terminal progress logging](guides/terminal_progress_logging.md)
- [Create a Gazebo grasping block](guides/create_grasp_block.md)

## Project planning and records

- [Competition technical plan](../COMPETITION_TECHNICAL_PLAN_CN.md)
- [Competition Gantt plan](../COMPETITION_GANTT_PLAN_CN.md)
- [Task sequence decomposition research](../TASK_SEQUENCE_DECOMPOSITION_RESEARCH_CN.md)
- [Robot simulation skill test commands](../ROBOT_SIM_SKILL_TEST_COMMANDS_CN.md)
- [2026-07-23 update log](guides/20260723George_Lin_updatelog.md)
- [2026-07-24 update log](guides/20260724George_Lin_updatelog.md)

## Robotics source records

- [RealMan RM65-B upstream selection](../ros2_ws/REALMAN_UPSTREAM.md)
- [Robotiq 2F-85 upstream selection](../ros2_ws/ROBOTIQ_UPSTREAM.md)

Do not add another architecture or TODO document. Add a guide only for durable
setup, operation, or verification instructions that do not belong in the root
README.

## Keeping documents current

When code changes, update the affected documents in the same change:

| Change | Documents to update |
| --- | --- |
| New or renamed Tool, Skill, ActionList, or DecisionTree | `src/sensoragent/README.md`, `docs/architecture.md`, and the matching contract in `contracts/` |
| New CLI command or script runner | root `README.md` and `docs/guides/testing.md` |
| New configuration key | the relevant `configs/*.yaml` comment and `docs/architecture.md` |
| New dependency | `requirements*.txt` or `pyproject.toml` plus the guide that installs it |
| Completed or newly discovered work | `TODO.md` |
