# SensorAgent

SensorAgent is the agent-side orchestration repository for embodied tasks. It
focuses on task understanding, skill/tool orchestration, workflow execution,
local VAD/ASR/TTS, structured logging, RM65-B simulation development, and a
safety-gated physical-hardware adapter.

It does **not** own robot firmware, vendor drivers, or physical-cell safety
certification. The included ROS 2 workspace contains both a local Gazebo/MoveIt
development stack and an adapter to externally installed physical-hardware ROS
packages. Physical motion remains opt-in and is disabled by default.

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
- Safety-gated HTTP integration with an externally installed RM65 + OmniPicker
  physical-hardware ROS stack.

SensorAgent is not responsible for:

- Isaac Sim scene deployment.
- Vendor driver, firmware, or low-level controller ownership.
- Physical-cell safety certification, emergency-stop integration, or operator
  procedures.
- Camera calibration and physical-hardware acceptance evidence.

## Current Status

As of 2026-08-17, the repository is beyond framework scaffolding. It has
simulation and physical-hardware execution adapters, but competition acceptance
is still limited by repeatable Gazebo testing, measured vision quality,
live-perception world-state fusion, and physical-cell validation.

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
| Strict Grounding DINO + SAM 2 Tool (`vision.grounded_sam2`) | Implemented with a pretrained baseline and a local single-class `red_block_v0` fine-tuning run; multi-class and industrial acceptance remain pending |
| Offline vision dataset evaluation harness | Implemented; datasets and weights stay local |
| Failure classification and recovery DecisionTree | Implemented for the industrial pick/place flow, including a live-perception mode; Gazebo acceptance pending |
| Unified competition world state | Task-local object/bin/task state implemented for the oracle multi-instance session; durable live-perception fusion remains pending |
| Physical RM65 + OmniPicker bridge | Implemented through externally installed ROS packages on `127.0.0.1:8766`; motion is disabled by default and only single-object pick/verify is wired |
| Hardware RGB-D capture and short-bolt planning | Implemented; uses synchronized RGB/point cloud capture, Grounded SAM2, a configured profile, and bounded workspace checks |
| Experimental generic mask/point-cloud planner | Implemented as `robot.plan_mask_pointcloud_pick`; not enabled in shipped configs or any ActionList |
| Batch simulation evaluation and repeatable scene reset | Not implemented |
| HTTP/WebSocket/MCP service entry points | Not implemented; only the CLI exists |
| Industrial Gazebo tabletop scenario | Initial environment implemented under the ROS 2 bringup package |
| Multi-instance competition sorting session | Implemented with text/real-voice input, semantic grounding, ambiguity rejection, oracle instance selection, state tracking, and bounded recovery |
| Gymnasium RL environment | Not implemented |

The reusable robot control surface now includes state, joint motion, pose motion,
linear motion, stop, gripper control, deterministic pick/place planning, named
place-target resolution, and `robot.pick` / `robot.place` / verification Skills.
`configs/robot_mock.yaml` selects the deterministic fake backend, while
`configs/robot_sim.yaml` selects the simulation HTTP bridge on port `8765`.
`configs/robot_hardware_sensoragent_v1i_baseline.yaml` selects the physical
hardware bridge on port `8766`; it supports capture, detect, profile selection,
pick, and grasp verification, but not physical place/sort/recovery workflows.
See the [hardware guide](docs/guides/hardware/physical-rm65-omnipicker.md)
before enabling any physical motion.

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
python -m pytest -q tests\unit
```

See the [testing guide](docs/guides/operations/testing.md) for the suite's scope and its
current validation scope.

## Repository Layout

```text
sensoragent/
├── configs/                 # Project-level configuration files
├── contracts/               # Language-neutral cross-module JSON contracts
├── docs/                    # Architecture, team documents, and guides
├── logs/                    # Ignored task logs, traces, audio, and captures
├── models/                  # Ignored local ASR, TTS, and vision weights
├── scripts/                 # Vision evaluation and Linux simulation/hardware runners
├── ros2_ws/                 # ROS 2 simulation and physical-hardware adapter workspace
│   └── src/
│       ├── rm_description/                  # Locally imported RM65-B model
│       ├── rm_gazebo/                       # Locally imported arm-only Gazebo stack
│       ├── rm_65_config/                    # Locally imported arm-only MoveIt config
│       ├── robotiq_description/             # Vendored Robotiq 2F-85 model
│       ├── sensoragent_rm65_b_bringup/      # Combined arm/gripper stack, worlds, models
│       ├── sensoragent_robot_bridge/        # HTTP-to-ROS 2 simulation bridge
│       ├── sensoragent_hardware_bridge/     # Safety-gated HTTP-to-physical ROS bridge
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
| `run-actionlist` | Directly run a registered ActionList, including configured hardware experiments |

Gazebo workflows are driven by `scripts/linux/` runners instead of CLI
subcommands. See the [testing guide](docs/guides/operations/testing.md) for the full list.

## Documentation

Start from the documentation index:

- [docs/README.md](docs/README.md)

Key SensorAgent documents:

- [Architecture (single source)](architecture.md)
- [Competition technical plan](docs/planning/competition-plan.md)
- [Competition schedule and progress](docs/planning/schedule.md)
- [Development backlog](TODO.md)
- [Documentation index](docs/README.md)
- [Terminal progress logging convention](TERMINAL_PROGRESS_LOGGING.md)
- [Testing guide](docs/guides/operations/testing.md)
- [Audio guide](docs/guides/audio/local-audio.md)
- [RM65-B Gazebo quickstart](docs/guides/simulation/rm65b-quickstart.md)
- [Simulation robot HTTP bridge](docs/guides/simulation/robot-bridge.md)
- [Physical RM65 + OmniPicker guide](docs/guides/hardware/physical-rm65-omnipicker.md)
- [Industrial intent to ActionList guide](docs/guides/workflows/intent-to-actionlist.md)
- [Failure detection and recovery guide](docs/guides/workflows/failure-recovery.md)
- [Open-vocabulary vision guide](docs/guides/vision/open-vocabulary.md)
- [Grounded SAM 2 strict Tool and red-block evaluation](docs/guides/vision/grounded-sam2-tool-cn.md)
- [Team conventions](docs/team/convention.md)

## Vision Model Training and Evaluation

The generic open-vocabulary path uses `vision.open_vocab_detect` for the
temporary YOLOE baseline and configurable experimental backends. The strict
`vision.grounded_sam2` Tool fixes the detector to Grounding DINO, always invokes
SAM 2, and fails instead of silently falling back to a detector box when mask
generation fails. Validate a portable dataset manifest before running a long
evaluation:

```powershell
python scripts\vision_eval.py validate `
  --manifest configs\vision_dataset.example.jsonl `
  --allow-missing-files
```

Run a labeled local dataset with one persistent model instance:

```powershell
python scripts\vision_eval.py run `
  --manifest data\vision\competition_test.jsonl `
  --config configs\vision_grounded_sam2.yaml `
  --tool vision.grounded_sam2 `
  --output-dir runs\vision\competition_test `
  --device 0 `
  --require-masks `
  --save-overlays
```

The runner saves per-sample JSONL, aggregate metrics, Tool logs, and optional
overlays. Dataset images, model weights, caches, and `runs/` outputs remain local.

Roboflow-style COCO segmentation exports can be converted without adding a
runtime dependency on `pycocotools`:

```powershell
python scripts\vision_coco_segmentation_to_eval.py `
  --source-root "..\red block.v2i.coco-segmentation" `
  --output-root data\vision\team\red_block_v2 `
  --sample-prefix red_block_v2 `
  --query "red block" `
  --category-name "red-block" `
  --dataset-name "Roboflow red block v2" `
  --source-url "https://universe.roboflow.com/yiannnn202s-workspace/red-block" `
  --source-license "CC BY 4.0"
```

The current first training target is Grounding DINO itself. Its JSONL manifest
keeps text class names, absolute `bbox_xyxy` targets, provenance, and scene-level
splits. Validate the complete dataset before allocating GPU time:

```powershell
python scripts\vision_train_grounding_dino.py `
  --config configs\vision_train_grounding_dino.example.yaml `
  --manifest data\vision\competition_train.jsonl `
  --dry-run
```

After the prompt order, scene-level splits, and detection boxes are reviewed,
start direct full-parameter fine-tuning with:

```powershell
python scripts\vision_train_grounding_dino.py `
  --config configs\vision_train_grounding_dino.example.yaml `
  --manifest data\vision\competition_train.jsonl `
  --device cuda:0
```

`configs/vision_train_grounding_dino.example.yaml` records the proposed prompt
order and reproducible training parameters. `class_labels` are indexes into
that exact text list; they are not an independent YOLO class map. SAM 2 masks
remain useful annotations, but Grounding DINO is optimized on text-grounded
boxes. YOLO11n-seg and `scripts/vision_train.py` remain historical experiment
support and are outside the current 2026-08-10 delivery path.

The templates are not checked-in training data. A local single-class
`red_block_v0` run has been completed for training and Tool-chain validation;
its checkpoint, dataset, caches, and run outputs stay outside Git. See the
[red_block_v0 training handoff](docs/guides/vision/grounding-dino-red-block-v0-cn.md)
for the recorded configuration, hashes, metrics, and remaining work.
See the [open-vocabulary vision guide](docs/guides/vision/open-vocabulary.md)
for the manifest contract, data-source plan, evaluation metrics, and current
Grounding DINO + SAM2 delivery route.
The [strict Tool guide](docs/guides/vision/grounded-sam2-tool-cn.md) documents
the fixed Tool contract, COCO conversion workflow, red-block data audit, and
the measured 2026-08-01 pretrained baseline.
The [SAM3 assessment](docs/guides/vision/sam3-assessment.md) records why SAM3
is a later same-split comparison instead of a drop-in replacement for the current
Grounding DINO + SAM2 delivery.

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
[full Ubuntu guide](docs/guides/simulation/rm65b-quickstart.md).

To start Gazebo without MoveIt and RViz:

```bash
bash scripts/linux/run_rm65_b_sim.sh start_moveit:=false
```

The combined model, arm motion, and gripper opening/closing have been manually
exercised on Ubuntu. Repeatable object-contact and grasp-stability acceptance
remain before this simulation should be used for reinforcement learning. See the
[full Ubuntu guide](docs/guides/simulation/rm65b-quickstart.md).

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
the [audio guide](docs/guides/audio/local-audio.md), configure the LLM credentials in an
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

1. Establish a clean offline test baseline and automated ROS 2/Gazebo acceptance.
2. Add repeatable scene reset, batch execution, and report-ready metrics.
3. Freeze the competition object classes, validation data, camera contract, and
   physical-robot access plan.
4. Complete measured RGB-D perception and recovery acceptance on the minimum
   competition scene.
5. Define the unified world-state contract needed by perception, planning,
   execution, and replay.

Service entry points, broader object coverage, and reinforcement learning remain
outside the critical path until the repeatable simulation loop passes its first
stage gate.

The Python Agent package currently declares Python 3.12, while Ubuntu 22.04 and
ROS 2 Humble normally use Python 3.10. The implemented design keeps them in
separate processes and connects them through HTTP.
