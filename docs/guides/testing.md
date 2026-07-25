# Testing Guide

The default suite uses mocks and fixtures; it does not require ROS 2, a robot,
microphone access, or local model weights.

## Run the suite

```powershell
$env:PYTHONPATH = "$(Get-Location)\src"
python -m unittest discover -s tests -p 'test_*.py'
```

The suite includes unit and end-to-end tests for config loading, planner
validation, tool/skill runtimes, ActionLists, DecisionTrees, audio fakes,
contract validation, robot planning/control adapters, and open-vocabulary vision
error handling. It also covers failure classification and recovery planning
tools. It does not start ROS 2 or Gazebo.

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

## Open-vocabulary vision tests

The focused vision suite uses injected detector and mask-refiner fakes. It
checks the stable Tool contract, SAM 2 box fallback, mask centroid and depth
sampling, camera projection, and base-frame transformation without downloading
weights:

```powershell
$env:PYTHONPATH = "$(Get-Location)\src"
pytest -q tests\unit\test_vision_open_vocab.py
```

Real Grounding DINO and SAM 2 inference is a separate environment acceptance
step. Follow `docs/guides/vision_open_vocab_cn.md`; do not treat the mock unit
tests as evidence of model accuracy or robot-coordinate correctness.

## Failure detection and recovery tests

```powershell
$env:PYTHONPATH = "$(Get-Location)\src"
python -m unittest tests.unit.test_failure_recovery
```

This suite checks typed failure classification, deterministic recovery-plan
selection, `vision.verify_object_lifted`, `vision.verify_object_in_bin`, and the
DecisionTree `last_failure` context used by recovery branches.

The full industrial recovery tree has focused tests for nominal execution,
grasp-failure recovery, place-plan recovery, and wrong-bin recovery:

```powershell
$env:PYTHONPATH = "$(Get-Location)\src"
python -m unittest tests.unit.test_industrial_recovery_tree
```

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

## Industrial ActionList dry run

On a machine with the Agent Python environment:

```bash
PYTHONPATH=src .venv312/bin/python scripts/linux/run_industrial_actionlist_sim.py \
  --planner static \
  --object-query roller \
  --target bin_cell_3
```

Without `--execute`, the script swaps the robot backend to fake and validates
the workflow wiring without moving Gazebo.

## ROS 2 simulation acceptance

On Ubuntu with ROS 2 Humble:

```bash
bash scripts/linux/run_rm65_b_sim.sh
```

Check the arm trajectory controller, effort gripper controller, gripper Action,
MoveIt planning, HTTP bridge readiness, and object contact manually:

```bash
curl http://127.0.0.1:8765/health
curl http://127.0.0.1:8765/ready
```

Then use the targeted scripts as needed:

```bash
PYTHONPATH=src .venv312/bin/python scripts/linux/test_gazebo_pick_pipeline.py --diagnose-only
PYTHONPATH=src .venv312/bin/python scripts/linux/run_industrial_actionlist_sim.py --planner static --object-query roller --target bin_cell_3 --execute
PYTHONPATH=src .venv312/bin/python scripts/linux/run_gazebo_vision_actionlist_sim.py --object-query "red roller" --target bin_cell_3 --execute
```

The repository currently has no automated ROS 2, Gazebo, or grasp-stability test
cases in the default suite.

ROS 2, Gazebo, hardware, and local-model acceptance checks are manual or
environment-specific and are not part of the default Python test suite.
