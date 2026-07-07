# Configuration

SensorAgent uses YAML configuration files to decide how the Agent runtime should be assembled for a given environment.

Configuration controls:

```text
which tools are enabled
which skills are enabled
which skill is the default
where logs are written
which environment mode is active
```

## Default mock configuration

The first supported configuration is:

```text
configs/mock.yaml
```

It enables the mock tools and mock skill used by the Phase 1 local call chain:

```yaml
agent:
  name: sensoragent
  mode: mock
  default_skill: mock.pick_and_place

tools:
  enabled:
    - vision.mock_detect
    - audio.mock_transcribe
    - robot.mock_pick
    - robot.mock_place

skills:
  enabled:
    - mock.pick_and_place
```

## Config path resolution

SensorAgent resolves the config file in this priority order:

```text
1. Explicit path passed by code or CLI
2. SENSORAGENT_CONFIG
3. SENSORAGENT_ENV mapped to configs/<env>.yaml
4. configs/mock.yaml
```

Examples:

```bash
SENSORAGENT_CONFIG=configs/dev.yaml
```

```bash
SENSORAGENT_ENV=mock
```

`SENSORAGENT_ENV=mock` maps to:

```text
configs/mock.yaml
```

`SENSORAGENT_ENV=competition` maps to:

```text
configs/competition.yaml
```

## Why this exists

The Agent framework should not hard-code which tools and skills are active. Different environments should be assembled through config:

```text
mock: all local mock tools
dev: mixed mock and real service adapters
competition: real vision/audio/robot tools
```

The code path remains the same; only the configuration changes.

## Current implementation

Configuration code lives under:

```text
src/sensoragent/config/
├── env.py       # Resolve config path from explicit path or environment variables
├── loader.py    # Load YAML into typed config objects
└── schema.py    # Dataclass config schemas
```

Runtime assembly lives in:

```text
src/sensoragent/agent/bootstrap.py
```

The main helpers are:

```python
load_config("configs/mock.yaml")
build_agent_from_config("configs/mock.yaml")
build_agent_from_env()
```
