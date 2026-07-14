"""Audio ActionList definitions."""

from sensoragent.schemas import ActionList, ActionStep, ActionStepKind


def build_voice_command_ack_actionlist() -> ActionList:
  """Build an ActionList that listens for a voice command and acknowledges it."""

  return ActionList(
    name="audio.voice_command_ack_actionlist",
    description="Listen for one operator command and acknowledge it by speech.",
    inputs={"duration_seconds": "number", "language": "string"},
    tags=("audio", "voice-command"),
    steps=[
      ActionStep(
        name="listen_command",
        kind=ActionStepKind.SKILL,
        target="audio.listen_command",
        input={
          "duration_seconds": "{{ duration_seconds }}",
          "language": "{{ language }}",
        },
        save_as="command",
      ),
      ActionStep(
        name="announce_command",
        kind=ActionStepKind.SKILL,
        target="audio.announce",
        input={
          "text": "{{ command.text }}",
          "play": False,
        },
        save_as="announcement",
      ),
    ],
  )
