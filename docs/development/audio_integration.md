# Audio Integration Review

This document records the Phase A0 review of Radish audio content for ASR/TTS migration into SensorAgent.

## Scope

Only Radish sound and TTS-related content is in scope.

In-scope candidates:

```text
Radish/service/sound/
Radish/service/tts/
Radish/src/sound/
```

Out of scope:

```text
Radish ROS 2 robot packages
Radish arm/base/brain/webui packages
Radish perception, face, pose, object-detection services
Radish launch scripts except as reference
ROS 2 message/service definitions
```

SensorAgent should not gain a ROS 2 dependency from this migration.

## Reviewed files

### ASR service

```text
Radish/service/sound/server.py
Radish/service/sound/audio/asr.py
Radish/service/sound/audio/config.py
Radish/service/sound/audio/pipeline.py
Radish/service/sound/audio/vad.py
Radish/service/sound/audio/yamnet.py
Radish/service/sound/api.md
Radish/service/sound/pyproject.toml
```

### TTS service

```text
Radish/service/tts/tts_server.py
Radish/service/tts/tts.md
Radish/service/tts/pyproject.toml
```

### ROS 2 sound package

```text
Radish/src/sound/package.xml
Radish/src/sound/sound/hearing.py
Radish/src/sound/sound/speak.py
Radish/src/sound/config/*.yaml
Radish/src/sound/launch/sound_launch.py
```

## ASR summary

Radish ASR is mainly implemented as a FastAPI sound service:

```text
Radish/service/sound/server.py
```

It exposes:

```text
WebSocket /ws/asr/v1
HTTP     POST /asr
HTTP     GET /health
```

The primary ASR path is streaming WebSocket:

```text
raw int16 PCM, 16 kHz, mono
→ Silero VAD
→ SenseVoice ASR
→ transcript JSON messages
```

The legacy one-shot path is:

```text
POST /asr
body: raw int16 PCM, 16 kHz, mono
response: {"text": "...", "language": "..."}
```

Reusable non-ROS logic:

```text
audio/asr.py          # SenseVoice wrapper, hallucination filter
audio/config.py       # model path resolution and ASR/VAD parameters
audio/pipeline.py     # VAD/ASR pipeline reference; YAMNet is out of scope
audio/vad.py          # Silero VAD wrapper
audio/yamnet.py       # Out of scope; do not migrate bell detection
server.py             # FastAPI service reference
```

Important dependencies from `service/sound/pyproject.toml`:

```text
fastapi
uvicorn[standard]
python-multipart
numpy
onnxruntime==1.23.2
websockets>=12.0
pydantic>=2.0
sherpa-onnx expected from system site-packages
```

## ASR model expectations

Radish ASR expects SenseVoice files:

```text
model.int8.onnx
tokens.txt
```

Old default search paths include:

```text
~/Projects/models/sense-voice/
~/Projects/models/sensevoice/
~/gpsr_ws/models/sense-voice/
~/gpsr_ws/models/sensevoice/
```

Override:

```text
ASR_MODEL_DIR
```

For SensorAgent, these should be normalized to:

```text
models/asr/sense-voice/
```

or configured through:

```yaml
integrations:
  audio:
    asr_model_dir: models/asr/sense-voice
```

## VAD model expectations

VAD expects:

```text
silero_vad.onnx
```

Old default paths:

```text
~/Projects/models/vad/silero_vad.onnx
~/gpsr_ws/models/vad/silero_vad.onnx
```

Override:

```text
ASR_VAD_MODEL
```

For SensorAgent, this should be normalized to:

```text
models/asr/vad/silero_vad.onnx
```

YAMNet bell detection is out of scope for this migration. Do not copy YAMNet model files or migrate bell detection logic.

## TTS summary

Radish TTS is implemented as a FastAPI HTTP service:

```text
Radish/service/tts/tts_server.py
```

It exposes:

```text
GET  /health
POST /tts
```

`POST /tts` accepts JSON:

```json
{
  "text": "Hello world",
  "speed": 1.0,
  "sid": 0
}
```

It returns:

```text
Content-Type: audio/wav
headers:
  X-Sample-Rate
  X-Duration
  X-Gen-Time
  X-Voice
  X-Text
```

The server code currently uses `sherpa_onnx.OfflineTts` with Piper-VITS style assets.

Reusable non-ROS logic:

```text
tts_server.py          # FastAPI service and WAV response implementation
_resolve_tts_assets    # model asset resolution idea
_load_tts              # model loading pattern
_pcm_to_wav            # audio serialization helper
```

## TTS model expectations

`tts_server.py` currently resolves assets under:

```text
~/Projects/models/vits-piper-en_US-glados/
```

Expected files:

```text
en_US-glados.onnx
tokens.txt
espeak-ng-data/
```

For SensorAgent, these should be normalized to:

```text
models/tts/vits-piper-en_US-glados/
```

or configured through:

```yaml
integrations:
  audio:
    tts_model_dir: models/tts
```


The current local `models/tts/` directory in this repository uses a Baker/icefall-style layout:

```text
models/tts/model-steps-3.onnx
models/tts/vocos-22khz-univ.onnx
models/tts/tokens.txt
models/tts/lexicon.txt
models/tts/*.fst
models/tts/dict/
```

`LocalAudioClient` supports this layout through the `sherpa-onnx-offline-tts` CLI when that command is installed. If the command is not available, the tool returns a clear model/backend error.

Current implementation status:

```text
FakeAudioClient        implemented for tests
LocalAudioClient       implemented for SenseVoice ASR and sherpa-onnx TTS backends
audio.transcribe       implemented
audio.speak            implemented
configs/audio_mock.yaml
configs/audio_local.yaml
```

Note: `Radish/service/tts/tts.md` and `pyproject.toml` mention Qwen3-TTS, while the reviewed `tts_server.py` uses sherpa-onnx Piper-VITS. The current SensorAgent adapter supports the reviewed Piper-VITS layout and the local Baker/icefall CLI layout; Qwen3-TTS is not integrated.

## ROS 2 sound package summary

Radish also includes:

```text
Radish/src/sound/
```

This is a ROS 2 package. `package.xml` depends on:

```text
rclpy
std_msgs
std_srvs
sound_interfaces
python3-numpy
python3-scipy
```

Important files:

```text
sound/hearing.py
sound/speak.py
```

`hearing.py` is a ROS 2 node that:

```text
subscribes to microphone topic
streams audio to the sound WebSocket service
publishes transcripts and bell events to ROS topics; bell events are out of scope for SensorAgent migration
```

`speak.py` is a ROS 2 node that:

```text
exposes /task/speak
calls a TTS HTTP service
plays WAV audio through sounddevice
publishes speaker/device state
```

These files should not be merged directly into SensorAgent because they depend on ROS 2 and system audio playback.

Potentially reusable ideas:

```text
WAV decoding helpers in speak.py
HTTP call shape to local TTS service
speaker playback behavior as future reference only
```

Do not copy ROS 2 node structure into SensorAgent.

## Migration recommendation

Use a two-layer migration:

```text
AudioClient integration layer
→ audio tools
```

Suggested SensorAgent files:

```text
src/sensoragent/integrations/audio.py
src/sensoragent/tools/audio/transcribe.py
src/sensoragent/tools/audio/speak.py
```

Suggested tool names:

```text
audio.transcribe
audio.speak
```

Do not make workflows depend on Radish internals. Workflows should only call SensorAgent tools.

## Proposed ASR tool contract

Tool:

```text
audio.transcribe
```

Input:

```json
{
  "audio_path": "tests/fixtures/audio/command.wav",
  "language": "zh"
}
```

Output:

```json
{
  "text": "把银色滚柱放到第三个格子",
  "confidence": 0.94,
  "language": "zh"
}
```

## Proposed TTS tool contract

Tool:

```text
audio.speak
```

Input:

```json
{
  "text": "任务已完成",
  "voice": "default",
  "output_path": "logs/audio/task_001.wav",
  "play": false
}
```

Output:

```json
{
  "spoken": true,
  "audio_path": "logs/audio/task_001.wav",
  "duration_ms": 1200
}
```

First implementation should generate or return an audio file path. Playback should remain optional and disabled by default.

## Implementation order

Recommended next steps:

```text
1. Add models/ to .gitignore.
2. Document model layout under docs/development/audio_models.md or this file.
3. Add audio.transcribe and audio.speak contracts.
4. Add FakeAudioClient.
5. Add audio.transcribe and audio.speak tools backed by FakeAudioClient.
6. Add config for audio_mock.
7. Add tests.
8. Wrap Radish service logic as LocalAudioClient without ROS 2.
```

## Decisions recorded

- ASR/TTS should be tools first.
- Audio skills/workflows are optional and should be added only after tools are stable.
- ROS 2 wrappers from Radish are not merged.
- YAMNet bell detection is not migrated.
- Model files are local runtime assets and are not tracked by Git.
- TTS playback is not part of the first migration step.
