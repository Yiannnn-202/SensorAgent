# SensorAgent

SensorAgent is the agent-side orchestration repository for embodied tasks. It
focuses on task understanding, skill/tool orchestration, workflow execution,
local VAD/ASR/TTS, structured logging, and RM65-B simulation development.

It does **not** own production robot drivers, firmware, physical safety, or hardware
bringup. The included ROS 2 workspace provides a local Gazebo and MoveIt 2
development stack, not the production robot runtime.

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
- External module integration through HTTP, API-shaped adapters, or MCP-style
  contracts.
- Agent-owned structured logging.
- Local Silero VAD and SenseVoice ASR command intake.
- Local file-based TTS generation through supported sherpa-onnx models.
- Reproducible local RM65-B + Robotiq 2F-85 Gazebo and MoveIt 2 integration.

SensorAgent is not responsible for:

- Isaac Sim scene deployment.
- Production ROS 2 runtime ownership.
- Mechanical arm drivers or low-level control.
- Physical robot safety.
- Camera or hardware bringup.

## Current Status

| Area | Status |
| --- | --- |
| Agent, Tool, Skill, ActionList, and DecisionTree runtimes | Implemented |
| Static and OpenAI-compatible LLM planning | Implemented with an allowed-target workflow whitelist |
| Local microphone VAD and SenseVoice ASR | Implemented |
| Local TTS file generation | Implemented; direct playback is intentionally disabled |
| RM65-B + Robotiq Gazebo and MoveIt stack | Implemented and manually exercised on Ubuntu |
| Backend-neutral robot Tools and pick/place Skills | Implemented |
| SensorAgent-to-Gazebo/MoveIt HTTP bridge | Implemented and used by Gazebo test scripts; automated ROS acceptance is not in the default suite |
| Industrial config-detect pick/place ActionLists | Implemented for the current tabletop world |
| Gazebo RGB-D open-vocabulary vision ActionList | Implemented as an optional vision path |
| Failure classification and recovery planning | Implemented as reusable tools; full recovery tree pending |
| Physical robot connection | Not connected |
| Industrial Gazebo tabletop scenario | Initial environment implemented under the ROS 2 bringup package |
| Gymnasium RL environment | Not implemented |

The reusable robot control surface now includes state, joint motion, pose motion,
linear motion, stop, gripper control, deterministic pick/place planning, named
place-target resolution, and `robot.pick` / `robot.place` / verification Skills.
`configs/robot_mock.yaml` selects the deterministic fake backend, while
`configs/robot_sim.yaml` selects `HttpRobotControlClient`, scene objects,
place targets, optional open-vocabulary vision, visual verification, and recovery
classification tools. The physical robot is not connected.

## Repository Layout

```text
sensoragent/
├── configs/                 # Project-level configuration files
├── docs/                    # Architecture, team documents, and guides
├── scripts/                 # Project-level startup and maintenance scripts
├── ros2_ws/                 # Local ROS 2 simulation workspace
│   └── src/
│       ├── rm_description/                  # Locally imported RM65-B model
│       ├── rm_gazebo/                       # Locally imported arm-only Gazebo stack
│       ├── rm_65_config/                    # Locally imported arm-only MoveIt config
│       ├── robotiq_description/             # Vendored Robotiq 2F-85 model
│       ├── sensoragent_rm65_b_bringup/      # Combined arm/gripper stack
│       └── sensoragent_robot_bridge/         # HTTP-to-ROS 2 simulation bridge
├── simulation/              # Gazebo worlds, models, and scenarios
├── reinforcement_learning/  # Future RL environments and policies
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

- [Architecture](docs/architecture.md)
- [Competition technical plan](COMPETITION_TECHNICAL_PLAN_CN.md)
- [Development backlog](TODO.md)
- [Testing guide](docs/guides/testing.md)
- [Audio guide](docs/guides/audio.md)
- [RM65-B Gazebo quickstart](docs/guides/rm65_b_gazebo_quickstart_cn.md)
- [Simulation robot HTTP bridge](docs/guides/robot_sim_bridge_cn.md)
- [Industrial intent to ActionList guide](docs/guides/intent_to_actionlist_cn.md)
- [Failure detection and recovery guide](docs/guides/failure_recovery_cn.md)
- [Open-vocabulary vision guide](docs/guides/vision_open_vocab_cn.md)
- [Gazebo RGB-D vision ActionList test](docs/guides/gazebo_vision_actionlist_test.md)

## RM65-B and Robotiq Simulation

The tracked `sensoragent_rm65_b_bringup` package combines:

```text
RealMan RM65-B
└── Link6
    └── Robotiq 2F-85
```

The gripper is attached to `Link6` by a fixed joint. A single
`gz_ros2_control` system manages the six arm joints and two independently
effort-controlled parallel gripper joints. MoveIt exposes separate `rm_group`
and `gripper` planning groups.

On Ubuntu 22.04 with ROS 2 Humble, prepare the workspace once:

```bash
bash scripts/linux/prepare_rm65_b_sim.sh
```

After that, start the complete Gazebo and MoveIt stack with one command:

```bash
bash scripts/linux/run_rm65_b_sim.sh
```

An optional shell alias reduces this to `sensoragent-sim`; see the
[full Ubuntu guide](docs/guides/rm65_b_gazebo_quickstart_cn.md).

To start Gazebo without MoveIt and RViz:

```bash
bash scripts/linux/run_rm65_b_sim.sh start_moveit:=false
```

The combined model, arm motion, and gripper opening/closing have been manually
exercised on Ubuntu. Repeatable object-contact and grasp-stability acceptance
remain before this simulation should be used for reinforcement learning. See the
[full Ubuntu guide](docs/guides/rm65_b_gazebo_quickstart_cn.md).

## Local Voice Command Pipeline

The local path is:

```text
microphone
→ SoundDeviceVadRecorder
→ Silero VAD
→ SenseVoice ASR
→ Agent planner
→ approved workflow target
```

Install the Python runtime dependencies:

```bash
python -m pip install -r requirements.txt
```

Place local model assets under the ignored `models/` directory as described in
the [audio guide](docs/guides/audio.md), configure the LLM credentials in an
ignored `.env`, and run:

```bash
PYTHONPATH=src python -m sensoragent.services.cli.main \
  listen-task \
  --config configs/audio_local.yaml \
  --planner llm \
  --duration 15
```

`--duration` is the maximum listening window. The realtime VAD recorder stops
after speech followed by the configured silence tail.

The repository also includes `audio.listen_command`, `audio.announce`, and
`audio.voice_command_ack_actionlist`. TTS currently writes an audio file; local
playback and automatic task-result announcements are not enabled.

## Run the Mock Pipeline

The local mock Agent chain is the fastest Windows-friendly smoke test:

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

To try the listen-once audio path with fake audio components:

```powershell
$env:PYTHONPATH = "$(Get-Location)\src"
python -m sensoragent.services.cli.main listen-task --config configs\audio_mock.yaml --planner static --duration 1 --object-query "silver roller" --target "third bin cell"
```

## Run the Industrial Gazebo Workflows

On Ubuntu 22.04 with ROS 2 Humble, start Gazebo, MoveIt, and the HTTP bridge:

```bash
bash scripts/linux/run_rm65_b_sim.sh
curl http://127.0.0.1:8765/ready
```

Run the config-based industrial ActionList without moving the robot:

```bash
PYTHONPATH=src .venv312/bin/python scripts/linux/run_industrial_actionlist_sim.py \
  --planner static \
  --object-query roller \
  --target bin_cell_3
```

Add `--execute` after checking the scene and bridge readiness. The optional
RGB-D path captures one Gazebo frame, runs `vision.open_vocab_detect`, then
executes the parallel vision ActionList:

```bash
PYTHONPATH=src .venv312/bin/python scripts/linux/run_gazebo_vision_actionlist_sim.py \
  --object-query "red roller" \
  --target bin_cell_3 \
  --execute
```

## Current Development Priorities

1. Add automated ROS 2/Gazebo acceptance tests and repeatable scene reset.
2. Connect recognized voice commands to approved robot workflows.
3. Broaden industrial object/bin coverage with recovery branches.
4. Define the Gymnasium observation, action, reward, and termination contract.
5. Add service entry points and a physical robot adapter.

The Python Agent package currently declares Python 3.12, while Ubuntu 22.04 and
ROS 2 Humble normally use Python 3.10. The implemented design keeps them in
separate processes and connects them through HTTP.
