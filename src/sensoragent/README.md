# `sensoragent` Package Layout

This directory contains the core Python package for SensorAgent. It is organized around the Agent framework rather than any specific robot, simulator, or perception backend.

```text
src/sensoragent/
├── agent/
├── mcp/
├── skills/
├── tools/
│   ├── audio/
│   ├── robot/
│   └── vision/
├── workflows/
│   ├── actionlists/
│   └── decision_trees/
├── logger/
├── state/
├── integrations/
├── schemas/
├── config/
└── services/
    ├── api/
    └── cli/
```

## `agent/`

Agent runtime, planning, orchestration, and task lifecycle management.

Expected files:

```text
runtime.py       # Main Agent runtime loop
bootstrap.py     # Build runtime objects from config
planner.py       # Planner protocol and deterministic StaticPlanner baseline
llm_planner.py   # DeepSeek/OpenAI-compatible LLMPlanner implementation
selector.py      # Workflow selector interface
prompts/         # Prompt templates for future/active LLM planners
errors.py        # Agent-level exceptions
```

`planner.py` defines what a planner is and provides the non-LLM baseline. `llm_planner.py` is one concrete planner implementation that calls an OpenAI-compatible LLM endpoint and converts model JSON into an `AgentPlan`.

## `mcp/`

MCP-style protocol definitions and transport helpers for collaboration with external modules.

Expected files:

```text
server.py        # MCP server entry point or wrapper
client.py        # MCP client for external tools/agents
contracts.py     # Tool/resource contract definitions
registry.py      # MCP capability discovery and registry helpers
errors.py        # MCP-related exceptions
mock.py          # Local MCP/API-shaped mock entry point
```

## `skills/`

Composable high-level capabilities built from tools.

Expected files:

```text
base.py          # Skill base class or protocol
registry.py      # Skill registration and lookup
runtime.py       # Skill execution helper
definitions.py   # Built-in skill definitions
```

Example skills:

```text
inspect_scene
pick_and_place
verify_object_placement
recover_from_failure
```

## `tools/`

Atomic callable capabilities exposed to Agent workflows and skills.

Expected files:

```text
base.py          # Tool base class or protocol
registry.py      # Tool registration and lookup
runtime.py       # Tool invocation wrapper, timeout, error handling
errors.py        # Tool-related exceptions
```

### `tools/vision/`

Vision-related tools or clients for external vision agents.

Expected files:

```text
detect.py        # Object detection tool adapter
segment.py       # Segmentation tool adapter
verify.py        # Visual verification tool adapter
client.py        # Client for external vision service/agent
schemas.py       # Vision-specific input/output schemas
```

### `tools/audio/`

Audio-related tools or clients for ASR/TTS/audio event services.

Expected files:

```text
transcribe.py    # Speech-to-text tool adapter
speak.py         # Text-to-speech tool adapter
events.py        # Audio event detection adapter
client.py        # Client for external audio service/agent
schemas.py       # Audio-specific input/output schemas
```

### `tools/robot/`

Robot-control tool adapters. These call external robot runtimes; they do not implement low-level robot control.

Expected files:

```text
pick.py          # Pick tool adapter
place.py         # Place tool adapter
move.py          # Move/move_to tool adapter
state.py         # Robot state query adapter
client.py        # Client for external robot runtime
schemas.py       # Robot-specific input/output schemas
```

## `workflows/`

Task-specific execution policies.

Expected files:

```text
errors.py        # Workflow-related exceptions
actionlists/     # Linear workflows
decision_trees/  # Branching workflows
registry.py      # Future workflow registration and selection
errors.py        # Workflow-related exceptions
```

### `workflows/actionlists/`

Linear ordered action-list workflows.

Expected files:

```text
base.py          # ActionList definition
runtime.py       # Sequential action execution
mock.py          # Mock pick-and-place ActionList
industrial_pick_place.py
```

### `workflows/decision_trees/`

Branching workflows with conditions, retries, and recovery paths.

Expected files:

```text
base.py          # Decision tree node definitions
runtime.py       # Decision tree execution
mock.py          # Mock retry/not-found DecisionTrees
industrial_pick_place.py
```

## `logger/`

Structured logging infrastructure owned by SensorAgent.

Expected files:

```text
task.py          # Task-level logger
span.py          # Tool/skill/workflow span logging
sink.py          # File/console/remote log sinks
formatter.py     # JSON and human-readable formatting
context.py       # Trace/task context propagation
```

The logger is infrastructure, not a normal skill. It should be called automatically by runtimes and middleware.

## `state/`

Agent runtime state, task context, and event buffers.

Expected files:

```text
task.py          # TaskState and lifecycle status
events.py        # Agent event model and buffers
store.py         # In-memory task store
memory.py        # Future short-term task memory
```

## `integrations/`

Adapters for external modules, services, agents, or runtimes.

Expected files:

```text
base.py          # Integration client protocol
http.py          # HTTP API client helpers
websocket.py     # WebSocket client helpers
mcp.py           # MCP integration client helpers
llm.py           # OpenAI-compatible LLM client
vision.py        # Vision-agent integration
audio.py         # Audio-agent integration
robot.py         # Robot-runtime integration
```

## `schemas/`

Shared typed data structures used across the package.

Expected files:

```text
core.py          # Agent/tool/skill/log schemas
workflow.py      # ActionList and DecisionTree schemas
plan.py          # AgentPlan and planner target schemas
```

## `config/`

Configuration loading and validation code.

Expected files:

```text
loader.py        # Load YAML/JSON/env configuration
schema.py        # Typed config schemas
env.py           # Environment variable handling
defaults.py      # Built-in default values
```

The root `configs/` directory stores configuration files; this package directory stores the code that loads and validates them.

## `services/`

Runtime entry points for exposing SensorAgent to users or other modules.

Expected files:

```text
app.py           # Shared service construction helpers
```

### `services/api/`

HTTP/WebSocket service entry points.

Expected files:

```text
server.py        # API server entry point
routes.py        # HTTP routes
websocket.py     # Event streaming / task socket
schemas.py       # API-specific request/response schemas
```

### `services/cli/`

Command-line entry points.

Expected files:

```text
main.py          # CLI entry point
commands.py      # CLI command definitions
format.py        # CLI output formatting
```

## Rule of Thumb

- Put Agent decision logic in `agent/`.
- Put protocol and capability contracts in `mcp/`.
- Put reusable capability composition in `skills/`.
- Put atomic callable adapters in `tools/`.
- Put task-specific procedures in `workflows/`.
- Put external service connection details in `integrations/`.
- Put shared typed models in `schemas/`.
- Put runtime logging infrastructure in `logger/`.
- Put configuration loading code in `config/`, not in root `configs/`.
