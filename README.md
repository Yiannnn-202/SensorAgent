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
| Gazebo RGB-D frame capture Tool (`vision.capture_frame`) | Implemented; requires a ROS 2 Python interpreter on Ubuntu |
| Offline vision dataset evaluation harness | Implemented; datasets and weights stay local |
| Failure classification and recovery DecisionTree | Implemented for the industrial pick/place flow, including a live-perception mode; Gazebo acceptance pending |
| HTTP/WebSocket/MCP service entry points | Not implemented; only the CLI exists |
| Physical robot connection | Not connected |
| Industrial Gazebo tabletop scenario | Initial environment implemented under the ROS 2 bringup package |
| Gymnasium RL environment | Not implemented |

The reusable robot control surface now includes state, joint motion, pose motion,
linear motion, stop, gripper control, deterministic pick/place planning, named
place-target resolution, and `robot.pick` / `robot.place` / verification Skills.
`configs/robot_mock.yaml` selects the deterministic fake backend, while
`configs/robot_sim.yaml` selects `HttpRobotControlClient`, scene objects,
place targets, optional open-vocabulary vision, visual verification, recovery
classification tools, and `industrial.recovery_pick_place_tree`. The physical
robot is not connected.

## Quick Start

Python 3.12 is required for the Agent package.

```powershell
python -m pip install -r requirements.txt          # core runtime + local audio
python -m pip install -r requirements-vision.txt   # only for the vision model path
python -m pip install onnxruntime pytest           # Silero VAD and the pytest-based tests
```

Runtime configuration is resolved in this order: an explicit `--config` path,
`SENSORAGENT_CONFIG`, `SENSORAGENT_ENV` mapped to `configs/<env>.yaml`, then
`configs/mock.yaml`. Copy `.env.example` to an ignored `.env` for LLM
credentials and logging overrides. Other recognized variables are
`SENSORAGENT_ROS_PYTHON` (ROS 2 interpreter used by RGB-D capture),
`SENSORAGENT_GROUNDING_DINO_MODEL`, and `SENSORAGENT_SAM2_WEIGHTS`.

Run the default offline test suite:

```powershell
$env:PYTHONPATH = "$(Get-Location)\src"
python -m unittest discover -s tests -p 'test_*.py'
```

See the [testing guide](docs/guides/testing.md) for the suite's scope and its
current known issues.

## Repository Layout

```text
sensoragent/
├── configs/                 # Project-level configuration files
├── contracts/               # Language-neutral cross-module JSON contracts
├── docs/                    # Architecture, team documents, and guides
├── logs/                    # Ignored task logs, traces, audio, and captures
├── models/                  # Ignored local ASR, TTS, and vision weights
├── scripts/                 # Windows mock runner, vision evaluation, Linux Gazebo runners
├── ros2_ws/                 # Local ROS 2 simulation workspace
│   └── src/
│       ├── rm_description/                  # Locally imported RM65-B model
│       ├── rm_gazebo/                       # Locally imported arm-only Gazebo stack
│       ├── rm_65_config/                    # Locally imported arm-only MoveIt config
│       ├── robotiq_description/             # Vendored Robotiq 2F-85 model
│       ├── sensoragent_rm65_b_bringup/      # Combined arm/gripper stack, worlds, models
│       ├── sensoragent_robot_bridge/        # HTTP-to-ROS 2 simulation bridge
│       └── sensoragent_rm65_b_{description,gazebo,moveit_config}/  # Reserved, empty
├── simulation/              # Reserved Gazebo worlds, models, and scenarios
├── reinforcement_learning/  # Future RL environments and policies
├── src/
│   └── sensoragent/
│       ├── agent/           # Agent loop, planning, orchestration
│       ├── config/          # Configuration loading code
│       ├── contracts/       # JSON contract validation helpers
│       ├── evaluation/      # Offline vision dataset evaluation
│       ├── integrations/    # External and local service adapters
│       ├── logger/          # Structured agent logging
│       ├── mcp/             # MCP-style contracts and helpers
│       ├── recovery/        # Failure evidence, classification, recovery planning
│       ├── schemas/         # Shared schemas
│       ├── services/        # CLI entry point and reserved API package
│       ├── skills/          # High-level reusable capabilities
│       ├── state/           # Agent state and task context
│       ├── tools/           # Atomic tool adapters
│       └── workflows/       # ActionList and DecisionTree workflows
└── tests/                   # Unit and integration tests
```

## Command-line Surface

`python -m sensoragent.services.cli.main` (or the installed `sensoragent`
script) currently exposes:

| Command | Purpose |
| --- | --- |
| `mock-pick-place` | Run the mock skill chain end to end |
| `run-task` | Run a natural-language task through the static or LLM planner |
| `listen-task` | Record one utterance, transcribe it, and plan from the transcript |
| `vision-detect` | Run open-vocabulary detection on one RGB(-D) image and print the Tool result |

Gazebo workflows are driven by `scripts/linux/` runners instead of CLI
subcommands. See the [testing guide](docs/guides/testing.md) for the full list.

## Documentation

Start from the documentation index:

- [docs/README.md](docs/README.md)

Key SensorAgent documents:

- [Architecture (single source)](docs/architecture.md)
- [Layered technical-report view](architecture.md)
- [Competition technical plan](COMPETITION_TECHNICAL_PLAN_CN.md)
- [Development backlog](TODO.md)
- [Testing guide](docs/guides/testing.md)
- [Audio guide](docs/guides/audio.md)
- [RM65-B Gazebo quickstart](docs/guides/rm65_b_gazebo_quickstart_cn.md)
- [RM65-B named joint pose tuning](docs/guides/rm65_b_named_joint_poses.md)
- [Simulation robot HTTP bridge](docs/guides/robot_sim_bridge_cn.md)
- [Industrial tabletop Gazebo environment](docs/guides/industrial_gazebo_environment_cn.md)
- [Industrial intent to ActionList guide](docs/guides/intent_to_actionlist_cn.md)
- [Failure detection and recovery guide](docs/guides/failure_recovery_cn.md)
- [Gazebo failure recovery demo](docs/guides/gazebo_recovery_demo_cn.md)
- [Open-vocabulary vision guide](docs/guides/vision_open_vocab_cn.md)
- [Gazebo vision VM setup](docs/guides/gazebo_vision_vm_setup.md)
- [Gazebo RGB-D vision ActionList test](docs/guides/gazebo_vision_actionlist_test.md)
- [Team conventions](docs/team/convention.md)

## Vision Model Training and Evaluation

The open-vocabulary model path uses `vision.open_vocab_detect` for both the
temporary YOLOE baseline and the Grounding DINO + SAM 2 teacher model. Validate a
portable dataset manifest before running a long evaluation:

```powershell
python scripts\vision_eval.py validate `
  --manifest configs\vision_dataset.example.jsonl `
  --allow-missing-files
```

Run a labeled local dataset with one persistent model instance:

```powershell
python scripts\vision_eval.py run `
  --manifest data\vision\competition_test.jsonl `
  --config configs\vision_grounding_dino.yaml `
  --output-dir runs\vision\competition_test `
  --device 0 `
  --require-masks `
  --save-overlays
```

The runner saves per-sample JSONL, aggregate metrics, Tool logs, and optional
overlays. Dataset images, model weights, caches, and `runs/` outputs remain local.

The first fixed-class baseline uses YOLO11n-seg. Validate its Ultralytics dataset
before allocating GPU time:

```powershell
python scripts\vision_train.py `
  --data data\vision\competition\dataset.yaml `
  --dry-run
```

After the class map, scene-level splits, and polygon labels are reviewed, train
the reproducible baseline with:

```powershell
python scripts\vision_train.py `
  --data data\vision\competition\dataset.yaml `
  --model models\vision\yolo11n-seg.pt `
  --device 0
```

`configs/vision_train.example.yaml` records the proposed competition class map.
It is a template, not a checked-in dataset or evidence that a model has trained.
See the [Chinese open-vocabulary vision guide](docs/guides/vision_open_vocab_cn.md)
for the manifest contract, data-source plan, evaluation metrics, and teacher to
student optimization route.

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
  --object-query block \
  --target target_area_3
```

Add `--execute` after checking the scene and bridge readiness. The optional
RGB-D path captures one Gazebo frame, runs `vision.open_vocab_detect`, then
executes the parallel vision ActionList:

```bash
PYTHONPATH=src .venv312/bin/python scripts/linux/run_gazebo_vision_actionlist_sim.py \
  --object-query "red block" \
  --target target_area_3 \
  --execute
```

The recovery DecisionTree can be invoked from Python or Agent APIs as
`industrial.recovery_pick_place_tree`. It runs the same pick/place path, records
`last_failure` after failed nodes, classifies the failure, plans a local recovery,
and rejoins the flow through bounded re-detect, re-pick, re-place, gripper-open,
or bridge-reset branches.

For a video-ready failure-recovery demo, inject a wrong-bin placement in Gazebo:

```bash
PYTHONPATH=src .venv312/bin/python scripts/linux/run_gazebo_recovery_demo.py \
  --failure wrong-bin \
  --object-query block \
  --target target_area_3 \
  --wrong-target target_area_2 \
  --execute \
  --json-out logs/tasks/recovery_wrong_bin_demo.json
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
