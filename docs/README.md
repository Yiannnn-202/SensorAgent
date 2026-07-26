# Documentation

The documentation set is organized around one architecture source, durable
operation guides, and a small number of project planning records.

## Primary documents

- [Architecture](architecture.md) — the single source for repository design,
  ownership boundaries, runtime structure, configuration, logging, audio, and
  robotics simulation.
- [Development backlog](../TODO.md) — the single source for planned and incomplete
  work.

## Team documents

- [Conventions](team/convention.md)
- [中文约定](team/convention_cn.md)
- [团队总览](team/general_cn.md)

## Operational guides

- [Testing](guides/testing.md)
- [Audio](guides/audio.md)
- [Robot backend selection plan](guides/robot_backend_selection.md)
- [RM65-B + Robotiq 2F-85 Gazebo quickstart](guides/rm65_b_gazebo_quickstart_cn.md)
- [SensorAgent simulation robot HTTP bridge](guides/robot_sim_bridge_cn.md)
- [Industrial tabletop Gazebo environment](guides/industrial_gazebo_environment_cn.md)
- [Industrial intent to ActionList workflow](guides/intent_to_actionlist_cn.md)
- [Open-vocabulary vision Tool](guides/vision_open_vocab_cn.md)
- [Gazebo vision VM setup](guides/gazebo_vision_vm_setup.md)
- [Gazebo RGB-D vision ActionList test](guides/gazebo_vision_actionlist_test.md)
- [Gazebo pick pipeline test script](guides/gazebo_pick_pipeline_test.md)
- [Gazebo pick and place pipeline test scripts](guides/gazebo_pick_place_pipeline_test.md)
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
