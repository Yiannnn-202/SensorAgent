# Local VAD, ASR, and TTS Guide

SensorAgent supports fake and local audio integrations without a ROS 2
dependency. The default local microphone backend uses realtime Silero VAD to
capture one utterance and SenseVoice to transcribe it.

## Current pipeline

```text
microphone
→ 16 kHz mono PCM windows
→ Silero VAD
→ automatic end-of-speech detection
→ SenseVoice ASR
→ Agent task
```

The recognized task currently executes an approved mock workflow. It does not
control the RM65-B simulation.

## Python dependencies

Install:

```bash
python -m pip install -r requirements.txt
```

The local path uses `numpy`, `sounddevice`, `sherpa-onnx`, and `onnxruntime`.
`requirements.txt` installs the shared runtime plus `sounddevice` and
`sherpa-onnx`. At present `onnxruntime` is used directly by the VAD code but is
not explicitly declared in `requirements.txt`; install it manually if it is not
already present:

```bash
python -m pip install onnxruntime
```

The package metadata in `pyproject.toml` currently lists only the core runtime
dependencies. Installing the project package alone does not install the full
local audio stack.

## Model layout

Model weights are local runtime assets and must not be committed:

```text
models/
├── asr/
│   ├── sense-voice/
│   │   ├── model.int8.onnx
│   │   └── tokens.txt
│   └── vad/
│       └── silero_vad.onnx
└── tts/
    ├── model-steps-3.onnx
    ├── vocos-22khz-univ.onnx
    ├── tokens.txt
    ├── lexicon.txt
    ├── *.fst
    └── dict/
```

Generated recordings and speech output belong under ignored `logs/audio/`.

## Fake audio pipeline

```powershell
$env:PYTHONPATH = "$(Get-Location)\src"
python -m sensoragent.services.cli.main listen-task --config configs\audio_mock.yaml --planner static --duration 1 --object-query "silver roller" --target "third bin cell"
```

This uses `FakeMicrophoneRecorder`, the committed WAV fixture, and
`FakeAudioClient`. It requires no microphone or model weights.

## Local realtime VAD and ASR

```bash
PYTHONPATH=src python -m sensoragent.services.cli.main \
  listen-task \
  --config configs/audio_local.yaml \
  --planner llm
```

Requirements include `sounddevice`, `numpy`, `sherpa_onnx`, SenseVoice model files,
Silero VAD, and an LLM API key in `.env`.

`listen_duration_seconds` is a maximum recording window. Recording ends earlier
after speech followed by the configured silence period.

Useful VAD overrides for one-off tuning:

```bash
PYTHONPATH=src python -m sensoragent.services.cli.main \
  listen-task \
  --config configs/audio_local.yaml \
  --planner llm \
  --duration 15 \
  --vad-threshold 0.30 \
  --vad-post-roll-ms 2800 \
  --vad-tail-padding-ms 500
```

The defaults live in `configs/audio_local.yaml`:

```text
listen_duration_seconds
listen_language
vad_threshold
vad_min_rms
vad_min_speech_windows
vad_pre_roll_ms
vad_post_roll_ms
vad_tail_padding_ms
vad_max_utterance_sec
```

## ASR input constraints

The current local ASR/VAD path expects:

```text
mono
16 kHz
16-bit PCM WAV
```

Recognized SenseVoice tags are removed. Empty output and a small set of common
hallucination strings are normalized to an empty command.

## TTS status

`audio.speak` and `audio.announce` can generate WAV files from supported local
assets. Direct playback is intentionally disabled:

```text
play: true → rejected
play: false → write WAV output
```

`audio.voice_command_ack_actionlist` listens and creates an acknowledgement
file, but no dedicated CLI command exposes that ActionList and `listen-task`
does not automatically speak success or failure messages.

## Environment boundary

The current SensorAgent package requires Python 3.12, whereas ROS 2 Humble on
Ubuntu 22.04 normally uses Python 3.10. Run the local audio and ROS 2 stacks as
separate processes; robot execution crosses the HTTP bridge rather than
importing `rclpy` into the Agent process.
