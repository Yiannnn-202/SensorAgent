# SensorAgent

SensorAgent is the agent-side orchestration module for embodied tasks. It focuses on task understanding, skill/tool orchestration, workflow execution, external module integration, and structured logging.

It does **not** own Isaac Sim deployment, ROS 2 drivers, robot firmware, MoveIt2 configuration, or physical robot execution. Those capabilities are provided by other modules or teams and are consumed through API, MCP, WebSocket, or other documented adapters.

## Role in the System

```text
User / multimodal input
→ SensorAgent
→ skills / tools
→ API or MCP calls to external modules
→ task result and structured logs
```

SensorAgent is responsible for:

- Agent planning and task orchestration.
- MCP-style skills/tools contracts.
- ActionList and DecisionTree workflow execution.
- Vision/audio/robot tool adapters.
- External module integration through API or MCP.
- Agent-owned structured logging.

SensorAgent is not responsible for:

- Isaac Sim scene deployment.
- ROS 2 runtime ownership.
- Mechanical arm drivers or low-level control.
- Physical robot safety.
- Camera or hardware bringup.

## Repository Layout

```text
sensoragent/
├── configs/                 # Project-level configuration files
├── docs/                    # Project, team, and related-module docs
├── scripts/                 # Project-level startup and maintenance scripts
├── src/
│   └── sensoragent/
│       ├── agent/           # Agent loop, planning, orchestration
│       ├── mcp/             # MCP-style contracts and helpers
│       ├── skills/          # High-level reusable capabilities
│       ├── tools/           # Atomic tool adapters
│       ├── workflows/       # ActionList and DecisionTree workflows
│       ├── logger/          # Structured agent logging
│       ├── state/           # Agent state and task context
│       ├── integrations/    # External service adapters
│       ├── schemas/         # Shared schemas
│       ├── config/          # Configuration loading code
│       └── services/        # API and CLI entry points
└── tests/                   # Unit and integration tests
```

## Documentation

Start from the documentation index:

- [docs/README.md](docs/README.md)

Key SensorAgent documents:

- [Architecture](docs/sensoragent/architecture.md)
- [Module positioning](docs/sensoragent/positioning.md)
- [中文架构](docs/sensoragent/architecture_cn.md)

## Run the Mock Pipeline

The current Phase 1 demo runs a local mock Agent chain:

```text
CLI
→ AgentRuntime
→ mock.pick_and_place
→ vision.mock_detect
→ robot.mock_pick
→ robot.mock_place
→ structured task log
```

From the repository root:

```powershell
$env:PYTHONPATH = "$(Get-Location)\src"
python -m sensoragent.services.cli.main mock-pick-place --config configs\mock.yaml --object-query "silver roller" --target "third bin cell"
```

Or use the helper script:

```powershell
.\scripts\run_mock_pipeline.ps1 --object-query "silver roller" --target "third bin cell"
```

By default, manual runs write JSONL task logs under `logs\tasks\`.

You can also run through the Agent task lifecycle and planner:

```powershell
$env:PYTHONPATH = "$(Get-Location)\src"
python -m sensoragent.services.cli.main run-task "put the silver roller into the third bin cell" --config configs\mock.yaml --planner static --object-query "silver roller" --target "third bin cell"
```

To try the DeepSeek-backed planner, create a local `.env` from `.env.example`, set `SENSORAGENT_LLM_API_KEY`, then run:

```powershell
$env:PYTHONPATH = "$(Get-Location)\src"
python -m sensoragent.services.cli.main run-task "put the silver roller into the third bin cell" --config configs\mock.yaml --planner llm
```

## Development Focus

The current development phase focuses on building the generic Agent framework:

1. MCP/API collaboration mechanism.
2. Tool and skill registries.
3. ActionList runtime.
4. DecisionTree runtime.
5. Structured logger.
6. External adapter pattern.
7. Minimal API and CLI entry points.

Competition-specific workflows should be added after the core framework is stable.
