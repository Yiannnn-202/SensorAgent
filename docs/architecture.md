# SensorAgent Architecture

SensorAgent is the repository for agent-side embodied-task orchestration and its
local development integrations. It combines a Python agent runtime, language-neutral
tool contracts, mock and audio adapters, and a reproducible RM65-B ROS 2 simulation
workspace.

## System role

Within the wider Aether system:

```text
GECA / SensorAgent
  understands tasks, plans, selects workflows, and invokes tools

ECOS and robot runtimes
  provide perception, simulation, motion, hardware, and safety capabilities
```

SensorAgent owns orchestration and integration boundaries. It does not own robot
firmware, vendor drivers, physical safety systems, or production hardware bringup.
The ROS 2 workspace in this repository is a development and simulation integration,
not a replacement for the robot runtime.

## Runtime architecture

```mermaid
flowchart LR
  USER["CLI / API / audio input"] --> AGENT["AgentRuntime"]
  AGENT --> PLANNER["Static or LLM planner"]
  AGENT --> WORKFLOW["ActionList / DecisionTree"]
  AGENT --> SKILL["Skill runtime"]
  WORKFLOW --> TOOL["Tool runtime"]
  SKILL --> TOOL
  TOOL --> LOCAL["Local or mock integration"]
  TOOL --> EXTERNAL["HTTP / WebSocket / MCP / ROS 2 adapter"]
  AGENT --> STATE["Task state and event stream"]
  TOOL --> LOG["Structured logs"]
  WORKFLOW --> LOG
```

### Agent and planner

`src/sensoragent/agent/` owns task orchestration, planner selection, task lifecycle,
and runtime assembly. The static planner provides deterministic tests. The LLM
planner uses an OpenAI-compatible endpoint and returns a validated `AgentPlan`; it
does not directly execute low-level tools.

### Tools, skills, and workflows

- **Tools** are atomic typed capabilities such as `audio.transcribe`,
  `vision.mock_detect`, or `robot.mock_pick`.
- **Skills** compose reusable tool behavior.
- **ActionLists** execute ordered steps.
- **DecisionTrees** add conditions, retries, and recovery branches.

Tool execution includes contract validation, timeout handling, retry policy, typed
errors, and structured logging.

### Contracts

`contracts/` contains language-neutral JSON contracts for cross-module interfaces.
Internal Python schemas remain under `src/sensoragent/schemas/`. External systems
should implement contracts without importing SensorAgent's Python package.

### State and logging

`src/sensoragent/state/` tracks task lifecycle and events. Agent-side logs are written
under ignored `logs/` paths:

```text
logs/app.log
logs/tasks/
logs/traces/
logs/errors/
logs/audio/
```

Task logs use JSONL records for requests, workflow steps, tool calls, retries,
failures, and final status. External robot or simulator logs remain owned by their
runtime unless an integration explicitly imports them.

## Configuration

YAML files under `configs/` select enabled tools, skills, integrations, logging, and
environment mode. Configuration resolution order is:

```text
explicit CLI or code path
SENSORAGENT_CONFIG
SENSORAGENT_ENV -> configs/<env>.yaml
configs/mock.yaml
```

Secrets and machine-local overrides belong in ignored `.env` files.

Current configurations include:

```text
configs/mock.yaml
configs/audio_mock.yaml
configs/audio_local.yaml
```

## Audio integration

The audio integration is ROS-independent. `AudioClient`, microphone, and VAD
abstractions live under `src/sensoragent/integrations/`; ASR/TTS/listen tools
live under `src/sensoragent/tools/audio/`.

The local command path is:

```text
16 kHz mono microphone input
→ SoundDeviceVadRecorder
→ Silero VAD ONNX inference
→ utterance WAV
→ SenseVoice through sherpa-onnx
→ normalized command text
→ Agent planner
```

`audio.listen_vad_transcribe` supports realtime VAD termination and per-call
threshold, silence-tail, and padding overrides. The older fixed-duration
`audio.listen_transcribe` remains available. Higher-level audio components
include:

- `audio.listen_command`, which normalizes one recognized command;
- `audio.announce`, which creates task-facing speech output;
- `audio.voice_command_ack_actionlist`, which listens and generates an
  acknowledgement file.

Local TTS supports compatible sherpa-onnx VITS layouts and a CLI path for the
present Baker/icefall assets. SensorAgent intentionally rejects direct local
playback, and `listen-task` does not automatically announce task results.

Local model weights are runtime assets under ignored `models/` paths. Automated
tests use fake clients and fixtures, so the default test suite does not require a
microphone, speaker, or model weights.

The audio path does not yet imply robot control. Both the static and LLM planners
currently select only `mock.pick_place_actionlist`; recognized commands therefore
exercise the Agent lifecycle and mock robot tools.

## Robotics simulation

`ros2_ws/` provides the local RM65-B simulation stack for Ubuntu 22.04 and ROS 2
Humble:

| Package | Ownership | Responsibility |
| --- | --- | --- |
| `rm_description` | Imported locally | RM65-B URDF and meshes |
| `rm_gazebo` | Imported locally | Upstream arm-only Gazebo integration |
| `rm_65_config` | Imported locally | Upstream arm-only MoveIt 2 configuration |
| `robotiq_description` | Vendored | Robotiq 2F-85 Xacro and meshes |
| `sensoragent_rm65_b_bringup` | Project-owned | Combined Gazebo, ros2_control, and MoveIt integration |

Upstream files are imported locally by
`scripts/linux/fetch_rm65_b_upstream.sh` because redistribution permission is
unclear. The repository tracks the import recipe and compatibility adjustments, not
the RealMan model assets. Robotiq assets are redistributed under BSD-3-Clause;
their pinned source and retained license are documented in
`ros2_ws/ROBOTIQ_UPSTREAM.md`.

### Combined robot structure

```text
world
└── base_link
    └── RM65-B joint1 ... joint6
        └── Link6
            └── robotiq_85_base_joint (fixed)
                └── Robotiq 2F-85 rigid parallel-jaw links
```

The mounting joint is defined in
`sensoragent_rm65_b_bringup/urdf/rm65_b_robotiq_2f85.urdf.xacro`. Its default
`xyz` and `rpy` are zero so Gazebo and MoveIt share one configurable transform.
The final flange adapter thickness and orientation remain an Ubuntu simulation
calibration task.

### Control and planning path

```text
MoveIt / direct ROS 2 Action
├── rm_group_controller
│   └── joint1 ... joint6
└── robotiq_gripper_controller
    └── gripper_action_bridge.py
        └── robotiq_gripper_effort_controller
            ├── robotiq_85_left_knuckle_joint
            └── robotiq_85_right_knuckle_joint
                ↓
           gz_ros2_control
                ↓
            Gazebo Sim
```

The simulation uses two bounded-effort prismatic finger joints behind the
standard `control_msgs/action/GripperCommand` API. Each side is collapsed into
one rigid jaw link containing the knuckle, finger, and fingertip meshes. The
jaw has exactly one prismatic opening degree of freedom, so it cannot rotate or
sway relative to the gripper base. Either jaw can still stop independently on
object contact.

The combined SRDF exposes:

- `rm_group`: the `base_link` to `Link6` arm chain;
- `gripper`: the active 2F-85 knuckle joint;
- `robotiq_2f85`: the end effector attached to `Link6`;
- named `open` and `closed` gripper states.

The combined model, arm trajectory execution, and gripper Action interface have
been manually exercised on Ubuntu. Object contact and repeatable grasp stability
still require acceptance testing.

SensorAgent does not yet contain a completed ROS 2 bridge for issuing full robot
tasks directly. `src/sensoragent/integrations/ros2/`, real robot Tools, robot
Skills, and robot workflows are placeholders. The ROS 2 bringup package can be
controlled directly through MoveIt and ROS 2 Actions, but it is not registered
inside the Python Agent runtime.

## Runtime compatibility boundary

The current Python Agent package declares Python 3.12 and uses features such as
`enum.StrEnum` and `datetime.UTC`. Ubuntu 22.04 with ROS 2 Humble normally ships
Python 3.10. The audio/Agent process and ROS 2 simulation can therefore run
separately, but an in-process `rclpy` integration needs an explicit compatibility
decision:

```text
make SensorAgent Python 3.10 compatible
or
keep separate processes and define a ROS 2 / API / MCP transport boundary
```

This is a known issue, not an implemented integration.

## Reinforcement learning and simulation assets

`reinforcement_learning/` and `simulation/gazebo/` currently provide tracked
empty structure for future environments, policies, evaluation, worlds, models,
and scenarios. No Gymnasium environment, reset interface, reward function,
industrial world, training entry point, or evaluation harness exists yet.
Low-level trajectory planning and safety remain with MoveIt 2, `ros2_control`,
and the robot runtime.

## Repository layout

```text
SensorAgent/
├── configs/                 runtime configurations
├── contracts/               cross-module JSON contracts
├── docs/
│   ├── architecture.md      single repository architecture source
│   ├── guides/              operational setup and test guides
│   └── team/                team-wide conventions and context
├── reinforcement_learning/ future RL structure
├── ros2_ws/                 local RM65-B ROS 2 simulation workspace
├── simulation/              Gazebo worlds, models, and scenarios
├── src/sensoragent/         Python agent runtime
├── tests/                   unit, end-to-end, ROS, simulation, and RL tests
├── README.md                entry point and common commands
└── TODO.md                  authoritative development backlog
```

## Documentation policy

This file is the only repository architecture document. `TODO.md` is the only
development backlog. Team-wide material stays under `docs/team/`; operational
instructions stay under `docs/guides/`. Superseded documents are deleted and remain
available through Git history rather than being copied into an archive folder.
