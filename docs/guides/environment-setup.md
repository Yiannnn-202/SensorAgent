# Environment Setup Guide

This guide contains the setup information needed to reproduce the submission
agent. Use it together with the [industrial agent reproduction guide](competition-agent.md).

## Python runtime

SensorAgent uses Python 3.10 or newer for the agent process.

```powershell
python -m pip install -r requirements.txt
python -m pip install onnxruntime pytest
$env:PYTHONPATH = "$(Get-Location)\src"
python -m pytest -q tests
```

Runtime config resolution order:

```text
--config
SENSORAGENT_CONFIG
SENSORAGENT_ENV -> configs/<env>.yaml
configs/competition_sim.yaml
```

## Local credentials and model paths

Copy `.env.example` to `.env` only for local credentials. Never commit real
keys, model weights, datasets, captured frames, or logs.

Relevant environment variables:

```text
SENSORAGENT_LLM_API_KEY
SENSORAGENT_LLM_MODEL
SENSORAGENT_LLM_BASE_URL
SENSORAGENT_PYTHON
SENSORAGENT_ROS_PYTHON
SENSORAGENT_ROS_SETUP
SENSORAGENT_ROS_WS_SETUP
SENSORAGENT_GROUNDING_DINO_MODEL
SENSORAGENT_SAM2_WEIGHTS
```

Expected local model layout:

```text
models/
├── asr/
│   ├── sense-voice/
│   │   ├── model.int8.onnx
│   │   └── tokens.txt
│   └── vad/
│       └── silero_vad.onnx
└── vision/
    ├── yolo11-seg/industrial-best.pt
    ├── grounding-dino/industrial-open-vocab/
    └── sam2_t.pt
```

## Simulation environment

Use Ubuntu 22.04 with ROS 2 Humble for Gazebo and MoveIt. The Python agent stays
outside ROS and talks to the bridge over HTTP.

Prepare the ROS workspace once:

```bash
cd ~/SensorAgent
bash scripts/linux/prepare_rm65_b_sim.sh
```

Start the simulation agent:

```bash
bash scripts/linux/run_sim_agent.sh
```

Useful options:

```bash
bash scripts/linux/run_sim_agent.sh --mode voice
bash scripts/linux/run_sim_agent.sh --dry-run
bash scripts/linux/run_sim_agent.sh --no-start-stack
bash scripts/linux/run_sim_agent.sh --llm-grounding-mode fallback
bash scripts/linux/run_sim_agent.sh --no-llm-grounding
```

## Hardware environment

The hardware path uses `sensoragent_hardware_bridge` on `127.0.0.1:8766`. It is
an adapter, not a safety-certified driver. Physical motion is disabled unless
the launcher receives `--enable-motion`.

The required Island-Arm ROS 2 packages are integrated under
`ros2_ws/src/island_arm`. Prepare the complete hardware workspace once; no
separate Island-Arm checkout or install overlay is required:

```bash
cd ~/SensorAgent
bash scripts/linux/prepare_hardware_stack.sh
```

`scripts/linux/start_hardware_stack.sh` then sources ROS 2 and this repository's
built ROS workspace. Override these paths only when they differ from the
defaults:

```bash
export SENSORAGENT_ROS_SETUP=/opt/ros/humble/setup.bash
export SENSORAGENT_ROS_WS_SETUP=$PWD/ros2_ws/install/local_setup.bash
```

Before enabling motion, verify:

```text
emergency stop
workspace clearance
camera calibration
TCP and gripper calibration
hardware ROS services
operator supervision
```

Start in safe dry-run mode:

```bash
bash scripts/linux/run_hardware_agent.sh
```

Enable physical motion only after local safety checks:

```bash
bash scripts/linux/run_hardware_agent.sh --enable-motion
```

Useful options:

```bash
bash scripts/linux/run_hardware_agent.sh --mode voice
bash scripts/linux/run_hardware_agent.sh --no-start-stack
bash scripts/linux/run_hardware_agent.sh --llm-grounding-mode fallback
bash scripts/linux/run_hardware_agent.sh --no-llm-grounding
```

## Main configs

```text
configs/competition_sim.yaml       # evaluator simulation entry
configs/competition_hardware.yaml  # evaluator hardware entry
configs/competition_eval.yaml      # offline fake-backend evaluation/tests
configs/audio_local.yaml           # local VAD/ASR settings
```

Vision-only configs:

```text
configs/vision_dual_branch.example.yaml
configs/vision_grounded_sam2.yaml
configs/vision_grounding_dino.yaml
configs/vision_yolo11_seg.example.yaml
configs/vision_dataset.example.jsonl
configs/vision_train_grounding_dino.example.yaml
configs/vision_train_grounding_dino.example.jsonl
```

The open branch uses GroundingDINO + SAM2. `SENSORAGENT_GROUNDING_DINO_MODEL`
may override the configured GroundingDINO path, and `SENSORAGENT_SAM2_WEIGHTS`
may override the SAM2 path.

The current submission-branch test baseline is **389 passed, 49 subtests
passed**.
