"""Audio skills for command intake and spoken feedback."""

from __future__ import annotations

from sensoragent.schemas import SkillCall, SkillResult, SkillSpec
from sensoragent.skills.base import SkillContext


class AudioListenCommandSkill:
  """Listen for one operator command and return normalized command text."""

  spec = SkillSpec(
    name="audio.listen_command",
    description="Listen for one spoken operator command using audio tools.",
    tags=("audio", "voice-command"),
  )

  def run(self, call: SkillCall, context: SkillContext) -> SkillResult:
    tool_name = str(call.input.get("tool", "audio.listen_vad_transcribe"))
    listen_input = {}
    for field in ("duration_seconds", "sample_rate", "language", "output_path", "vad"):
      if field in call.input:
        listen_input[field] = call.input[field]

    result = context.tool_runtime.invoke(tool_name, listen_input, call.trace)
    if not result.success or not result.output:
      return SkillResult(skill=self.spec.name, success=False, error=result.error)

    text = str(result.output.get("text", "")).strip()
    if not text:
      return SkillResult(skill=self.spec.name, success=False, error="NO_SPEECH_COMMAND")

    return SkillResult(
      skill=self.spec.name,
      success=True,
      output={
        "text": text,
        "command_text": text,
        "language": result.output.get("language", ""),
        "confidence": result.output.get("confidence", 0.0),
        "audio_path": result.output.get("audio_path", ""),
        "transcript": result.output,
      },
    )


class AudioAnnounceSkill:
  """Speak a task-facing message through the configured TTS tool."""

  spec = SkillSpec(
    name="audio.announce",
    description="Speak a task status or feedback message using audio tools.",
    tags=("audio", "tts", "feedback"),
  )

  _DEFAULT_MESSAGES = {
    "task_started": "任务已开始",
    "task_success": "任务已完成",
    "task_failed": "任务执行失败",
    "command_not_understood": "没有听清指令，请再说一遍",
  }

  def run(self, call: SkillCall, context: SkillContext) -> SkillResult:
    kind = str(call.input.get("kind", "custom"))
    text = str(call.input.get("text") or self._DEFAULT_MESSAGES.get(kind, "")).strip()
    if not text:
      return SkillResult(skill=self.spec.name, success=False, error="Missing field: text")

    speak_input = {"text": text}
    for field in ("voice", "output_path", "play"):
      if field in call.input:
        speak_input[field] = call.input[field]

    result = context.tool_runtime.invoke("audio.speak", speak_input, call.trace)
    if not result.success or not result.output:
      return SkillResult(skill=self.spec.name, success=False, error=result.error)

    output = dict(result.output)
    output["text"] = text
    output["kind"] = kind
    return SkillResult(skill=self.spec.name, success=True, output=output)
