# SensorAgent

SensorAgent is the agent-side orchestration repository for embodied industrial
tasks. It focuses on task understanding, skill/tool orchestration, workflow
execution, local VAD/ASR command intake, structured logging, RM65-B simulation
development, and a safety-gated physical-hardware adapter.

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
- Reproducible local RM65-B + Robotiq 2F-85 Gazebo and MoveIt 2 integration.
- Safety-gated HTTP integration with an externally installed RM65 + OmniPicker
  physical-hardware ROS stack.

SensorAgent is not responsible for:

- Isaac Sim scene deployment.
- Vendor driver, firmware, or low-level controller ownership.
- Physical-cell safety certification, emergency-stop integration, or operator
  procedures.
- Camera calibration and physical-hardware acceptance evidence.

## System Architecture

SensorAgent is organized as a competition-oriented industrial agent with three
runtime layers: perception, decision, and execution. Configuration, contracts,
state, logging, and tests support all three layers.

```mermaid
flowchart LR
  user["User / voice / CLI"] --> perception["Perception layer"]
  perception --> decision["Decision layer"]
  decision --> execution["Execution layer"]
  execution --> sim["ROS 2 / MoveIt / Gazebo"]
  execution --> hw["Safety-gated physical ROS bridge"]

  cfg["configs/"] --> perception
  cfg --> decision
  cfg --> execution
  contracts["contracts/"] --> decision
  contracts --> execution
  logs["logs / traces"] <-- decision
  logs <-- execution
```

### Perception layer

The perception layer converts operator commands and scene observations into
structured task inputs. Speech input uses local VAD and SenseVoice ASR. Vision
uses the competition-facing `vision.dual_branch_detect` Tool: known industrial
classes route to YOLO11-seg for stable fixed-class instance segmentation, while
unknown or long-tail language references route to industrial GroundingDINO +
SAM2 for open-vocabulary detection and mask refinement.

Simple industrial references such as "左边的螺母" are not delegated to an
unbounded LLM. They are handled by deterministic ontology and spatial grounding:
aliases normalize the object class, the dual-branch detector provides
masks/boxes, and the spatial selector chooses among existing candidates by image
or base-frame geometry.

Gazebo RGB-D capture is isolated in `vision.capture_frame`, which shells out to
ROS Python and writes image, depth, camera-info, and transform manifests under
`logs/vision/`. Physical capture uses the hardware RGB + point-cloud script and
keeps robot motion separate from sensing.

### Decision layer

The decision layer turns text, grounded task intent, and perception output into
bounded robot actions. It owns task lifecycle, workflow selection, world-state
updates, failure classification, and recovery policy. LLM planning is constrained
to approved workflows; it cannot directly issue arbitrary low-level robot
commands.

ActionLists provide deterministic action fragments. DecisionTrees add condition
checks, retries, local recovery, and structured failure evidence. The competition
sorting path also maintains task-local object/bin state so the agent can reject
ambiguous commands, avoid occupied bins, and record recovery history.

### Execution layer

The execution layer invokes Skills and Tools, translates backend-neutral robot
commands into simulation or hardware requests, and returns structured results to
the decision layer. The Python agent process does not import ROS 2 directly.
Robot execution crosses an HTTP boundary into either the Gazebo/MoveIt bridge on
port `8765` or the safety-gated hardware bridge on port `8766`.

The physical bridge is an adapter, not a vendor driver or safety-certified cell
runtime. It binds to localhost, keeps physical motion disabled by default, and
does not replace emergency-stop procedures, calibration, or operator safety
checks.

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
| RM65-B + Robotiq Gazebo and MoveIt stack | Implemented and manually exercised on Ubuntu |
| Backend-neutral robot Tools and pick/place Skills | Implemented |
| SensorAgent-to-Gazebo/MoveIt HTTP bridge | Implemented and used by Gazebo test scripts; automated ROS acceptance is not in the default suite |
| Industrial config-detect pick/place ActionLists | Implemented for the current tabletop world |
| Gazebo RGB-D dual-branch vision ActionList | Implemented as the competition perception path |
| Gazebo RGB-D frame capture Tool (`vision.capture_frame`) | Implemented; requires a ROS 2 Python interpreter on Ubuntu |
| Dual-branch competition vision (`vision.dual_branch_detect`) | Implemented as a routing entry point: known industrial classes prefer YOLO11-seg, while open/long-tail references use the GroundingDINO + SAM2 branch |
| Strict Grounding DINO + SAM 2 Tool (`vision.grounded_sam2`) | Implemented as the open-vocabulary branch with mandatory SAM2 mask refinement |
| YOLOE and YOLO11-seg Tools | Implemented as optional alternatives; `vision.yolo11_seg_detect` is the fixed/many-class industrial segmentation branch and requires native masks |
| Offline vision dataset evaluation harness | Implemented; datasets and weights stay local |
| Failure classification and recovery DecisionTree | Implemented for the industrial pick/place flow, including a live-perception mode; Gazebo acceptance pending |
| Unified competition world state | Task-local object/bin/task state implemented for live perception and hardware sessions; durable long-horizon fusion remains pending |
| Physical RM65 + OmniPicker bridge | Implemented through externally installed ROS packages on `127.0.0.1:8766`; motion is disabled by default, and `scripts/linux/run_hardware_agent.sh --enable-motion` enables the real hardware pick-place path after operator safety checks |
| Hardware RGB-D capture, pick planning, and bin placement | Implemented; uses synchronized RGB/point cloud capture, dual-branch visual grounding, configured object pick profiles, recorded bin-cell poses, and bounded workspace checks |
| Experimental generic mask/point-cloud planner | Implemented as `robot.plan_mask_pointcloud_pick`; not enabled in shipped configs or any ActionList |
| Industrial Gazebo tabletop scenario | Initial environment implemented under the ROS 2 bringup package |
| Multi-instance competition sorting session | Implemented with text/real-voice input, semantic grounding, ambiguity rejection, Gazebo RGB-D dual-branch perception, state tracking, and bounded recovery |

The reusable robot control surface now includes state, joint motion, pose motion,
linear motion, stop, gripper control, deterministic pick/place planning, named
place-target resolution, and `robot.pick` / `robot.place` / verification Skills.
`configs/competition_eval.yaml` selects the local fake backend for offline
evaluation, while `configs/competition_sim.yaml` selects the simulation HTTP
bridge on port `8765`.
`configs/competition_hardware.yaml` selects the physical hardware bridge on port
`8766`; it supports capture, dual-branch visual grounding, profile selection,
physical pick, grasp verification, and placement into recorded bin-cell targets through
`hardware.pick_place_actionlist`. Physical motion remains opt-in and must be
started with `scripts/linux/run_hardware_agent.sh --enable-motion`.
See the [environment setup guide](docs/guides/environment-setup.md) before
enabling any physical motion.

## Quick Start

Python 3.10 or newer is required for the Agent package.

```powershell
python -m pip install -r requirements.txt
python -m pip install onnxruntime pytest           # Silero VAD and the pytest-based tests
```

Runtime configuration is resolved in this order: an explicit `--config` path,
`SENSORAGENT_CONFIG`, `SENSORAGENT_ENV` mapped to `configs/<env>.yaml`, then
`configs/competition_sim.yaml`. Copy `.env.example` to an ignored `.env` for LLM
credentials and logging overrides. Other recognized variables are
`SENSORAGENT_PYTHON` (agent launcher interpreter override),
`SENSORAGENT_ROS_PYTHON` (ROS 2 interpreter used by RGB-D capture),
`SENSORAGENT_GROUNDING_DINO_MODEL`, and `SENSORAGENT_SAM2_WEIGHTS`.

Run the default offline test suite:

```powershell
$env:PYTHONPATH = "$(Get-Location)\src"
python -m pytest -q tests\unit
```

See the [environment setup guide](docs/guides/environment-setup.md) for runtime
dependencies and validation commands.

## Reproduce the Industrial Agent

Evaluators should start from the single reproduction guide:

- [Industrial agent reproduction guide](docs/guides/competition-agent.md)

The two submission entry points are:

```bash
bash scripts/linux/run_sim_agent.sh
bash scripts/linux/run_hardware_agent.sh
```

Competition launchers enable constrained LLM semantic grounding by default in
`assist` mode. The LLM may refine rule-ready intents inside a strict whitelist,
for example by adding a spatial selector or asking for clarification. Use
`--llm-grounding-mode fallback` if the LLM should run only after deterministic
grounding fails, or `--no-llm-grounding` for offline/rules-only execution. In
all modes the LLM may only output allowed object classes, targets, actions,
quantities, and spatial selectors; it cannot generate coordinates or robot
actions.

## Repository Layout

```text
sensoragent/
├── configs/                 # Project-level configuration files
├── contracts/               # Language-neutral cross-module JSON contracts
├── docs/                    # Submission reproduction and environment guides
├── logs/                    # Ignored task logs, traces, audio, and captures
├── models/                  # Ignored local ASR and vision weights
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
| `run-task` | Run a natural-language task through the static or LLM planner |
| `listen-task` | Record one utterance, transcribe it, and plan from the transcript |
| `vision-detect` | Run a selected vision Tool, including `vision.dual_branch_detect`, on one RGB(-D) image and print the Tool result |
| `run-actionlist` | Directly run a registered ActionList, including configured hardware experiments |

Gazebo workflows are driven by `scripts/linux/` runners instead of CLI
subcommands. Evaluator-facing commands are documented in the reproduction guide.

## Documentation

The submission branch keeps only two operational guides:

- [Industrial agent reproduction guide](docs/guides/competition-agent.md)
- [Environment setup guide](docs/guides/environment-setup.md)

## Vision Model Training and Evaluation

The competition-facing path is `vision.dual_branch_detect`. It routes common
industrial classes such as bolts, nuts, rollers, gears, flanges, and wrenches to
the fixed-class YOLO11-seg branch, then falls back to the GroundingDINO + SAM2
branch when needed. Queries outside the fixed industrial ontology start from
GroundingDINO to preserve open-vocabulary behavior. Validate a portable dataset
manifest before running a long evaluation:

```powershell
python scripts\vision_eval.py validate `
  --manifest configs\vision_dataset.example.jsonl `
  --allow-missing-files
```

Run a labeled local dataset with one persistent model instance:

```powershell
python scripts\vision_eval.py run `
  --manifest data\vision\competition_test.jsonl `
  --config configs\vision_dual_branch.example.yaml `
  --tool vision.dual_branch_detect `
  --output-dir runs\vision\competition_test `
  --device 0 `
  --require-masks `
  --save-overlays
```

The runner saves per-sample JSONL, aggregate metrics, Tool logs, and optional
overlays. Dataset images, model weights, caches, and `runs/` outputs remain local.

Reviewed COCO segmentation exports can be converted without adding a runtime
dependency on `pycocotools`:

```powershell
python scripts\vision_coco_segmentation_to_eval.py `
  --source-root data\vision\raw_coco `
  --output-root data\vision\competition_eval `
  --sample-prefix industrial_part `
  --query "industrial part" `
  --category-name "industrial-part" `
  --dataset-name "SensorAgent competition dataset" `
  --source-license "internal-reviewed"
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
boxes. The fixed industrial-class branch uses YOLO11-seg checkpoints through
`vision.yolo11_seg_detect`; the competition-facing router is
`vision.dual_branch_detect`.

The templates are not checked-in training data. Checkpoints, datasets, caches,
and run outputs stay outside Git; the repository keeps only code, contracts,
configuration templates, and reproducible evaluation scripts.
The [environment setup guide](docs/guides/environment-setup.md) lists the
submission configs, local model layout, and validation commands.
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

An optional shell alias can reduce this to `sensoragent-sim`.

To start Gazebo without MoveIt and RViz:

```bash
bash scripts/linux/run_rm65_b_sim.sh start_moveit:=false
```

The combined model, arm motion, and gripper opening/closing have been manually
exercised on Ubuntu. Repeatable object-contact and grasp-stability acceptance
remain before this simulation should be used for reinforcement learning.

## Competition Agent Runtime

The submission branch exposes the industrial sorting agent through one
persistent competition session script. In simulation, start Gazebo, MoveIt, and
the HTTP bridge:

```bash
bash scripts/linux/run_rm65_b_sim.sh
curl http://127.0.0.1:8765/ready
```

Then run the persistent agent loop:

```bash
PYTHONPATH=src python3 scripts/linux/run_competition_sorting_session.py \
  --mode text \
  --execute
```

For voice input, switch the mode after local ASR/VAD assets are installed:

```bash
PYTHONPATH=src python3 scripts/linux/run_competition_sorting_session.py \
  --mode voice \
  --execute
```

The loop keeps a session-level world state, accepts multiple commands, rejects
ambiguous references, tracks occupied bin cells, records execution history, and
performs bounded recovery before waiting for the next command.

The Python Agent package supports Python 3.10+, so it can run on Ubuntu 22.04
alongside ROS 2 Humble while keeping ROS and the agent connected through HTTP.
