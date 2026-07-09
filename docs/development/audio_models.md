# Audio Model Layout

SensorAgent keeps local ASR/TTS model files under the repository-level `models/` directory during development.

Model files are runtime assets and must not be committed to Git. The root `.gitignore` ignores:

```text
models/
```

## Expected layout

```text
models/
├── asr/
│   ├── sense-voice/
│   │   ├── model.int8.onnx
│   │   └── tokens.txt
│   └── vad/
│       └── silero_vad.onnx
└── tts/
    └── vits-piper-en_US-glados/
        ├── en_US-glados.onnx
        ├── tokens.txt
        └── espeak-ng-data/
```

## ASR models

Radish's ASR service expects SenseVoice files:

```text
model.int8.onnx
tokens.txt
```

Place them under:

```text
models/asr/sense-voice/
```

Radish's VAD expects:

```text
silero_vad.onnx
```

Place it under:

```text
models/asr/vad/silero_vad.onnx
```

YAMNet bell detection is not part of this migration. Do not download or place YAMNet model files for SensorAgent.

## TTS models

The reviewed Radish TTS server currently uses sherpa-onnx Piper-VITS assets. It expects:

```text
en_US-glados.onnx
tokens.txt
espeak-ng-data/
```

Place them under:

```text
models/tts/vits-piper-en_US-glados/
```


The current local `models/tts/` directory may instead use a Baker/icefall-style layout:

```text
models/tts/model-steps-3.onnx
models/tts/vocos-22khz-univ.onnx
models/tts/tokens.txt
models/tts/lexicon.txt
models/tts/*.fst
models/tts/dict/
```

SensorAgent's `LocalAudioClient` supports this layout through the `sherpa-onnx-offline-tts` command-line tool. Install that command before running local TTS with this model layout.

Note: Radish's TTS documentation also mentions Qwen3-TTS, but the reviewed `tts_server.py` uses Piper-VITS through `sherpa_onnx.OfflineTts`. Qwen3-TTS is not integrated in SensorAgent.

## Configuration

Future audio configs should point to these model paths:

```yaml
integrations:
  audio:
    backend: local
    asr_model_dir: models/asr/sense-voice
    vad_model_path: models/asr/vad/silero_vad.onnx
    tts_model_dir: models/tts
```

## Git policy

Do not commit:

```text
model weights
downloaded model repositories
generated audio dumps
temporary waveform outputs
local cache directories
```

Generated audio should go under ignored runtime paths such as:

```text
logs/audio/
```
