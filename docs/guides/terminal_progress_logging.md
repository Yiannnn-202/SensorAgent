# Terminal Progress Logging Guide

Use this style when a command runs a multi-stage pipeline and users need to see
what is happening live.

## Goal

Print concise human-readable progress to stderr while keeping structured JSON on
stdout.

This lets operators watch the system:

```text
[listen] config=configs/audio_robot_sim.yaml planner=llm
Listening now. Speak one complete command after this line...
[audio] transcribed 4200 ms text="把红色方块放到第三个格子，并用视觉确认"
[agent] planning from transcript text="把红色方块放到第三个格子，并用视觉确认"
[agent] execute industrial.recovery_pick_place_tree
[tree] node capture_initial kind=tool
[tool] start vision.capture_frame
[tool] ok vision.capture_frame error=None
[tree] node detect_object kind=tool
[tool] start vision.open_vocab_detect
[tool] ok vision.open_vocab_detect error=None
[tree] node plan_pick kind=tool
[tool] start robot.plan_top_down_pick
```

while scripts can still parse the final stdout JSON.

## Rules

1. Progress logs go to `stderr`, not `stdout`.
2. Keep each line short and stage-prefixed: `[audio]`, `[vad]`, `[asr]`,
   `[agent]`, `[tree]`, `[tool]`, `[skill]`, `[robot]`, `[vision]`.
3. Print start and finish for long operations.
4. Include the selected target, status, and error when relevant.
5. Do not print secrets, API keys, full prompts, or huge payloads.
6. Keep machine-readable JSON events/results on `stdout`.

## Python helper pattern

For standalone scripts:

```python
import sys


def _progress(message: str) -> None:
  print(message, file=sys.stderr, flush=True)


_progress("[vad] waiting for utterance threshold=0.55 post_roll=1000ms")
_progress("[asr] transcript text=\"把红色方块放到第三个格子\"")
```

For SensorAgent runtimes, prefer the shared `TaskLogger(console=True)` path so
Tool, Skill, ActionList, DecisionTree, and Agent events all use one formatter.

## Good examples

```text
[audio] listening utterance=1 path=logs/audio/listen_vad_...
[vad] speech started start_ms=0 prob=0.998 rms=0.0102
[vad] speech ended utterance=1 reason=post_roll_silence duration=4300ms
[asr] transcribing utterance=1
[asr] transcript utterance=1 text="把红色方块放到第三个格子，并用视觉确认"
[agent] execute industrial.recovery_pick_place_tree
[tool] start robot.move_joints
[tool] ok robot.move_joints error=None
[tool] fail vision.open_vocab_detect error=NO_OBJECT_DETECTED
```

## Avoid

```text
Running...
Done.
```

Too vague.

```text
[llm] api_key=...
```

Leaks secrets.

```text
[tool] input={...huge image/depth arrays...}
```

Too noisy for terminal use. Keep full details in JSONL task logs instead.

## Where this is currently used

- `listen-task` via `TaskLogger(console=True)`
- `scripts/linux/test_audio_input_pipeline.py`
- `scripts/linux/stream_vad_pipeline.py`
- `scripts/linux/stream_asr_pipeline.py`
