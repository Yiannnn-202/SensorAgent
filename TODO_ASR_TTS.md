# TODO - ASR/TTS Integration

This file tracks the ASR + TTS migration from the existing Radish project into SensorAgent.

The goal is **not** to merge Radish. The goal is to extract only the reusable ASR/TTS capability and expose it through the current SensorAgent architecture:

```text
Radish sound / tts reusable logic
→ non-ROS audio integration
→ audio tools
→ optional audio skills/workflows
→ AgentRuntime / CLI / logs / tests
```

## Confirmed requirements

- [x] Only Radish sound/TTS-related parts are in scope.
- [x] Radish robot, ROS 2, base, arm, brain, web UI, perception, and launch content are out of scope.
- [x] SensorAgent should not depend on a ROS 2 environment for ASR/TTS.
- [x] Local model calls are acceptable.
- [x] Model weights must live under a root-level model directory and must not be uploaded to GitHub.
- [x] ASR/TTS should become normal SensorAgent capabilities through tools and integrations.
- [x] YAMNet bell detection is out of scope and should not be migrated.

## Target architecture

```text
models/                         # local model files, ignored by Git
src/sensoragent/integrations/    # local/service audio client
src/sensoragent/tools/audio/      # audio.transcribe / audio.speak tools
contracts/tools/                 # audio tool input/output contracts
configs/                         # audio local/mock configs
tests/                           # fake-client and fixture tests
docs/development/                # migration notes and usage docs
```

## Phase A0 - Inspect Radish audio content

Goal: identify exactly what can be reused.

- [x] Locate the newly added Radish project in the repository.
- [x] Inspect only Radish sound/TTS-related paths, expected candidates:
  ```text
  Radish/service/sound/
  Radish/service/tts/
  Radish/src/sound/
  ```
- [x] Identify which files are ASR logic.
- [x] Identify which files are TTS logic.
- [x] Identify which files are only HTTP/service wrappers.
- [x] Identify which files are ROS 2 wrappers and should not be merged.
- [x] Identify model paths expected by the old project.
- [x] Identify old dependencies needed for ASR/TTS.
- [x] Decide which code should be copied, rewritten, wrapped, or discarded.
- [x] Record findings in `docs/development/audio_integration.md`.

## Phase A1 - Model storage policy

Goal: prepare local model storage without committing model weights.

- [x] Add root-level `models/` directory for local ASR/TTS model files.
- [x] Update `.gitignore` to ignore `models/`.
- [x] Add documentation explaining expected model layout:
  ```text
  models/asr/
  models/tts/
  ```
- [x] Document how to obtain or place required model files.
- [x] Confirm no model weights, generated audio dumps, or large artifacts are tracked by Git.

## Phase A2 - Audio contracts

Goal: define stable SensorAgent-side audio tool contracts before implementation.

- [x] Add `contracts/tools/audio.transcribe.schema.json`.
- [x] Add `contracts/tools/audio.speak.schema.json`.
- [x] Define ASR input fields:
  ```text
  audio_path
  language
  ```
- [x] Define ASR output fields:
  ```text
  text
  confidence
  language
  ```
- [x] Define TTS input fields:
  ```text
  text
  voice
  output_path
  play
  ```
- [x] Define TTS output fields:
  ```text
  spoken
  audio_path
  duration_ms
  ```
- [x] Define ASR error codes:
  ```text
  AUDIO_NOT_FOUND
  TRANSCRIBE_FAILED
  ASR_MODEL_MISSING
  ASR_UNAVAILABLE
  ```
- [x] Define TTS error codes:
  ```text
  SPEAK_FAILED
  TTS_MODEL_MISSING
  AUDIO_WRITE_FAILED
  TTS_UNAVAILABLE
  ```
- [x] Add contract tests for audio input/output payloads.

## Phase A3 - Audio fixtures

Goal: make audio tests runnable without live microphone or real services.

- [x] Add a small WAV fixture under `tests/fixtures/audio/`.
- [x] Add expected ASR response fixture under `tests/fixtures/responses/`.
- [x] Add expected TTS response fixture under `tests/fixtures/responses/`.
- [x] Ensure fixtures are small and safe to commit.
- [x] Keep generated audio outputs under ignored `logs/audio/` or temp directories.

## Phase A4 - Audio integration abstraction

Goal: isolate old demo details behind a clean SensorAgent integration layer.

- [x] Add `src/sensoragent/integrations/audio.py`.
- [x] Define an `AudioClient` interface with methods such as:
  ```text
  transcribe_file(audio_path, language)
  speak_text(text, output_path, voice, play)
  ```
- [x] Add `FakeAudioClient` for tests.
- [x] Add typed audio integration errors.
- [x] Add unit tests for `FakeAudioClient`.
- [x] Do not import ROS 2 packages in this layer.

## Phase A5 - Audio tools

Goal: expose ASR/TTS to SensorAgent as normal tools.

- [x] Add `src/sensoragent/tools/audio/transcribe.py`.
- [x] Add `src/sensoragent/tools/audio/speak.py`.
- [x] Implement `audio.transcribe` using `AudioClient`.
- [x] Implement `audio.speak` using `AudioClient`.
- [x] Add tool metadata: version, tags, timeout, retry.
- [x] Ensure tool input/output passes contracts.
- [x] Add unit tests for success paths.
- [ ] Add unit tests for failure paths.
- [x] Add e2e test for fake audio tools.

## Phase A6 - Config integration

Goal: enable ASR/TTS through configuration.

- [x] Add `configs/audio_mock.yaml` for fake audio client tests.
- [x] Add `configs/audio_local.yaml` for local Radish-derived models.
- [x] Add audio integration config fields, e.g.:
  ```yaml
  integrations:
    audio:
      backend: local
      asr_model_dir: models/asr
      tts_model_dir: models/tts
  ```
- [x] Register `audio.transcribe` and `audio.speak` from config.
- [ ] Keep existing `audio.mock_transcribe` available for old mock tests if still useful.
- [x] Update bootstrap to construct audio integration-backed tools when enabled.

## Phase A7 - Radish local implementation adapter

Goal: wrap the old local model calls without ROS 2.

- [x] Extract reusable ASR logic from Radish sound service.
- [x] Extract reusable TTS logic from Radish TTS service.
- [x] Remove or bypass ROS 2 dependencies.
- [x] Remove old project launch/service assumptions.
- [x] Implement `LocalAudioClient`.
- [x] Read model paths from config.
- [ ] Add local-only tests that skip gracefully when models are missing.
- [ ] Document local setup requirements.

## Phase A8 - Optional audio skills

Goal: add higher-level audio skills only if they simplify workflows.

- [ ] Decide whether ASR/TTS need skills or only tools.
- [ ] If needed, add `src/sensoragent/skills/audio.py`.
- [ ] Consider `audio.listen_command`:
  ```text
  audio.transcribe → normalized text
  ```
- [ ] Consider `audio.report_result`:
  ```text
  task result summary → audio.speak
  ```
- [ ] Add tests if audio skills are added.

## Phase A9 - Optional audio workflow

Goal: prove a speech-to-Agent path if needed.

- [ ] Decide whether ASR should happen before SensorAgent receives input or inside a workflow.
- [ ] If inside SensorAgent, add an ActionList:
  ```text
  audio.transcribe
  → run planner / task
  → audio.speak
  ```
- [ ] Add e2e test using audio fixture and fake TTS output.
- [ ] Do not require microphone access in default tests.

## Phase A10 - CLI and documentation

Goal: make ASR/TTS integration usable by teammates.

- [ ] Add CLI command for ASR-only test.
- [ ] Add CLI command for TTS-only test.
- [ ] Add CLI command for full audio demo only if useful.
- [ ] Add `docs/development/audio_integration.md`.
- [ ] Add `docs/development/tests/audio_pipeline.md`.
- [ ] Update root `README.md` with audio commands after they are usable.
- [ ] Update `docs/README.md` with audio docs.

## Phase A11 - Cleanup and boundary check

Goal: ensure SensorAgent remains an Agent-side module.

- [ ] Remove unused copied Radish files.
- [ ] Confirm no ROS 2 dependency remains in ASR/TTS integration.
- [ ] Confirm no model weights are tracked by Git.
- [ ] Confirm generated audio outputs are ignored.
- [ ] Confirm workflows depend on `audio.transcribe` / `audio.speak`, not old Radish internals.
- [ ] Run all tests.

## Phase A12 - Microphone to Agent pipeline

Goal: make microphone input a SensorAgent-native streaming/listening capability. Radish may be used as reference, but the final implementation should not depend on the Radish sound service.

Target long-term chain:

```text
microphone
→ VAD
→ ASR
→ transcript text
→ LLMPlanner
→ AgentPlan
→ ActionList / DecisionTree
→ task result
→ optional TTS response
```

### A12.1 - Listen-once MVP

Goal: prove the full microphone-to-Agent path with fixed-duration recording before implementing real streaming VAD.

- [x] Add a microphone recorder abstraction.
- [x] Use a simple fixed-duration recording first, e.g. 5 seconds.
- [x] Save recorded audio to `logs/audio/`.
- [x] Ensure recorded audio is 16 kHz, mono, 16-bit PCM WAV before ASR.
- [x] Add `audio.listen_transcribe` contract.
- [x] Add `audio.listen_transcribe` tool.
- [x] Implement the tool using microphone recording + `audio.transcribe`.
- [x] Add CLI command:
  ```text
  listen-task
  ```
- [x] `listen-task` should:
  ```text
  record microphone
  → transcribe
  → run Agent task with --planner llm
  → print task result
  ```
- [x] Add fake recorder tests that do not require real microphone access.
- [x] Add manual test documentation.

### A12.2 - Simple local VAD

Goal: replace fixed-duration recording with simple speech-boundary detection.

- [ ] Add RMS-based VAD.
- [ ] Start recording when energy crosses threshold.
- [ ] Stop after post-speech silence.
- [ ] Add max utterance duration.
- [ ] Save utterance WAV to `logs/audio/`.
- [ ] Add tests with synthetic audio fixtures.

### A12.3 - Silero VAD / streaming pipeline

Goal: replace simple RMS VAD with a model-backed streaming VAD if needed.

- [ ] Decide whether Silero VAD is required.
- [ ] If yes, add VAD model path under `models/asr/vad/`.
- [ ] Add streaming frame pipeline.
- [ ] Emit events:
  ```text
  speech_started
  speech_ended
  transcript_ready
  task_started
  task_finished
  ```
- [ ] Keep WebSocket/UI event streaming compatible with Agent event stream.

### A12.4 - Optional TTS response

Goal: optionally speak Agent results after task completion.

- [ ] Decide whether TTS should be called by SensorAgent, frontend, or another interaction module.
- [ ] If SensorAgent owns it, add optional `--speak` flag to `listen-task`.
- [ ] Use `audio.speak` to generate response audio.
- [ ] Keep playback disabled by default; generate audio file first.

## Open decisions

- [ ] Should ASR happen before SensorAgent receives user input, or should ASR be an Agent tool?
- [ ] Should TTS be called by SensorAgent, frontend, or a separate interaction module?
- [ ] Will the old Radish demo run as a local service or be imported as Python code?
- [ ] What audio formats should be supported first: WAV file, bytes, microphone stream?
- [ ] Should TTS generate files only, or also play audio through the system device?
- [x] Radish service should not be a runtime dependency of the final microphone-to-Agent path.

## Recommended first implementation path

Start small:

```text
1. Inspect Radish sound/TTS files.
2. Define audio.transcribe and audio.speak contracts.
3. Add FakeAudioClient.
4. Add audio.transcribe and audio.speak tools using FakeAudioClient.
5. Add tests.
6. Add LocalAudioClient by extracting old Radish model logic.
```

Do not integrate live microphone, playback automation, large model files, or ROS 2 wrappers until the contracts and fake-client tests are stable.
