# Documentation

The repository root keeps three primary project documents and one operational
logging convention:

- [README](../README.md): project entry point, status, quick start, and navigation.
- [Architecture](../architecture.md): the single architecture source of truth.
- [TODO](../TODO.md): incomplete work, blockers, and immediate priorities.
- [Terminal progress logging](../TERMINAL_PROGRESS_LOGGING.md): the shared
  stderr/stdout convention for observable command-line pipelines.

Everything else is organized below by purpose. A topic should have one
authoritative document; other documents should link to it instead of repeating
the same status or design.

## Planning

- [Competition technical plan](planning/competition-plan.md)
- [Competition schedule and progress baseline](planning/schedule.md)
- [Vision delivery plan for August 10](planning/vision-aug10-delivery.md)

## Research

- [Task-sequence decomposition research](research/task-sequence-decomposition.md)

## Operational guides

### Audio

- [Local VAD, ASR, and TTS](guides/audio/local-audio.md)
- [Voice-driven robot simulation pipeline](guides/audio/voice-robot-simulation.md)

### Vision

- [Open-vocabulary vision](guides/vision/open-vocabulary.md)
- [Public datasets and licenses](guides/vision/public-datasets.md)
- [SAM3 suitability assessment](guides/vision/sam3-assessment.md)
- [Gazebo vision VM setup](guides/vision/gazebo-vm-setup.md)
- [Gazebo RGB-D ActionList test](guides/vision/gazebo-actionlist-test.md)

### Simulation and robot integration

- [RM65-B Gazebo quickstart](guides/simulation/rm65b-quickstart.md)
- [RM65-B named joint poses](guides/simulation/rm65b-joint-poses.md)
- [Robot HTTP bridge](guides/simulation/robot-bridge.md)
- [Industrial Gazebo environment](guides/simulation/industrial-environment.md)
- [Gazebo pick test](guides/simulation/gazebo-pick-test.md)
- [Gazebo pick/place test](guides/simulation/gazebo-pick-place-test.md)
- [Gazebo recovery demo](guides/simulation/gazebo-recovery-demo.md)
- [Create a grasping block](guides/simulation/create-grasp-block.md)

### Workflows

- [Intent to ActionList](guides/workflows/intent-to-actionlist.md)
- [Failure detection and recovery](guides/workflows/failure-recovery.md)

### Operations

- [Testing](guides/operations/testing.md)

## Reference

- [Robot simulation command reference](reference/robot-sim-commands.md)
- [Python package layout and registered targets](../src/sensoragent/README.md)
- [Cross-module contracts](../contracts/README.md)
- [RealMan RM65-B upstream selection](../ros2_ws/REALMAN_UPSTREAM.md)
- [Robotiq 2F-85 upstream selection](../ros2_ws/ROBOTIQ_UPSTREAM.md)

## Team records

- [Conventions](team/convention.md)
- [中文约定](team/convention_cn.md)
- [团队总览](team/general_cn.md)
- [视觉模块交接](team/vision_handoff_cn.md)

## Archive and assets

- `archive/progress-logs/`: dated execution and progress records that are no
  longer primary guidance.
- `assets/`: PDFs, spreadsheets, and other supporting files.

Archived records are evidence, not current status sources. Current project
status belongs in the root README, current work belongs in TODO, and schedule
status belongs in `planning/schedule.md`.

## Maintenance rules

| Change | Authoritative document |
| --- | --- |
| Repository-wide design or ownership | `architecture.md` |
| Current capabilities and quick start | `README.md` |
| Incomplete work or newly discovered blocker | `TODO.md` |
| Competition module levels and dates | `docs/planning/schedule.md` |
| Durable setup, operation, or verification | Existing file under `docs/guides/` |
| Cross-module payload or error contract | `contracts/` |
| Historical progress record | `docs/archive/progress-logs/` |

Do not add another architecture, TODO, or project-status document.
