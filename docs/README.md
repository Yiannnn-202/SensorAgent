# Documentation Index

Documentation is organized by scope. English is the preferred original language. Chinese translations or summaries use the same path and base name with a `_cn.md` suffix.

```text
docs/
├── sensoragent/   # SensorAgent-specific documentation
├── team/          # Team-level conventions and overview
└── modules/       # Related modules in the broader system
```

## SensorAgent project docs

These documents describe this repository and should be treated as the primary source for SensorAgent-specific architecture and boundaries.

| Document | Description |
|---|---|
| [sensoragent/architecture.md](sensoragent/architecture.md) | Architecture for this repository. |
| [sensoragent/architecture_cn.md](sensoragent/architecture_cn.md) | Chinese architecture for this repository. |
| [sensoragent/positioning.md](sensoragent/positioning.md) | SensorAgent's role in the overall project. |
| [sensoragent/configuration.md](sensoragent/configuration.md) | Configuration loading and environment selection. |
| [sensoragent/configuration_cn.md](sensoragent/configuration_cn.md) | Chinese configuration guide. |
| [sensoragent/logging.md](sensoragent/logging.md) | Logging policy and runtime log layout. |
| [sensoragent/logging_cn.md](sensoragent/logging_cn.md) | Chinese logging guide. |
| [sensoragent/robotics_extension_cn.md](sensoragent/robotics_extension_cn.md) | Discussion draft for the RM65-B, Gazebo, ROS 2, and reinforcement-learning repository extension. |

## Team-level docs

These documents describe team-wide conventions and the broader Aether 2607 architecture.

| Document | Description |
|---|---|
| [team/convention.md](team/convention.md) | Repository-wide code, documentation, CMake, and Git conventions. |
| [team/convention_cn.md](team/convention_cn.md) | Chinese conventions document. |
| [team/general_cn.md](team/general_cn.md) | Chinese summary of the team-level architecture and project plan. |

## Development and test docs

These documents describe how specific parts of the implementation are verified.

| Document | Description |
|---|---|
| [robotics/rm65_b_gazebo_quickstart_cn.md](robotics/rm65_b_gazebo_quickstart_cn.md) | Ubuntu guide for importing, building, and launching the RM65-B Gazebo and MoveIt 2 stack. |
| [development/tests/mock_pipeline.md](development/tests/mock_pipeline.md) | How to run and evaluate the current mock Agent pipeline. |
| [development/tests/audio_pipeline.md](development/tests/audio_pipeline.md) | How to run and evaluate the listen-once audio pipeline. |
| [development/audio_integration.md](development/audio_integration.md) | Review and migration plan for Radish ASR/TTS integration. |
| [development/audio_models.md](development/audio_models.md) | Local ASR/TTS model directory layout and Git policy. |

## Related module docs

These documents describe related modules owned by the broader project. They are useful context, but they are not SensorAgent's direct implementation scope.

| Document | Description |
|---|---|
| [modules/ecos.md](modules/ecos.md) | ECOS robot runtime document. |
| [modules/ecos_cn.md](modules/ecos_cn.md) | Chinese ECOS summary. |
| [modules/geca.md](modules/geca.md) | GECA agent-side document. |
| [modules/geca_cn.md](modules/geca_cn.md) | Chinese GECA summary. |
| [modules/arm.md](modules/arm.md) | Robotic arm module document. |
| [modules/base.md](modules/base.md) | Robotic base module document. |

## Rule of thumb

- Put SensorAgent-specific docs under `docs/sensoragent/`.
- Put team-wide process and overview docs under `docs/team/`.
- Put docs for other modules under `docs/modules/`.
- Use `_cn.md` for Chinese translations or summaries.
