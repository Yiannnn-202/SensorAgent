# Testing Guide

The default suite uses mocks and fixtures; it does not require ROS 2, a robot,
microphone access, or local model weights. Two known exceptions are listed under
[Known issues](#known-issues).

## Dependencies

```powershell
python -m pip install -r requirements.txt
python -m pip install pytest
```

`pytest` is not declared in `requirements.txt` or `pyproject.toml`, but
`tests/unit/test_vision_evaluation.py` imports it, so `unittest discover` reports
a collection error without it. Tests that need `onnxruntime`, model weights, or a
microphone skip themselves when those assets are missing.

## Run the suite

```powershell
$env:PYTHONPATH = "$(Get-Location)\src"
python -m unittest discover -s tests -p 'test_*.py'
```

The suite currently collects 233 tests covering config loading, planner
validation, tool/skill runtimes, ActionLists, DecisionTrees, audio fakes,
contract validation, robot planning/control adapters, open-vocabulary vision
error handling, and the vision evaluation harness. It also covers failure
classification and recovery planning tools. It does not start ROS 2 or Gazebo.

## Known issues

| Test | Symptom | Cause |
| --- | --- | --- |
| `tests/unit/test_vision_evaluation.py` | Import error during discovery | `pytest` is not installed or not declared as a dependency |
| `tests/unit/test_gazebo_recovery_demo_script.py::GazeboRecoveryDemoScriptTest::test_wrong_table_demo_runs_without_gazebo` | `ROBOT_BRIDGE_UNAVAILABLE` on `127.0.0.1:8765` | The case runs the demo with `--execute`, so it uses the `http` robot backend from `configs/robot_sim.yaml` and needs a live bridge despite its name |

Both are tracked in `TODO.md`. Treat a run with only these two failures as a
clean offline baseline until they are fixed.

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

## Single-image and dataset vision checks

With `requirements-vision.txt` installed and local weights present, one image can
be checked through the same Tool the workflows use:

```powershell
$env:PYTHONPATH = "$(Get-Location)\src"
python -m sensoragent.services.cli.main vision-detect --config configs\vision_grounding_dino.yaml --image data\vision\sample.png --query "red block"
```

Dataset-level evaluation uses the offline harness:

```powershell
python scripts\vision_eval.py validate --manifest configs\vision_dataset.example.jsonl --allow-missing-files
python scripts\vision_eval.py run --manifest data\vision\competition_test.jsonl --config configs\vision_grounding_dino.yaml --output-dir runs\vision\competition_test
```

Manifests, images, weights, and `runs/` outputs stay local and untracked.

The primary Grounding DINO training preflight checks the ordered text classes,
required splits, scene leakage, absolute `bbox_xyxy` targets, image paths, and
data provenance. It does not import or download the model when `--dry-run` is
used:

```powershell
python scripts\vision_train_grounding_dino.py --config configs\vision_train_grounding_dino.example.yaml --manifest data\vision\competition_train.jsonl --dry-run
pytest -q tests\unit\test_vision_train_grounding_dino.py
```

The verified training path uses `batch_size: 1` and gradient accumulation so
each target class index maps to the exact candidate-label prompt order. Record
AMP state, effective batch size, model ID, checkpoint hash, manifest hash, and
dataset hash in every comparison. The older `scripts/vision_train.py` suite is
retained for the optional YOLO11n-seg student baseline. If a network blocks
Hugging Face, pass a local `from_pretrained` snapshot directory with `--model`;
do not hard-code a personal cache path in a committed config.

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

The Gazebo recovery demo runner also has a no-Gazebo smoke test:

```powershell
$env:PYTHONPATH = "$(Get-Location)\src"
python -m unittest tests.unit.test_gazebo_recovery_demo_script
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
  --object-query block \
  --target target_area_3
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
PYTHONPATH=src .venv312/bin/python scripts/linux/run_industrial_actionlist_sim.py --planner static --object-query block --target target_area_3 --execute
PYTHONPATH=src .venv312/bin/python scripts/linux/run_gazebo_vision_actionlist_sim.py --object-query "red block" --target target_area_3 --execute
PYTHONPATH=src .venv312/bin/python scripts/linux/run_gazebo_recovery_demo.py --failure wrong-bin --object-query block --target target_area_3 --wrong-target target_area_2 --execute
```

The repository currently has no automated ROS 2, Gazebo, or grasp-stability test
cases in the default suite.

ROS 2, Gazebo, hardware, and local-model acceptance checks are manual or
environment-specific and are not part of the default Python test suite.
