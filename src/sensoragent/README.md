# `sensoragent` Python Package

This package contains the Agent runtime and ROS-independent integrations. The
ROS 2 simulation packages live separately under `ros2_ws/src/`.

## Current layout

```text
src/sensoragent/
├── agent/          runtime assembly, task lifecycle, static/LLM planning
├── config/         YAML and environment configuration
├── contracts/      JSON contract validation helpers
├── integrations/   local audio, microphone, VAD, LLM, and robot HTTP clients
├── logger/         structured JSONL task logging
├── mcp/            current mock MCP-shaped endpoint
├── schemas/        Agent, Tool, Skill, workflow, and plan data models
├── services/       CLI entry point and future API package
├── skills/         Skill registry/runtime, mock/audio/robot skills
├── state/          in-memory task store and event stream
├── tools/          Tool registry/runtime and mock/audio/vision/robot tools
└── workflows/      ActionList and DecisionTree runtimes and definitions
```

## Implemented execution targets

Tools:

```text
vision.mock_detect
vision.config_detect
vision.open_vocab_detect
robot.mock_pick
robot.mock_place
robot.get_state
robot.move_joints
robot.move_pose
robot.move_linear
robot.plan_top_down_pick
robot.plan_oriented_pick
robot.plan_place
robot.resolve_place_target
robot.stop
gripper.open
gripper.close
gripper.get_state
vision.verify_object_lifted
vision.verify_object_in_bin
recovery.classify_failure
recovery.plan
audio.mock_transcribe
audio.listen_transcribe
audio.listen_vad_transcribe
audio.transcribe
audio.speak
```

Skills:

```text
mock.pick_and_place
audio.listen_command
audio.announce
robot.pick
robot.place
robot.verify_grasp
robot.verify_place
```

ActionLists:

```text
mock.pick_place_actionlist
audio.voice_command_ack_actionlist
industrial.pick_place_actionlist
industrial.pick_only_actionlist
industrial.place_only_actionlist
industrial.vision_pick_place_actionlist
```

DecisionTree support is implemented and tested with mock retry and not-found
flows, but no production robot DecisionTree is registered.

## Audio path

The local path combines:

```text
SoundDeviceVadRecorder
→ SileroVadSegmenter / ONNX Runtime
→ LocalAudioClient
→ SenseVoice / sherpa-onnx
```

TTS writes WAV output through supported sherpa-onnx assets. Direct playback is
intentionally disabled.

## Robot boundary

`tools/robot/` and `skills/robot/` contain backend-neutral robot control,
planning, pick/place, and verification behavior. `configs/robot_mock.yaml` uses
`FakeRobotControlClient`; `configs/robot_sim.yaml` uses
`HttpRobotControlClient` to talk to the ROS 2 bridge on `127.0.0.1:8765`.

The working RM65-B and Robotiq control stack is a separate ROS 2 package:

```text
ros2_ws/src/sensoragent_rm65_b_bringup
```

The Agent process does not import ROS 2 directly. Robot execution crosses the
HTTP bridge into `ros2_ws/src/sensoragent_robot_bridge`.

## Runtime compatibility

The package currently declares Python 3.12. ROS 2 Humble on Ubuntu 22.04
normally uses Python 3.10, so direct in-process `rclpy` integration is not yet
supported by the declared runtime baseline.
