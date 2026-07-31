# TODO

This file tracks SensorAgent development progress by framework maturity. The current priority is to build a reliable Agent architecture before adding competition-specific workflows.

## 2026-07-31 project snapshot

The generic Agent framework is largely implemented. Current competition progress
is better described as **core software L2- and overall system L1+**:

- Agent planning, registered workflows, robot Tools, the HTTP simulation bridge,
  RGB-D capture, open-vocabulary vision, and classified recovery are connected.
- The deterministic industrial ActionList still uses configured object poses;
  live RGB-D perception is an explicit vision ActionList and recovery-tree mode.
- The main blockers are repeatable Gazebo reset and batch acceptance, a unified
  world-state model, fixed evaluation datasets and metrics, and physical-robot
  integration.
- The 2026-07-31 offline run collected 224 tests and ended with one failure and
  two errors listed under [Known issues](#known-issues).

Do not start reinforcement-learning work or expand service surfaces at the
expense of the first repeatable simulation acceptance loop.

## Phase 0 - Project skeleton and documentation

Goal: make the project understandable to new contributors and keep repository boundaries clear.

- [x] Define SensorAgent as an agent-side orchestration module.
- [x] Remove out-of-scope robot runtime, ROS 2, simulation, and hardware-driver content.
- [x] Establish Python `src/` package layout.
- [x] Add root `README.md`.
- [x] Establish one repository architecture document and a small operational guide set.
- [x] Add `src/sensoragent/README.md` describing package layout.
- [x] Initialize `pyproject.toml`.
- [x] Add root `.gitignore`.
- [x] Document configuration and logging in the repository architecture.
- [x] Add root `TODO.md`.

## Phase 1 - Minimal MCP/API to Skill to Tool pipeline

Goal: make the first complete local call chain work before expanding abstractions.

Target chain:

```text
mock MCP/API request
→ Agent runtime
→ Skill registry
→ Skill runtime
→ Tool registry
→ Tool runtime
→ mock tool result
→ skill result
→ Agent response
→ structured log trace
```

- [x] Define minimal call/result schemas: `AgentRequest`, `AgentResponse`.
- [x] Define minimal tool schemas: `ToolSpec`, `ToolCall`, `ToolResult`.
- [x] Define minimal skill schemas: `SkillSpec`, `SkillCall`, `SkillResult`.
- [x] Define minimal event/log schemas: `LogRecord`, `TraceContext`.
- [x] Implement tool base protocol.
- [x] Implement skill base protocol.
- [x] Implement tool registry.
- [x] Implement skill registry.
- [x] Implement tool runtime with basic logging and exception wrapping.
- [x] Implement skill runtime with basic logging and exception wrapping.
- [x] Implement a mock vision tool: `vision.mock_detect`.
- [x] Implement a mock audio tool: `audio.mock_transcribe`.
- [x] Implement mock robot tools: `robot.mock_pick`, `robot.mock_place`.
- [x] Implement one mock skill: `mock.pick_and_place`.
- [x] Add a minimal Agent runtime that invokes one skill by name.
- [x] Expose the mock skill invocation through a minimal MCP/API-shaped entry point.
- [x] Return a structured result from the full chain.
- [x] Record one full task/tool-call log trace.
- [x] Add `tests/unit/` for registry and logger basics.
- [x] Add `tests/e2e/` for mock MCP/API -> Agent -> Skill -> Tool.
- [x] Add `tests/fixtures/` directory structure for future mock inputs.
- [x] Add e2e assertions for final result, called tools, and generated logs.

## Phase 1.1 - Config-driven mock pipeline

Goal: make the current mock chain configurable instead of hard-coded in tests.

- [x] Add `configs/mock.yaml`.
- [x] Define minimal config schema for enabled tools and skills.
- [x] Implement config loader in `src/sensoragent/config/loader.py`.
- [x] Implement config schema in `src/sensoragent/config/schema.py`.
- [x] Add environment selection, e.g. `SENSORAGENT_ENV=mock`.
- [x] Add registry builder that creates tool and skill registries from config.
- [x] Move mock tool/skill registration out of e2e test setup.
- [x] Update e2e test to build runtime from `configs/mock.yaml`.
- [x] Document config loading in dedicated config docs.

## Phase 1.2 - Tool contracts

Goal: document cross-module tool input/output formats before real integrations begin.

- [x] Add root `contracts/` directory.
- [x] Add `contracts/README.md` explaining contracts vs internal schemas.
- [x] Add `contracts/tools/vision.mock_detect.schema.json`.
- [x] Add `contracts/tools/audio.mock_transcribe.schema.json`.
- [x] Add `contracts/tools/robot.mock_pick.schema.json`.
- [x] Add `contracts/tools/robot.mock_place.schema.json`.
- [x] Add shared error format contract.
- [x] Add shared trace context contract.
- [x] Add a simple contract validation helper for tests.
- [x] Validate mock tool inputs against contracts in tests.
- [x] Validate mock tool outputs against contracts in tests.

## Phase 1.3 - Manual runnable mock demo

Goal: let teammates run the mock Agent chain without reading test code.

- [x] Add CLI module `src/sensoragent/services/cli/main.py`.
- [x] Add command for running `mock.pick_and_place`.
- [x] Add CLI arguments: `--object-query`, `--target`, `--log-path`.
- [x] Write logs to `logs/tasks/` by default when run manually.
- [x] Print final `AgentResponse` in human-readable form.
- [x] Add script `scripts/run_mock_pipeline.*` if useful.
- [x] Add README instructions for running the mock chain.
- [x] Add e2e test for CLI execution.

## Phase 2 - Runtime hardening

Goal: make the minimal runtime safer, clearer, and easier to extend.

- [x] Replace broad tool exception handling with typed errors.
- [x] Replace broad skill exception handling with typed errors.
- [x] Add timeout support to `ToolRuntime`.
- [x] Add optional retry support to `ToolRuntime`.
- [x] Add input validation hook before tool invocation.
- [x] Add output validation hook after tool invocation.
- [x] Add richer `ToolError` and `SkillError` schemas.
- [x] Add tool/skill metadata such as version, tags, and enabled state.
- [x] Add duplicate registration tests.
- [x] Add unknown tool/skill tests.
- [x] Add failure-path e2e tests.
- [x] Add JSONL log shape tests.

## Phase 3 - ActionList workflow runtime

Goal: move fixed multi-step task procedures out of skills and into workflows.

- [x] Define ActionList schema.
- [x] Define ActionStep schema.
- [x] Implement sequential ActionList runtime.
- [x] Support passing step output into later steps.
- [x] Support named variables in workflow context.
- [x] Support stop-on-failure behavior.
- [x] Support per-step logging.
- [x] Recreate mock pick-and-place as an ActionList.
- [x] Add e2e test for ActionList mock pick-and-place.
- [x] Allow `AgentRuntime` to run an ActionList directly.
- [x] Keep `mock.pick_and_place` as a skill-level smoke test.
- [x] Use `mock.pick_place_actionlist` as the workflow-level demo.

## Phase 4 - DecisionTree workflow runtime

Goal: support branching task policies with retries and recovery.

- [x] Define DecisionTree node schema.
- [x] Define condition schema.
- [x] Implement branch evaluation.
- [x] Implement success/failure branches.
- [x] Implement retry counters.
- [x] Implement recoverable vs terminal failure states.
- [x] Add mock failure tools for testing.
- [x] Add e2e test for retry after mock pick failure.
- [x] Add e2e test for branch when object is not found.

## Phase 5 - Agent runtime expansion

Goal: evolve AgentRuntime from single-skill dispatch into task orchestration.

- [x] Add task/session state object.
- [x] Add workflow selector interface.
- [x] Add planner interface.
- [x] Add prompt placeholder structure for future LLM planner.
- [x] Add DeepSeek/OpenAI-compatible LLM planner implementation.
- [x] Add CLI planner mode for static or LLM planning.
- [x] Add task lifecycle states: pending, running, succeeded, failed, cancelled.
- [x] Add cancellation hook.
- [x] Add event stream abstraction.
- [x] Add task result persistence hook.
- [x] Add end-to-end test for task lifecycle.

## Phase 5.1 - Audio integration completion

Goal: finish the existing ROS-independent ASR/TTS path without expanding the
documentation surface again.

Completed:

- [x] Define audio contracts and fixtures.
- [x] Implement fake and local audio clients.
- [x] Implement `audio.transcribe`, `audio.speak`, and `audio.listen_transcribe`.
- [x] Add audio configuration and fake end-to-end tests.
- [x] Add the fixed-duration `listen-task` microphone pipeline.
- [x] Add realtime Silero VAD microphone recording.
- [x] Add `audio.listen_vad_transcribe` and its language-neutral contract.
- [x] Add `audio.listen_command` and `audio.announce` skills.
- [x] Add the voice-command acknowledgement ActionList.
- [x] Confirm model weights and generated audio are ignored.

Remaining:

- [x] Add audio tool failure-path tests.
- [x] Add local-only tests that skip when model assets are unavailable.
- [ ] Decide whether TTS playback belongs in SensorAgent or the interaction frontend.
- [ ] Add optional spoken task responses only after ownership is decided.
- [ ] Remove unused Radish-derived code and confirm no ROS 2 audio dependency remains.
- [ ] Declare `onnxruntime` and the local audio stack in installable package metadata.
- [ ] Decide whether Python 3.10 compatibility or a separate-process bridge will
  connect SensorAgent to ROS 2 Humble.

## Phase 6 - API, WebSocket, and MCP service entry points

Goal: expose SensorAgent to users, frontend, and other modules.

- [ ] Decide first real service framework.
- [ ] Add minimal HTTP API entry point.
- [ ] Add `POST /tasks` mock endpoint.
- [ ] Add `GET /tasks/{task_id}` mock endpoint.
- [ ] Add WebSocket event stream for task logs/events.
- [ ] Add minimal MCP server wrapper if needed.
- [ ] Add MCP client adapter for external tools if needed.
- [ ] Add service-level tests with mock runtime.
- [ ] Document API/MCP usage.

## Phase 7 - External integrations

Goal: connect SensorAgent to modules owned by other teams through stable adapters.

- [ ] Define integration config format.
- [ ] Implement HTTP integration client.
- [ ] Implement WebSocket integration client.
- [ ] Implement MCP integration client.
- [ ] Add vision-agent adapter.
- [ ] Add audio-agent adapter.
- [x] Define backend-neutral robot runtime adapter protocol.
- [x] Add atomic arm and gripper Tool contracts.
- [x] Add deterministic `robot.pick` and `robot.place` Skills.
- [x] Add the HTTP-to-ROS 2 simulation runtime adapter.
- [x] Connect the existing robot Tools to Gazebo/MoveIt through the HTTP bridge.
- [ ] Complete Ubuntu ROS 2 runtime acceptance for the Gazebo/MoveIt HTTP bridge.
- [ ] Connect the existing robot Tools to the physical robot.
- [ ] Add mocked integration tests.
- [ ] Add contract tests for external adapters.

## Phase 8 - Competition workflows and evaluation

Goal: implement competition-specific task logic after the generic framework is stable.

- [ ] Define the industrial pick-and-place task schema: intent, object category,
  attributes, target bin cell, constraints, allowed skills, and retry policy.
- [ ] Define the world-state schema needed by task decomposition: object instances,
  confidence, 3D pose, bin cells, robot state, gripper state, and task state.
- [x] Add the L1 fixed industrial pick-and-place ActionList workflow as the
  deterministic baseline.
- [x] Add the L2 industrial DecisionTree workflow with detect, plan-pick, pick,
  verify-grasp, plan-place, place, verify-place, success, and failure nodes.
- [x] Add visual verification workflow branches for grasp verification and target
  bin-cell placement verification.
- [x] Add classified recovery branches for object-not-found, path-planning failure,
  pick failure, dropped object, wrong-bin placement, and pose abnormality.
- [x] Add typed failure classification and deterministic recovery-plan tools.
- [x] Add visual postcondition verification tools for lifted-object and target-bin checks.
- [x] Add a constrained planner prompt/schema that can only select approved
  workflows, skills, and failure-recovery policies.
- [ ] Add fixture-based planner tests for standard commands, synonymous commands,
  ambiguous commands, missing target information, and invalid object categories.
- [x] Add fixture-based DecisionTree e2e tests for every required failure type.
- [ ] Add task log export for report tables and replay, including parsed intent,
  selected plan, node results, failure type, recovery attempts, and final status.
- [ ] Add evaluation metrics logging for parse accuracy, sequence validity,
  sequence completeness, robot-logic consistency, branch coverage, end-to-end
  success rate, recovery success rate, recovery gain, and average recovery cost.
- [ ] Add an experiment runner that batches fixed ActionList, pure LLM ActionList,
  rule/HTN ActionList, LLM + DecisionTree, and LLM + DecisionTree + visual
  verification baselines on the same fixture set.
- [ ] Add a demo CLI/API command for the competition task that can run in mock,
  Gazebo/MoveIt, and later physical-robot modes.
- [x] Add a Gazebo failure-recovery demo runner for wrong-bin, place-plan, and
  release-failure injection.
- [ ] Save report-ready CSV/JSONL summaries and failure-case artifacts for the
  technical report and demonstration video.

## Vision model four-stage plan

Goal: deliver a measurable model component without taking ownership of the ROS 2,
Gazebo, or physical-arm integration owned by other modules. This plan records the
scope agreed in the 2026-07-26 vision discussion.

### Stage 1 - YOLOE temporary baseline

- [x] Preserve `vision.open_vocab_detect` and the YOLOE backend as the temporary
  Gazebo-compatible model interface.
- [x] Keep `configs/robot_sim.yaml` on the existing baseline so Grounding DINO
  experiments do not change the default simulation workflow.
- [ ] Restore or train `models/vision/yoloe.pt`; weights stay local and must not be
  committed.
- [ ] Re-run the YOLOE baseline on the final competition class list and save the
  same metrics as later stages.
- [ ] Let the simulation owner complete end-to-end Gazebo acceptance; the vision
  owner supplies model output and diagnoses model-side failures.

### Stage 2 - Grounding DINO and SAM 2 teacher model

- [x] Implement Grounding DINO text-grounded boxes and SAM 2 box-prompted masks.
- [x] Keep strict-mask mode and explicit box fallback diagnostics.
- [x] Complete real-image smoke tests for bus, wrench, screwdriver, conveyor
  roller, and spur gear; all five mask runs used `grounding_dino_sam2` without
  box fallback.
- [x] Add a portable JSONL dataset contract, leakage/license validation, batch
  evaluation, report JSON, and configurable acceptance thresholds.
- [ ] Build a labeled competition validation set with positive, negative,
  occluded, reflective, weak-texture, and multi-instance scenes.
- [ ] Measure precision, recall, box IoU, mask IoU, center error, and warm latency
  on that fixed validation set. Single-image confidence is not an accuracy metric.
- [ ] Add real RGB-D samples, camera intrinsics, and hand-eye calibration before
  claiming base-frame position accuracy.

### Stage 3 - Industrial fine-tuning and lightweight student model

- [x] Add direct Grounding DINO fine-tuning with ordered text prompts, COCO-style
  detection targets, scene-level leakage checks, provenance validation, and
  reproducible checkpoint summaries.
- [x] Add a YOLO11n-seg baseline runner with class-map, polygon-label, and
  train/validation/test leakage preflight. It is retained as an optional later
  student baseline, not the current first training target.
- [ ] Review every Grounding DINO training box and preserve optional SAM 2 masks
  for segmentation analysis or later student training.
- [ ] Inspect Mechanical Parts Dataset 2022 and any selected BOP/MVTec subset;
  record version, license, category mapping, duplicate policy, and source split
  before adding it to a local training manifest.
- [ ] Split complete capture scenes/sessions before augmentation to prevent nearby
  frames from leaking across train, validation, and test sets.
- [ ] Fine-tune Grounding DINO on the frozen competition prompt order and report
  same-split detection metrics, latency, VRAM, model identity, and data identity.
- [ ] Fine-tune a fixed-class YOLOE/segmentation student for the final industrial
  categories only if deployment constraints justify a smaller later model.
- [ ] Compare teacher, student, and hybrid routing on the exact same test split.
- [ ] Run ablations for fine-tuning data, mask refinement, model size, input size,
  and fallback threshold. Report accuracy, latency, VRAM, and model size together.
- [ ] Export the selected student artifact only after its preprocessing and class
  map are frozen; publish the download path and checksum, not the weight file.

### Stage 4 - Real industrial acceptance

- [ ] Freeze an untouched real-scene test set covering all required categories and
  at least one negative scene per common confusing object.
- [ ] Evaluate normal light, dim light, glare, occlusion, clutter, rotation, scale,
  multi-instance, and out-of-distribution objects.
- [ ] Record per-class and aggregate metrics, failure cases, warm latency, hardware,
  model checksum, thresholds, and software version.
- [ ] Repeat RGB-D position tests after camera calibration and report error in the
  camera and `base_link` frames separately.
- [ ] Obtain team sign-off on the final model/threshold version before integrating
  it into the competition demo branch.

### Progress rhythm and ownership boundary

- [x] Prepare the 2026-07-29 model progress report with verified evidence and open
  dependencies.
- [ ] Post a short model update every 3-4 days: completed evidence, current metric,
  blocker, and next deliverable.
- [ ] Confirm the final semantic class list, camera output contract, and model
  runtime budget with the owners of intent parsing, simulation, and robot control.
- [ ] Do not claim ROS 2, Gazebo-to-arm, physical grasp, or safety acceptance from
  model-only tests.

## Robotics simulation and learning environment

Goal: provide a reproducible RM65-B manipulation environment before building
reinforcement-learning tasks.

- [x] Add a reproducible minimal RM65-B upstream import.
- [x] Vendor the BSD-3-Clause Robotiq 2F-85 simulation description.
- [x] Attach the 2F-85 to RM65-B `Link6` in a combined Xacro.
- [x] Add Humble-compatible arm and gripper ros2_control configuration.
- [x] Add combined Gazebo and MoveIt 2 launch files.
- [x] Add bounded-effort two-finger gripper control and a standard GripperCommand bridge.
- [x] Manually verify the combined model, arm motion, and gripper open/close path on Ubuntu.
- [x] Add the initial industrial tabletop world, part models, RGB-D rig, and named target areas.
- [ ] Validate finger contact, friction, and grasp stability in Gazebo Sim.
- [ ] Add automated ROS 2 launch and controller smoke tests.
- [ ] Add repeatable scene reset, object randomization, and grasp scenarios.
- [ ] Add a batch simulation runner with per-task JSONL/CSV metrics.
- [ ] Define the Gymnasium observation, action, reward, and termination contract.
- [ ] Implement the first RL environment and scripted baseline.

## Known issues

Observed on 2026-07-31 with `python -m unittest discover -s tests -p 'test_*.py'`
(224 tests run, 1 failure and 2 errors) on a Windows machine without ROS 2:

- [ ] `tests/unit/test_vision_evaluation.py` imports `pytest`, which is not declared
  in `requirements.txt` or `pyproject.toml`. Either declare a test dependency set
  or port the module to `unittest`.
- [ ] `test_gazebo_recovery_demo_script.GazeboRecoveryDemoScriptTest.test_wrong_table_demo_runs_without_gazebo`
  runs the demo with `--execute`, so it keeps the `http` robot backend from
  `configs/robot_sim.yaml` and fails with `ROBOT_BRIDGE_UNAVAILABLE` unless the
  bridge is running. The case needs a fake robot backend and a stateful fake
  detector to match its name, or it should be moved out of the default suite.
- [ ] `DecisionTreeLastFailureTest.test_failed_node_is_available_to_recovery_tools`
  expects `last_failure.failed_step` to remain `not_found`, but the current
  runtime reports the subsequent `found_check` condition node. The intended
  failure-evidence semantics must be fixed or the test expectation deliberately
  updated.
- [ ] `vision.capture_frame` and the `robot.plan_*` planning tools have no files
  under `contracts/tools/`.
- [ ] `src/sensoragent/services/api/` is still an empty placeholder while the
  README and architecture describe API/MCP entry points as future work.

## Notes

- Logger is framework infrastructure, not a normal skill.
- Low-level robot control, production ROS 2 drivers, and physical safety belong to
  external runtime modules. The local RM65-B workspace is a development simulation
  integration.
- SensorAgent collaborates with external modules through API, MCP, WebSocket, or documented adapters.
- Internal Python schemas are not the same as cross-module contracts; contracts should be language-neutral.
