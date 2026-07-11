# Audio Guide

SensorAgent supports fake and local ASR/TTS integrations without a ROS 2 dependency.

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

## Local microphone and ASR

```powershell
$env:PYTHONPATH = "$(Get-Location)\src"
python -m sensoragent.services.cli.main listen-task --config configs\audio_local.yaml --planner llm --duration 5
```

Requirements include `sounddevice`, `numpy`, `sherpa_onnx`, SenseVoice model files,
and an LLM API key in `.env`.

The current recorder captures a fixed-duration 16 kHz mono WAV before transcription.
Streaming VAD and automatic spoken responses remain future work tracked in
[`TODO.md`](../../TODO.md).
