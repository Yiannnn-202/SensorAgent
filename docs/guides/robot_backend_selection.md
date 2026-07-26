# Robot Backend Selection Plan

This note describes a planned runtime switch for the robot execution backend.
It does not change execution behavior by itself.

## Goal

Provide a terminal-level choice between:

```text
simple scripted robot execution
MoveIt 2-based robot execution
```

The upper layers of SensorAgent should stay unchanged:

```text
ASR -> Agent -> Skill -> ActionList -> Robot tool API
```

Only the robot backend implementation should vary.

## Why this is needed

For fixed industrial scenarios, MoveIt 2 can feel heavier than necessary and
may generate paths that are harder to read or less visually direct. A simple
scripted backend is easier to control for:

- fixed staging poses
- direct approach and retreat
- simple retry behavior
- short, repeatable motions

MoveIt 2 remains useful when:

- path search is needed
- obstacle avoidance matters
- the scene changes often
- a fallback execution path is required

## Proposed runtime modes

### 1. `simple`

Use a scripted backend with precomputed motion patterns.

Typical behavior:

- move to a safe staging pose
- approach the object or place target
- execute a short straight motion
- open/close the gripper
- retreat to a safe pose
- retry from another scripted pose if needed

This mode is intended for simple, stable scenes.

### 2. `moveit2`

Use the existing MoveIt 2 bridge and planning stack.

Typical behavior:

- let MoveIt 2 compute the motion path
- keep collision checking and constraint handling
- use the bridge for execution

This mode is intended for complex or less predictable scenes.

## Configuration shape

The robot backend should be selectable from config, with optional CLI override.

Example:

```yaml
integrations:
  robot:
    backend: simple
```

or:

```yaml
integrations:
  robot:
    backend: http
```

Suggested CLI override:

```text
--robot-backend simple
--robot-backend moveit2
```

If both config and CLI are present, CLI should win.

## Integration point

The best place for the switch is the existing robot integration layer.

Recommended path:

```text
configs/
  -> bootstrap.py
  -> RobotControlClient factory
  -> simple backend or HTTP bridge backend
```

This keeps the following layers stable:

- contracts
- skills
- ActionLists
- planner
- ASR/TTS

## Suggested behavior for place failure recovery

If a place attempt fails, the agent can:

1. read back robot state
2. confirm whether the gripper released the object
3. optionally inspect the scene again
4. retry with a scripted fallback pose
5. fall back to MoveIt 2 when scripted retry is not enough

This gives a practical split:

- simple retry logic in script mode
- full replanning in MoveIt 2 mode

## Rollout plan

1. Add a new robot backend implementation for scripted execution.
2. Add config support for selecting the backend.
3. Add a CLI override for quick terminal testing.
4. Keep the MoveIt 2 backend available as a fallback.
5. Add tests for backend selection and backend-specific behavior.

## Acceptance criteria

- The backend can be selected without changing ActionLists.
- The same high-level task can run under both modes.
- The simple backend produces stable scripted motion.
- The MoveIt 2 backend still works unchanged.
- Model weights remain local-only and are not uploaded.

