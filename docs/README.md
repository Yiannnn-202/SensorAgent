# Documentation Index

The documentation is organized by scope first, then by language.

```text
docs/
├── sensoragent/    # SensorAgent-specific documentation
│   ├── en/         # English project docs
│   └── zh/         # Chinese project docs
├── team/           # Team-level conventions and system overview
│   └── zh/
└── modules/        # Documents for related modules in the broader system
    ├── en/
    └── zh/
```

## SensorAgent project docs

These documents describe this repository and should be treated as the primary source for SensorAgent-specific architecture and boundaries.

| Document | Description |
|---|---|
| [sensoragent/en/architecture.md](sensoragent/en/architecture.md) | English architecture for this repository. |
| [sensoragent/en/module-positioning.md](sensoragent/en/module-positioning.md) | English description of SensorAgent's role in the overall project. |
| [sensoragent/zh/architecture.md](sensoragent/zh/architecture.md) | Chinese architecture for this repository. |

## Team-level docs

These documents describe team-wide conventions and the broader Aether 2607 architecture.

| Document | Description |
|---|---|
| [team/zh/general-2607.md](team/zh/general-2607.md) | Chinese summary of the team-level architecture and project plan. |
| [team/zh/convention.md](team/zh/convention.md) | Team code, documentation, CMake, and Git conventions. |

## Related module docs

These documents describe related modules owned by the broader project. They are useful context, but they are not SensorAgent's direct implementation scope.

| Document | Description |
|---|---|
| [modules/en/ecos-2607.md](modules/en/ecos-2607.md) | English ECOS robot runtime document. |
| [modules/en/geca-2607.md](modules/en/geca-2607.md) | English GECA agent-side document. |
| [modules/en/robotic-arm-2607.md](modules/en/robotic-arm-2607.md) | English robotic arm module document. |
| [modules/en/robotic-base-2607.md](modules/en/robotic-base-2607.md) | English robotic base module document. |
| [modules/zh/ecos-2607.md](modules/zh/ecos-2607.md) | Chinese summary of the ECOS robot runtime document. |
| [modules/zh/geca-2607.md](modules/zh/geca-2607.md) | Chinese summary of the GECA agent-side document. |

## Rule of thumb

- Put SensorAgent-specific docs under `docs/sensoragent/`.
- Put team-wide process and overview docs under `docs/team/`.
- Put docs for other modules under `docs/modules/`.
- Keep language variants in `en/` or `zh/` subdirectories.
