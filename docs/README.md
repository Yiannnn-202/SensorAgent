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

- [Grounding DINO red_block_v0 training handoff](guides/vision/grounding-dino-red-block-v0-cn.md)
- [Grounded SAM 2 strict Tool and red-block evaluation](guides/vision/grounded-sam2-tool-cn.md)
- [Open-vocabulary vision](guides/vision/open-vocabulary.md)
- [Public datasets and licenses](guides/vision/public-datasets.md)
- [Competition vision evaluation and data handoff](guides/vision/competition-evaluation-framework-cn.md)
- [Tabletop scene-aware candidate policy](guides/vision/scene-aware-candidate-policy-cn.md)
- [XH-202607 vision module technical packaging](guides/vision/competition-vision-module-packaging-cn.md)
- [SAM3 suitability assessment](guides/vision/sam3-assessment.md)
- [Gazebo vision VM setup](guides/vision/gazebo-vm-setup.md)
- [Gazebo RGB-D ActionList test](guides/vision/gazebo-actionlist-test.md)

### Simulation and robot integration

- [Physical RM65 + OmniPicker](guides/hardware/physical-rm65-omnipicker.md)
- [RM65-B Gazebo quickstart](guides/simulation/rm65b-quickstart.md)
- [RM65-B named joint poses](guides/simulation/rm65b-joint-poses.md)
- [Robot HTTP bridge](guides/simulation/robot-bridge.md)
- [Industrial Gazebo environment](guides/simulation/industrial-environment.md)
- [Gazebo pick test](guides/simulation/gazebo-pick-test.md)
- [Gazebo pick/place test](guides/simulation/gazebo-pick-place-test.md)
- [Sorting-scene grasp matrix test](guides/simulation/sorting-scene-grasp-matrix-test.md)
- [Phase G1 Gazebo smoke test](guides/simulation/g1-gazebo-smoke.md)
- [Gazebo recovery demo](guides/simulation/gazebo-recovery-demo.md)
- [Metal sorting text session (skip voice/vision)](guides/simulation/metal-sorting-text-session.md)
- [Create a grasping block](guides/simulation/create-grasp-block.md)

### Workflows

- [Intent to ActionList](guides/workflows/intent-to-actionlist.md)
- [Failure detection and recovery](guides/workflows/failure-recovery.md)
- [Competition multi-instance sorting session](guides/workflows/competition-sorting-session.md)

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
- [视频文案用视觉模块单页](team/vision_video_slide_cn.md)
- [8 月 5 日讨论后视觉任务闭环](team/vision_aug5_task_closure_cn.md)
- [XH-202607 视觉模块比赛交付清单](team/vision_competition_delivery_checklist_cn.md)

## Archive and assets

- `archive/progress-logs/`: dated execution and progress records that are no
  longer primary guidance.
- `assets/`: PDFs, spreadsheets, and other supporting files.

Archived records are evidence, not current status sources. Current project
status belongs in the root README, current work belongs in TODO, and
`planning/schedule.md` preserves the competition planning baseline and dated
progress assessments.

## Maintenance rules

| Change | Authoritative document |
| --- | --- |
| Repository-wide design or ownership | `architecture.md` |
| Current capabilities and quick start | `README.md` |
| Incomplete work or newly discovered blocker | `TODO.md` |
| Competition plan, milestones, and dated progress assessments | `docs/planning/schedule.md` |
| Durable setup, operation, or verification | Existing file under `docs/guides/` |
| Cross-module payload or error contract | `contracts/` |
| Historical progress record | `docs/archive/progress-logs/` |

Do not add another architecture, TODO, or project-status document.
