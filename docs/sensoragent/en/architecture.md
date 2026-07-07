# SensorAgent Architecture

SensorAgent is the agent-side orchestration repository for embodied tasks. It does not own Isaac Sim deployment, robot drivers, ROS 2 bringup, MoveIt2 configuration, or physical robot execution. Those capabilities are provided by other teams and are consumed through tools, skills, or integration adapters.

The repository focuses on:

```text
User / multimodal input
→ Agent planning
→ MCP-style skill and tool invocation
→ Action-list or decision-tree execution
→ Structured logging
→ External system adapters
```

## Responsibility Boundary

| Area | Owned here | Not owned here |
|---|---|---|
| Agent | Planning, tool selection, workflow execution | Robot firmware, ROS 2 drivers |
| Skills / tools | Schemas, registry, adapters, invocation logs | Low-level hardware implementation |
| Vision / audio | Optional processing tools and service clients | Camera deployment owned by runtime teams |
| Robot control | Tool adapter contracts | Mechanical arm control stack |
| Simulation | Tool adapter contracts | Isaac Sim scene deployment |
| Logging | Agent task logs, tool-call traces, workflow records | External runtime logs |

## Target Layout

```text
sensoragent/
├── src/
│   └── sensoragent/
│       ├── agent/                  # Agent loop, planner, tool selection
│       ├── mcp/                    # MCP-style contracts, server/client helpers
│       ├── skills/                 # Composable high-level capabilities
│       ├── tools/
│       │   ├── vision/             # Vision processing tools or external clients
│       │   ├── audio/              # ASR/TTS/audio tools or external clients
│       │   └── robot/              # Robot-control tool adapters
│       ├── workflows/
│       │   ├── actionlists/        # Ordered executable action lists
│       │   └── decision_trees/     # Branching task policies
│       ├── logger/                 # Agent-owned structured logging
│       ├── state/                  # Agent state, task context, event buffers
│       ├── integrations/           # External team interface adapters
│       ├── schemas/                # Shared Pydantic/dataclass schemas
│       ├── config/                 # Runtime configuration loading
│       └── services/
│           ├── api/                # HTTP/WebSocket service entry points
│           └── cli/                # CLI entry points
├── configs/                        # Project-level configs
├── docs/                           # Architecture and team documents
├── scripts/                        # Project-level startup and maintenance scripts
└── tests/                          # Unit and integration tests
```

## Core Concepts

### Tool

A tool is the smallest callable capability. It has a stable schema, clear input and output, failure semantics, and structured logs.

Examples:

```text
vision.detect_object
vision.segment_object
audio.transcribe
audio.speak
robot.pick
robot.place
robot.get_state
```

### Skill

A skill composes tools into a higher-level capability.

Examples:

```text
inspect_scene = capture image + detect objects + summarize
pick_and_place = detect target + call robot pick + call robot place + verify
```

### Workflow

A workflow is a task-specific execution policy. It can be a simple ordered action list or a decision tree with branches, retries, and recovery.

Competition-specific logic should live here rather than inside low-level tools.

### Logger

The logger is a first-class module. Every task should record:

```text
task id
user input
parsed intent
selected workflow
tool calls
tool inputs and outputs
duration
errors
retry decisions
final status
```

These logs are used for debugging, evaluation, report writing, replay, and future training data.

## Initial Development Priority

The first long phase of this project is to build the generic agent framework:

1. MCP-style tool and skill contracts.
2. Tool registry and skill registry.
3. Action-list runtime.
4. Decision-tree runtime.
5. Structured logger.
6. External adapter pattern.
7. Minimal API / CLI for invoking tasks.

Task-specific competition workflows should be added after the framework is stable.
