# Testing Guide

The default suite uses mocks and fixtures; it does not require ROS 2, a robot,
microphone access, or local model weights.

## Run the suite

```powershell
$env:PYTHONPATH = "$(Get-Location)\src"
python -m unittest discover -s tests -p 'test_*.py'
```

## Mock task pipeline

```powershell
$env:PYTHONPATH = "$(Get-Location)\src"
python -m sensoragent.services.cli.main mock-pick-place --config configs\mock.yaml --object-query "silver roller" --target "third bin cell"
```

The command should exit successfully, print an `AgentResponse`, execute detection
before pick and pick before place, and write a JSONL task log under `logs/tasks/`.

The planner lifecycle can be exercised with:

```powershell
python -m sensoragent.services.cli.main run-task "put the silver roller into the third bin cell" --config configs\mock.yaml --planner static --object-query "silver roller" --target "third bin cell"
```

Use `--planner llm` only after configuring the OpenAI-compatible endpoint and API
key in `.env`.

## Audio smoke test

```powershell
python -m sensoragent.services.cli.main listen-task --config configs\audio_mock.yaml --planner static --duration 1 --object-query "silver roller" --target "third bin cell"
```

This copies the committed audio fixture through the fake recorder and returns a
deterministic transcript.

The suite also covers fake VAD segmentation, realtime-VAD result handling,
audio Skills, and the voice acknowledgement ActionList. Tests that instantiate
the actual Silero ONNX recorder skip when `onnxruntime` is unavailable.

## Local audio acceptance

Local microphone, model, and sound-device behavior is environment-specific:

```bash
PYTHONPATH=src python -m sensoragent.services.cli.main \
  listen-task \
  --config configs/audio_local.yaml \
  --planner llm \
  --duration 15
```

Confirm that speech starts recording, silence ends the utterance before the
maximum duration, SenseVoice returns the expected text, and a JSONL task log is
written.

## ROS 2 simulation acceptance

On Ubuntu with ROS 2 Humble:

```bash
bash scripts/linux/run_rm65_b_sim.sh
```

Check the arm trajectory controller, effort gripper controller, gripper Action,
MoveIt planning, and object contact manually. The repository currently has no
automated ROS 2, Gazebo, or grasp-stability test cases.

ROS 2, Gazebo, hardware, and local-model acceptance checks are manual or
environment-specific and are not part of the default Python test suite.
