# Audio Pipeline Test

This document describes the current listen-once audio pipeline.

## Current chain

```text
listen-task CLI
→ microphone recorder
→ audio.listen_transcribe
→ audio.transcribe
→ Agent run_task
→ planner
→ ActionList
→ task result
```

The default automated tests use `FakeMicrophoneRecorder` and `FakeAudioClient`, so they do not require a real microphone, ASR model, TTS model, or audio device.

## Run automated tests

```powershell
$env:PYTHONPATH = "$(Get-Location)\src"
python -m unittest discover -s tests -p 'test_*.py'
```

## Run listen-task with fake audio

```powershell
$env:PYTHONPATH = "$(Get-Location)\src"
python -m sensoragent.services.cli.main listen-task --config configs\audio_mock.yaml --planner static --duration 1 --object-query "silver roller" --target "third bin cell"
```

This records through the fake recorder by copying:

```text
tests/fixtures/audio/command.wav
```

and then uses `FakeAudioClient` to return a deterministic transcript.

## Run listen-task with local microphone and local ASR

Use:

```powershell
$env:PYTHONPATH = "$(Get-Location)\src"
python -m sensoragent.services.cli.main listen-task --config configs\audio_local.yaml --planner llm --duration 5
```

Requirements:

```text
sounddevice
numpy
sherpa_onnx
models/asr/sense-voice/model.int8.onnx
models/asr/sense-voice/tokens.txt
DeepSeek API key in .env for --planner llm
```

The local microphone path records a fixed-duration 16 kHz mono WAV file under `logs/audio/`, then calls `audio.transcribe`.

## Current limitations

```text
No streaming VAD yet.
No Silero VAD integration in the SensorAgent recorder yet.
No automatic TTS reply yet.
No default test depends on real microphone access.
```
