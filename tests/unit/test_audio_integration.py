"""Unit tests for audio integration clients and tools."""

from __future__ import annotations

import sys
import tempfile
import wave
from pathlib import Path
from unittest import TestCase, skipUnless

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
  sys.path.insert(0, str(SRC))

from sensoragent.agent import build_agent_from_config
from sensoragent.integrations import FakeAudioClient, FakeMicrophoneRecorder, LocalAudioClient
from sensoragent.integrations.audio import AudioError, _write_wav
from sensoragent.integrations.microphone import MicrophoneError
from sensoragent.integrations.vad import SoundDeviceVadRecorder
from sensoragent.schemas import ToolCall, TraceContext
from sensoragent.tools.audio import AudioSpeakTool, AudioTranscribeTool
from sensoragent.tools.audio import AudioListenTranscribeTool
from sensoragent.tools.audio import AudioListenVadTranscribeTool

try:
  import onnxruntime  # noqa: F401

  HAS_ONNXRUNTIME = True
except Exception:
  HAS_ONNXRUNTIME = False


class AudioIntegrationTest(TestCase):
  def test_fake_audio_client_transcribes_and_speaks(self) -> None:
    client = FakeAudioClient()

    transcript = client.transcribe_file("tests/fixtures/audio/command.wav", "zh")
    speech = client.speak_text("任务已完成", "logs/audio/fake.wav")

    self.assertEqual(transcript["language"], "zh")
    self.assertIn("银色滚柱", transcript["text"])
    self.assertTrue(speech["spoken"])
    self.assertEqual(speech["audio_path"], "logs/audio/fake.wav")

  def test_audio_transcribe_tool_uses_client(self) -> None:
    tool = AudioTranscribeTool(FakeAudioClient())

    result = tool.run(
      ToolCall(
        tool="audio.transcribe",
        input={"audio_path": "tests/fixtures/audio/command.wav", "language": "zh"},
        trace=TraceContext(),
      )
    )

    self.assertTrue(result.success)
    self.assertEqual(result.output["language"], "zh")

  def test_audio_listen_transcribe_tool_records_and_transcribes(self) -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
      output_path = str(Path(temp_dir) / "listen.wav")
      tool = AudioListenTranscribeTool(FakeMicrophoneRecorder(), FakeAudioClient())

      result = tool.run(
        ToolCall(
          tool="audio.listen_transcribe",
          input={
            "duration_seconds": 1,
            "language": "zh",
            "output_path": output_path,
          },
          trace=TraceContext(),
        )
      )

      self.assertTrue(result.success)
      self.assertEqual(result.output["audio_path"], output_path)
      self.assertIn("银色滚柱", result.output["text"])
      self.assertTrue(Path(output_path).exists())

  def test_audio_listen_vad_transcribe_tool_segments_before_asr(self) -> None:
    class CapturingAudioClient(FakeAudioClient):
      def __init__(self) -> None:
        self.audio_path = ""

      def transcribe_file(self, audio_path: str, language: str = "zh") -> dict:
        self.audio_path = audio_path
        return super().transcribe_file(audio_path, language)

    class FakeVadSegmenter:
      def segment_wav(self, audio_path: str, output_path: str | None = None) -> dict:
        destination = Path(output_path or audio_path)
        destination.write_bytes(Path(audio_path).read_bytes())
        return {
          "audio_path": str(destination),
          "start_ms": 100,
          "end_ms": 900,
          "duration_ms": 800,
          "sample_rate": 16000,
        }

    with tempfile.TemporaryDirectory() as temp_dir:
      output_path = str(Path(temp_dir) / "listen.wav")
      client = CapturingAudioClient()
      tool = AudioListenVadTranscribeTool(
        FakeMicrophoneRecorder(),
        client,
        FakeVadSegmenter(),
      )

      result = tool.run(
        ToolCall(
          tool="audio.listen_vad_transcribe",
          input={
            "duration_seconds": 1,
            "language": "zh",
            "output_path": output_path,
          },
          trace=TraceContext(),
        )
      )

      self.assertTrue(result.success)
      self.assertTrue(client.audio_path.endswith("_utterance.wav"))
      self.assertEqual(result.output["vad"]["source"], "silero")
      self.assertEqual(result.output["vad"]["duration_ms"], 800)

  def test_audio_listen_vad_transcribe_tool_uses_realtime_vad_recording(self) -> None:
    class RealtimeVadRecorder:
      def record_once(
        self,
        duration_seconds: float,
        output_path: str,
        sample_rate: int = 16000,
      ) -> dict:
        del duration_seconds
        FakeMicrophoneRecorder().record_once(1, output_path, sample_rate)
        return {
          "audio_path": output_path,
          "duration_ms": 1200,
          "sample_rate": sample_rate,
          "vad": {
            "enabled": True,
            "source": "silero_realtime",
            "start_ms": 120,
            "end_ms": 1320,
            "duration_ms": 1200,
          },
        }

    class FailingSegmenter:
      def segment_wav(self, audio_path: str, output_path: str | None = None) -> dict:
        raise AssertionError("offline segmenter should not run")

    with tempfile.TemporaryDirectory() as temp_dir:
      output_path = str(Path(temp_dir) / "listen.wav")
      tool = AudioListenVadTranscribeTool(
        RealtimeVadRecorder(),
        FakeAudioClient(),
        FailingSegmenter(),
      )

      result = tool.run(
        ToolCall(
          tool="audio.listen_vad_transcribe",
          input={"duration_seconds": 1, "language": "zh", "output_path": output_path},
          trace=TraceContext(),
        )
      )

      self.assertTrue(result.success)
      self.assertEqual(result.output["vad"]["source"], "silero_realtime")
      self.assertEqual(result.output["vad"]["start_ms"], 120)

  @skipUnless(HAS_ONNXRUNTIME, "onnxruntime is required for VAD recorder tests")
  def test_sounddevice_vad_recorder_supports_runtime_overrides(self) -> None:
    recorder = SoundDeviceVadRecorder(
      model_path=str(ROOT / "models" / "asr" / "vad" / "silero_vad.onnx"),
      threshold=0.3,
      min_rms=0.02,
      pre_roll_ms=120,
      post_roll_ms=1800,
      tail_padding_ms=700,
    )

    overridden = recorder.with_overrides(
      {"min_rms": 0.04, "post_roll_ms": 3000, "tail_padding_ms": 500}
    )

    self.assertEqual(overridden._min_rms, 0.04)
    self.assertEqual(overridden._post_roll_ms, 3000)
    self.assertEqual(overridden._tail_padding_ms, 500)
    self.assertEqual(overridden._pre_roll_ms, 120)

  def test_audio_speak_tool_uses_client(self) -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
      output_path = str(Path(temp_dir) / "speech.wav")
      tool = AudioSpeakTool(FakeAudioClient())

      result = tool.run(
        ToolCall(
          tool="audio.speak",
          input={"text": "任务已完成", "output_path": output_path, "play": False},
          trace=TraceContext(),
        )
      )

      self.assertTrue(result.success)
      self.assertEqual(result.output["audio_path"], output_path)

  def test_local_audio_client_detects_melo_tts_assets(self) -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
      model_dir = Path(temp_dir) / "vits-melo-tts-zh_en"
      dict_dir = model_dir / "dict"
      dict_dir.mkdir(parents=True)
      for filename in (
        "model.onnx",
        "tokens.txt",
        "lexicon.txt",
        "date.fst",
        "number.fst",
      ):
        (model_dir / filename).write_text("placeholder", encoding="utf-8")

      client = LocalAudioClient(tts_model_dir=temp_dir)
      assets = client._find_melo_vits_assets()

      self.assertIsNotNone(assets)
      model_path, tokens_path, lexicon_path, rule_fsts, voice_name = assets
      self.assertEqual(model_path, model_dir / "model.onnx")
      self.assertEqual(tokens_path, model_dir / "tokens.txt")
      self.assertEqual(lexicon_path, model_dir / "lexicon.txt")
      self.assertIn("date.fst", rule_fsts)
      self.assertIn("number.fst", rule_fsts)
      self.assertEqual(voice_name, "vits-melo-tts-zh_en")

  def test_local_audio_client_prefers_fanchen_tts_assets(self) -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
      model_dir = Path(temp_dir) / "vits-zh-hf-fanchen-wnj"
      model_dir.mkdir(parents=True)
      for filename in (
        "vits-zh-hf-fanchen-wnj.onnx",
        "tokens.txt",
        "lexicon.txt",
        "date.fst",
        "number.fst",
      ):
        (model_dir / filename).write_text("placeholder", encoding="utf-8")

      client = LocalAudioClient(tts_model_dir=temp_dir)
      assets = client._find_zh_vits_assets()

      self.assertIsNotNone(assets)
      model_path, tokens_path, lexicon_path, rule_fsts, voice_name = assets
      self.assertEqual(model_path, model_dir / "vits-zh-hf-fanchen-wnj.onnx")
      self.assertEqual(tokens_path, model_dir / "tokens.txt")
      self.assertEqual(lexicon_path, model_dir / "lexicon.txt")
      self.assertIn("date.fst", rule_fsts)
      self.assertIn("number.fst", rule_fsts)
      self.assertEqual(voice_name, "vits-zh-hf-fanchen-wnj")

  def test_tts_wav_writer_preserves_float_sample_scale(self) -> None:
    import numpy as np

    with tempfile.TemporaryDirectory() as temp_dir:
      output_path = Path(temp_dir) / "quiet.wav"
      _write_wav(output_path, np.array([0.0, 0.5, -0.5], dtype=np.float32), 16000)

      with wave.open(str(output_path), "rb") as wav:
        audio = np.frombuffer(wav.readframes(wav.getnframes()), dtype=np.int16)

      self.assertGreaterEqual(int(np.max(np.abs(audio))), 16000)
      self.assertLess(int(np.max(np.abs(audio))), 17000)

  def test_audio_mock_config_registers_audio_tools(self) -> None:
    bundle = build_agent_from_config(ROOT / "configs" / "audio_mock.yaml")

    self.assertIn("audio.transcribe", bundle.tool_registry.names())
    self.assertIn("audio.speak", bundle.tool_registry.names())


class _FailingAudioClient(FakeAudioClient):
  """Fake client whose transcribe/speak raise a configured AudioError."""

  def __init__(self, *, transcribe_error: str | None = None, speak_error: str | None = None) -> None:
    super().__init__()
    self._transcribe_error = transcribe_error
    self._speak_error = speak_error

  def transcribe_file(self, audio_path: str, language: str = "zh") -> dict:
    if self._transcribe_error is not None:
      raise AudioError(self._transcribe_error)
    return super().transcribe_file(audio_path, language)

  def speak_text(self, text: str, output_path: str | None = None, voice: str = "default", play: bool = False) -> dict:
    if self._speak_error is not None:
      raise AudioError(self._speak_error)
    return super().speak_text(text, output_path, voice, play)


class _FailingMicrophoneRecorder:
  """Recorder that always raises MicrophoneError."""

  def record_once(self, duration_seconds: float, output_path: str, sample_rate: int = 16000) -> dict:
    raise MicrophoneError("No microphone device available")


class AudioFailurePathTest(TestCase):
  """Tools must swallow integration errors and return a failed ToolResult."""

  def test_transcribe_returns_failure_when_audio_path_missing(self) -> None:
    tool = AudioTranscribeTool(FakeAudioClient())

    result = tool.run(ToolCall(tool="audio.transcribe", input={}, trace=TraceContext()))

    self.assertFalse(result.success)
    self.assertIn("audio_path", result.error)

  def test_transcribe_returns_failure_on_audio_error(self) -> None:
    tool = AudioTranscribeTool(
      _FailingAudioClient(transcribe_error="ASR service timed out")
    )

    result = tool.run(
      ToolCall(
        tool="audio.transcribe",
        input={"audio_path": "tests/fixtures/audio/command.wav", "language": "zh"},
        trace=TraceContext(),
      )
    )

    self.assertFalse(result.success)
    self.assertIn("ASR service timed out", result.error)

  def test_speak_returns_failure_when_text_missing(self) -> None:
    tool = AudioSpeakTool(FakeAudioClient())

    result = tool.run(ToolCall(tool="audio.speak", input={}, trace=TraceContext()))

    self.assertFalse(result.success)
    self.assertIn("text", result.error)

  def test_speak_returns_failure_on_audio_error(self) -> None:
    tool = AudioSpeakTool(_FailingAudioClient(speak_error="TTS model not loaded"))

    result = tool.run(
      ToolCall(
        tool="audio.speak",
        input={"text": "任务完成", "output_path": "logs/audio/x.wav", "play": False},
        trace=TraceContext(),
      )
    )

    self.assertFalse(result.success)
    self.assertIn("TTS model not loaded", result.error)

  def test_listen_transcribe_returns_failure_on_microphone_error(self) -> None:
    tool = AudioListenTranscribeTool(_FailingMicrophoneRecorder(), FakeAudioClient())

    result = tool.run(
      ToolCall(
        tool="audio.listen_transcribe",
        input={"duration_seconds": 1, "language": "zh"},
        trace=TraceContext(),
      )
    )

    self.assertFalse(result.success)
    self.assertIn("No microphone device", result.error)

  def test_listen_transcribe_returns_failure_on_transcribe_error(self) -> None:
    # Recording succeeds but the downstream ASR call fails.
    tool = AudioListenTranscribeTool(
      FakeMicrophoneRecorder(),
      _FailingAudioClient(transcribe_error="ASR connection refused"),
    )

    with tempfile.TemporaryDirectory() as temp_dir:
      result = tool.run(
        ToolCall(
          tool="audio.listen_transcribe",
          input={"duration_seconds": 1, "language": "zh", "output_path": str(Path(temp_dir) / "l.wav")},
          trace=TraceContext(),
        )
      )

    self.assertFalse(result.success)
    self.assertIn("ASR connection refused", result.error)

  def test_listen_vad_transcribe_returns_failure_on_microphone_error(self) -> None:
    tool = AudioListenVadTranscribeTool(
      _FailingMicrophoneRecorder(), FakeAudioClient(), None
    )

    result = tool.run(
      ToolCall(
        tool="audio.listen_vad_transcribe",
        input={"duration_seconds": 1, "language": "zh"},
        trace=TraceContext(),
      )
    )

    self.assertFalse(result.success)
    self.assertIn("No microphone device", result.error)

  def test_listen_vad_transcribe_returns_failure_on_invalid_vad_config(self) -> None:
    # A non-object vad value must be rejected before any recording happens.
    tool = AudioListenVadTranscribeTool(
      FakeMicrophoneRecorder(), FakeAudioClient(), None
    )

    result = tool.run(
      ToolCall(
        tool="audio.listen_vad_transcribe",
        input={"duration_seconds": 1, "language": "zh", "vad": "not-an-object"},
        trace=TraceContext(),
      )
    )

    self.assertFalse(result.success)
    self.assertIn("vad", result.error)
