# Voice to Gazebo Pick/Place with Vision Verification

This guide runs a spoken command through:

```text
microphone
→ realtime Silero VAD
→ one-utterance SenseVoice ASR
→ Chinese or English text
→ LLM planner JSON
→ industrial.recovery_pick_place_tree
→ robot pick/place over the HTTP bridge
→ RGB-D post-place vision verification
```

Use this path when you want local microphone input to control the RM65-B Gazebo
simulation and verify the placed object with vision.

## What `--duration` means

`listen-task --duration 15` sets the maximum listening window. It does not force
a 15-second recording.

The current CLI is utterance-based:

```text
mic audio streams into VAD
→ VAD stops after speech plus silence tail
→ WAV is finalized
→ SenseVoice runs ASR once on that utterance
```

So the microphone/VAD stage is realtime, but ASR is not a token-by-token
streaming decoder in this CLI. The command usually proceeds before the duration
limit as soon as VAD detects the end of speech.

## Chinese command support

`configs/audio_robot_sim.yaml` defaults to:

```yaml
listen_language: zh
```

SenseVoice receives the Chinese language hint, and the LLM planner prompt is
written to parse Chinese or English task text. Chinese target phrases such as
`第三个格子`, `三号格子`, and English phrases such as `bin cell 3` should normalize
to `bin_cell_3`.

Good example commands:

```text
把红色方块放到第三个格子，并用视觉确认
把滚柱放到三号格子，然后视觉检查
put the red block into bin cell 3 and verify it with vision
```

Mention visual verification explicitly (`用视觉确认`, `视觉检查`, or `verify it
with vision`) so the LLM selects `industrial.recovery_pick_place_tree`, which
captures a fresh RGB-D frame after placing and runs `vision.verify_object_in_bin`.

## Prerequisites

Install the Python runtime dependencies and local audio dependencies:

```bash
python -m pip install -r requirements.txt
python -m pip install onnxruntime
```

Make sure the local model assets exist:

```text
models/asr/sense-voice/model.int8.onnx
models/asr/sense-voice/tokens.txt
models/asr/vad/silero_vad.onnx
models/vision/yoloe.pt
```

Configure the LLM credentials in an ignored `.env` file. The LLM planner must be
available because it maps the Chinese transcript to workflow JSON.

## Start Gazebo and the robot bridge

In one terminal:

```bash
cd ~/SensorAgent
bash scripts/linux/run_rm65_b_sim.sh
```

In another terminal, check readiness:

```bash
cd ~/SensorAgent
curl http://127.0.0.1:8765/health
curl http://127.0.0.1:8765/ready
```

For execution, `/ready` should report the motion and gripper interfaces as
ready.

## Run voice control

From the repository root:

```bash
PYTHONPATH=src .venv312/bin/python -m sensoragent.services.cli.main \
  listen-task \
  --config configs/audio_robot_sim.yaml \
  --planner llm \
  --duration 15
```

Then speak one short command, for example:

```text
把红色方块放到第三个格子，并用视觉确认
```

The CLI prints JSON containing:

- `transcript`: recorded WAV path, ASR text, confidence, language, and VAD timing
- `task`: the selected plan, workflow status, result, and any error

Task logs are written under `logs/tasks/`. Captured RGB-D frames for live
verification are written under `logs/vision/`.

## Useful tuning

To test only the sound input path without LLM, robot, or vision, run:

```bash
PYTHONPATH=src .venv312/bin/python scripts/linux/test_audio_input_pipeline.py --mode devices
PYTHONPATH=src .venv312/bin/python scripts/linux/test_audio_input_pipeline.py --mode raw --duration 5
PYTHONPATH=src .venv312/bin/python scripts/linux/test_audio_input_pipeline.py --mode vad --duration 10
PYTHONPATH=src .venv312/bin/python scripts/linux/test_audio_input_pipeline.py --mode all --duration 10
```

Use `--mode raw` first. If its `rms` and `peak` are near zero, fix the OS/VM
microphone before debugging VAD or ASR.

The diagnostic scripts print concise live progress lines to stderr, for example
`[vad] speech started`, `[audio] captured`, and `[asr] transcript`. Structured
JSON events/results stay on stdout so they can still be copied or parsed.

To continuously test the ASR input path one utterance at a time, run:

```bash
PYTHONPATH=src .venv312/bin/python scripts/linux/stream_asr_pipeline.py
```

This loops until `Ctrl+C`, printing one JSON transcript event per VAD-detected
utterance. It does not call the LLM planner, robot bridge, or vision tools.

If a raw WAV is audible but the stream keeps printing `NO_SPEECH_DETECTED`,
bypass VAD and transcribe fixed-duration chunks:

```bash
PYTHONPATH=src .venv312/bin/python scripts/linux/stream_asr_pipeline.py \
  --capture-mode fixed \
  --listen-window 5 \
  --show-empty
```

Speak one sentence per 5-second window. This tests microphone + SenseVoice ASR
directly, without Silero.

To transcribe an already-recorded raw probe and inspect Silero's probability
scores on that same audio:

```bash
PYTHONPATH=src .venv312/bin/python scripts/linux/test_audio_input_pipeline.py \
  --mode asr \
  --audio-path logs/audio/raw_probe_YYYYMMDD_HHMMSS.wav \
  --probe-silero
```

The diagnostic scripts default to `--vad-threshold 0.55`, which is a normal
Silero starting point. The voice-command config uses `vad_post_roll_ms: 1000`
so a sentence closes after about one second of non-speech. Lower thresholds or
longer post-roll values are only for troubleshooting.

To test only VAD sentence separation, run:

```bash
PYTHONPATH=src .venv312/bin/python scripts/linux/stream_vad_pipeline.py
```

This prints `speech_started` when VAD decides a sentence began and
`speech_ended` when `post_roll_ms` of non-speech closes the sentence. It writes
one WAV per VAD-separated utterance under `logs/audio/`.

For a verbose 32 ms window-by-window view:

```bash
PYTHONPATH=src .venv312/bin/python scripts/linux/stream_vad_pipeline.py --print-windows
```

The full `listen-task` pipeline uses this VAD-separated utterance behavior. It
does not send fixed 5- or 10-second packs to ASR; fixed-window capture is only a
diagnostic mode in `stream_asr_pipeline.py --capture-mode fixed`.

Expected successful output looks like:

```json
{"event": "transcript", "text": "把红色方块放到第三个格子", "language": "zh"}
```

If the output repeats this pattern:

```json
{"event": "listening", "utterance_index": 1, "audio_path": "logs/audio/stream_asr_..._001.wav"}
{"event": "vad_error", "utterance_index": 1, "error": "NO_SPEECH_DETECTED"}
{"event": "listening", "utterance_index": 2, "audio_path": "logs/audio/stream_asr_..._002.wav"}
{"event": "vad_error", "utterance_index": 2, "error": "NO_SPEECH_DETECTED"}
```

the stream loop is working, but no sentence reached ASR. The failure point is:

```text
microphone/VAD stage
```

not SenseVoice. Run the raw microphone probe and speak during the recording:

```bash
PYTHONPATH=src .venv312/bin/python scripts/linux/test_audio_input_pipeline.py --mode raw --duration 5
```

Interpret the raw probe:

| Result | Meaning | Next step |
| --- | --- | --- |
| `rms` and `peak` near `0.0` | Python is receiving silence | Fix VM/Ubuntu mic passthrough, selected input device, mute state, or input volume |
| `rms`/`peak` clearly nonzero, but stream still says `NO_SPEECH_DETECTED` | Mic works, the extra RMS gate or VAD threshold is too strict | Set `--vad-min-rms 0.0`; lower `--vad-threshold` only if Silero probabilities are also low |
| VAD creates an utterance WAV but transcript text is empty | VAD works, ASR/model input is the issue | Test with `--show-empty`, inspect the WAV, and check SenseVoice model files |

If ASR consistently misses the first words, wait until the CLI prints
`Listening now...` before speaking and increase pre-roll:

```bash
PYTHONPATH=src .venv312/bin/python -m sensoragent.services.cli.main \
  listen-task \
  --config configs/audio_robot_sim.yaml \
  --planner llm \
  --duration 15 \
  --vad-pre-roll-ms 800 \
  --vad-post-roll-ms 1000
```

### `NO_SPEECH_DETECTED`

This means `SoundDeviceVadRecorder` opened the microphone stream and waited
until the duration limit, but no audio window passed both gates:

```text
Silero probability >= vad_threshold
RMS energy >= vad_min_rms
```

First try a more permissive one-off run:

```bash
PYTHONPATH=src .venv312/bin/python -m sensoragent.services.cli.main \
  listen-task \
  --config configs/audio_robot_sim.yaml \
  --planner llm \
  --duration 15 \
  --vad-pre-roll-ms 600 \
  --vad-threshold 0.20 \
  --vad-min-rms 0.0 \
  --vad-post-roll-ms 1000
```

If it still reports `NO_SPEECH_DETECTED`, verify the VM or host is exposing the
right microphone to Python:

```bash
.venv312/bin/python - <<'PY'
import numpy as np
import sounddevice as sd

print(sd.query_devices())
print("default device:", sd.default.device)
print("speak now for 3 seconds...")
audio = sd.rec(int(3 * 16000), samplerate=16000, channels=1, dtype="int16")
sd.wait()
samples = audio.astype("float32") / 32768.0
print("rms:", float(np.sqrt(np.mean(np.square(samples)))))
print("peak:", float(np.max(np.abs(samples))))
PY
```

An RMS near zero usually means the wrong input device is selected, the VM has no
microphone passthrough, or Ubuntu input volume is muted. If the probe fails with
`libportaudio.so.2`, install the PortAudio system library:

```bash
sudo apt update
sudo apt install -y libportaudio2
```

If VAD cuts off the end of speech, increase the post-roll:

```bash
PYTHONPATH=src .venv312/bin/python -m sensoragent.services.cli.main \
  listen-task \
  --config configs/audio_robot_sim.yaml \
  --planner llm \
  --duration 15 \
  --vad-post-roll-ms 3000
```

If background noise triggers false speech, raise the RMS gate:

```bash
--vad-min-rms 0.035
```

If quiet speech is missed, lower the VAD threshold slightly:

```bash
--vad-threshold 0.30
```
