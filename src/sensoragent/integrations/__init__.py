"""Adapters for external team services and runtimes."""

from sensoragent.integrations.llm import (
  LlmConfig,
  LlmError,
  OpenAICompatibleClient,
  load_llm_config_from_env,
)
from sensoragent.integrations.microphone import (
  FakeMicrophoneRecorder,
  MicrophoneError,
  MicrophoneRecorder,
  SoundDeviceRecorder,
)
from sensoragent.integrations.vad import (
  SileroVadSegmenter,
  SoundDeviceVadRecorder,
  VadError,
  VadSegmenter,
)
from sensoragent.integrations.audio import (
  AudioClient,
  AudioError,
  AudioInputError,
  AudioModelError,
  FakeAudioClient,
  LocalAudioClient,
)

__all__ = [
  "AudioClient",
  "AudioError",
  "AudioInputError",
  "AudioModelError",
  "FakeAudioClient",
  "FakeMicrophoneRecorder",
  "LlmConfig",
  "LlmError",
  "LocalAudioClient",
  "MicrophoneError",
  "MicrophoneRecorder",
  "OpenAICompatibleClient",
  "SileroVadSegmenter",
  "SoundDeviceVadRecorder",
  "SoundDeviceRecorder",
  "VadError",
  "VadSegmenter",
  "load_llm_config_from_env",
]
