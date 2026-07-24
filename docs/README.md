# Documentation

The documentation set is intentionally small.

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
- [RM65-B + Robotiq 2F-85 Gazebo quickstart](guides/rm65_b_gazebo_quickstart_cn.md)
- [SensorAgent simulation robot HTTP bridge](guides/robot_sim_bridge_cn.md)
- [Industrial tabletop Gazebo environment](guides/industrial_gazebo_environment_cn.md)
- [Open-vocabulary vision Tool](guides/vision_open_vocab_cn.md)
- [Gazebo RGB-D vision ActionList test](guides/gazebo_vision_actionlist_test.md)
- [Gazebo pick pipeline test script](guides/gazebo_pick_pipeline_test.md)
- [Gazebo pick and place pipeline test scripts](guides/gazebo_pick_place_pipeline_test.md)
- [Create a Gazebo grasping block](guides/create_grasp_block.md)

## Robotics source records

- [RealMan RM65-B upstream selection](../ros2_ws/REALMAN_UPSTREAM.md)
- [Robotiq 2F-85 upstream selection](../ros2_ws/ROBOTIQ_UPSTREAM.md)

Do not add another architecture or TODO document. Add a guide only for durable
setup, operation, or verification instructions that do not belong in the root
README.
