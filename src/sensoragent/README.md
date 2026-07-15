# `sensoragent` Python Package

This package contains the Agent runtime and ROS-independent integrations. The
ROS 2 simulation packages live separately under `ros2_ws/src/`.

## Current layout

```text
src/sensoragent/
├── agent/          runtime assembly, task lifecycle, static/LLM planning
├── config/         YAML and environment configuration
├── contracts/      JSON contract validation helpers
├── integrations/   local audio, microphone, VAD, and LLM clients
├── logger/         structured JSONL task logging
├── mcp/            current mock MCP-shaped endpoint
├── schemas/        Agent, Tool, Skill, workflow, and plan data models
├── services/       CLI entry point and API placeholder
├── skills/         Skill registry/runtime, mock and audio skills
├── state/          in-memory task store and event stream
├── tools/          Tool registry/runtime and mock/audio/vision tools
└── workflows/      ActionList and DecisionTree runtimes and definitions
```

## Implemented execution targets

Tools:

```text
vision.mock_detect
robot.mock_pick
robot.mock_place
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
```

ActionLists:

```text
mock.pick_place_actionlist
audio.voice_command_ack_actionlist
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

`tools/robot/`, `skills/robot/`, `workflows/robot/`, and
`integrations/ros2/` do not yet contain real robot implementations. Current
Python robot behavior is mock-only.

The working RM65-B and Robotiq control stack is a separate ROS 2 package:

```text
ros2_ws/src/sensoragent_rm65_b_bringup
```

Connecting it to Agent workflows requires real robot contracts and a ROS 2,
API, or MCP integration.

## Runtime compatibility

The package currently declares Python 3.12. ROS 2 Humble on Ubuntu 22.04
normally uses Python 3.10, so direct in-process `rclpy` integration is not yet
supported by the declared runtime baseline.
