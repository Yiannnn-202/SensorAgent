# TODO - ASR/TTS Integration

This file tracks the ASR + TTS integration work. The goal is to merge the existing ASR/TTS demo into SensorAgent as audio tools and optional audio skills, without breaking the current Agent framework.

## Goal

Integrate ASR and TTS as first-class Agent capabilities:

```text
audio.transcribe
audio.speak
optional audio skills / workflows
```

The integration should follow the current SensorAgent layering:

```text
external ASR/TTS service or local demo
→ integrations/audio.py
→ tools/audio/transcribe.py and tools/audio/speak.py
→ optional skills/audio.py
→ optional workflows
→ AgentRuntime / CLI / logs / tests
```

## Scope

SensorAgent should own:

```text
audio tool contracts
audio integration client
audio tool adapters
optional audio skills
config entries
tests and fixtures
Agent-side logs
```

SensorAgent should not own:

```text
large ASR/TTS model weights
hardware microphone setup
system audio driver setup
long-running production audio service deployment
```

If the old demo includes runtime/service code, keep only the reusable integration pieces or isolate the service under an adapter-friendly structure.

## Phase A0 - Review existing ASR/TTS demo

Goal: understand the old project before merging anything.

- [ ] Locate the old ASR/TTS demo files.
- [ ] Identify whether ASR is exposed as HTTP, WebSocket, CLI, local Python function, or process call.
- [ ] Identify whether TTS is exposed as HTTP, WebSocket, CLI, local Python function, or process call.
- [ ] Record ASR input format: audio file, bytes, microphone stream, text fixture, or other.
- [ ] Record ASR output format: text, confidence, language, timestamps, alternatives.
- [ ] Record TTS input format: text, voice, speed, language, play flag.
- [ ] Record TTS output format: audio path, bytes, playback status, duration.
- [ ] Identify old dependencies and model/data files.
- [ ] Decide what should be copied, rewritten, or discarded.
- [ ] Document findings in `docs/development/audio_integration.md`.

## Phase A1 - Audio contracts

Goal: define stable cross-module contracts before writing adapters.

- [ ] Add `contracts/tools/audio.transcribe.schema.json`.
- [ ] Add `contracts/tools/audio.speak.schema.json`.
- [ ] Define ASR error codes, e.g. `AUDIO_NOT_FOUND`, `TRANSCRIBE_FAILED`, `ASR_UNAVAILABLE`.
- [ ] Define TTS error codes, e.g. `SPEAK_FAILED`, `TTS_UNAVAILABLE`, `AUDIO_WRITE_FAILED`.
- [ ] Add examples for ASR input/output.
- [ ] Add examples for TTS input/output.
- [ ] Add contract tests using fixture payloads.
- [ ] Decide whether current `audio.mock_transcribe` contract remains separate or becomes a mock implementation of `audio.transcribe`.

## Phase A2 - Audio fixtures

Goal: create local test inputs without depending on live microphone or external services.

- [ ] Add small audio fixture under `tests/fixtures/audio/`.
- [ ] Add ASR expected response fixture under `tests/fixtures/responses/`.
- [ ] Add TTS expected response fixture under `tests/fixtures/responses/`.
- [ ] Ensure fixtures are small enough for Git.
- [ ] Do not commit large model weights or generated audio dumps.

## Phase A3 - Audio integration client

Goal: isolate external ASR/TTS service details from Agent tools.

- [ ] Add `src/sensoragent/integrations/audio.py`.
- [ ] Define `AudioClient` interface.
- [ ] Implement client for the old demo's actual interface.
- [ ] If old demo is HTTP-based, add methods such as `transcribe_file(...)` and `speak_text(...)`.
- [ ] If old demo is local Python-based, wrap it behind the same `AudioClient` interface.
- [ ] Add timeout handling.
- [ ] Convert external errors into typed integration errors.
- [ ] Add unit tests with mocked client behavior.

## Phase A4 - Audio tools

Goal: expose ASR/TTS to SensorAgent as normal tools.

- [ ] Add `src/sensoragent/tools/audio/transcribe.py`.
- [ ] Add `src/sensoragent/tools/audio/speak.py`.
- [ ] Implement `audio.transcribe` tool.
- [ ] Implement `audio.speak` tool.
- [ ] Ensure tools return `ToolResult`.
- [ ] Ensure tools pass contract validation.
- [ ] Add tool metadata: version, tags, timeout, retry policy.
- [ ] Add unit tests for success and failure paths.
- [ ] Add e2e tests using fake or local audio integration.

## Phase A5 - Config integration

Goal: enable ASR/TTS through config instead of hard-coded registration.

- [ ] Add `configs/audio_mock.yaml` or extend `configs/mock.yaml` if appropriate.
- [ ] Add `configs/audio_dev.yaml` for real/local demo ASR/TTS.
- [ ] Add audio integration config fields:
  ```yaml
  integrations:
    audio:
      protocol: http
      base_url: http://localhost:7004
  ```
- [ ] Register `audio.transcribe` and `audio.speak` through config.
- [ ] Add environment variable overrides if needed.
- [ ] Update `build_agent` bootstrap to create audio integration-backed tools when enabled.

## Phase A6 - Audio skills

Goal: add optional higher-level skills only after tools are stable.

- [ ] Decide whether ASR/TTS need skills or only tools.
- [ ] If needed, add `src/sensoragent/skills/audio.py`.
- [ ] Add `audio.listen_command` skill:
  ```text
  audio.transcribe → normalized text
  ```
- [ ] Add `audio.report_result` skill:
  ```text
  summarize task result → audio.speak
  ```
- [ ] Add tests for audio skills.

## Phase A7 - Audio workflow

Goal: prove a local speech-to-Agent path can run inside SensorAgent.

- [ ] Add ActionList workflow:
  ```text
  audio.transcribe
  → run planner / task
  → audio.speak
  ```
- [ ] Alternatively, keep ASR before Agent entry and TTS after Agent result if that is simpler.
- [ ] Add CLI command for audio demo if useful.
- [ ] Add e2e test with audio fixture and fake TTS output.

## Phase A8 - CLI and documentation

Goal: make audio integration usable by teammates.

- [ ] Add CLI command for ASR-only test.
- [ ] Add CLI command for TTS-only test.
- [ ] Add CLI command for full audio mock demo if useful.
- [ ] Add `docs/development/audio_integration.md`.
- [ ] Add `docs/development/tests/audio_pipeline.md`.
- [ ] Update root `README.md` with audio test commands after the integration is usable.
- [ ] Update `docs/README.md` with audio docs.

## Phase A9 - Cleanup and boundary check

Goal: keep the repository clean and aligned with SensorAgent's role.

- [ ] Remove copied old demo files that are not used.
- [ ] Keep large model weights out of Git.
- [ ] Keep generated audio outputs under ignored `logs/` or temporary directories.
- [ ] Confirm ASR/TTS code lives behind `integrations/` and `tools/`.
- [ ] Confirm workflows depend on `audio.transcribe` / `audio.speak`, not old demo internals.
- [ ] Run all tests.

## Open decisions

- [ ] Should ASR happen before SensorAgent receives user input, or should ASR be an Agent tool?
- [ ] Should TTS be called by SensorAgent, frontend, or a separate interaction module?
- [ ] Will the old ASR/TTS demo run as a local service or be imported as Python code?
- [ ] What is the maximum acceptable latency for ASR and TTS tools?
- [ ] What audio formats should be supported first: WAV file, bytes, microphone stream?

## Recommended first implementation path

Start small:

```text
1. Review old demo.
2. Define audio.transcribe and audio.speak contracts.
3. Add fake AudioClient.
4. Add audio.transcribe and audio.speak tools using the fake client.
5. Add tests.
6. Replace fake client with old demo adapter.
```

Do not integrate live microphone, large models, or playback automation until the tool contracts and fake-client tests are stable.
