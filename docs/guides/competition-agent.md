# Industrial Agent Reproduction Guide

This is the evaluator-facing entry point for the SensorAgent submission branch.
The project exposes one persistent industrial agent loop with two launch modes:
Gazebo simulation and physical hardware.

## Agent loop

The runtime is a session, not a one-shot script. It keeps running until the
operator enters `exit`, `quit`, `q`, `退出`, or `结束`.

```text
IDLE
→ UNDERSTAND        parse the Chinese/English command into object, target, selector
→ CHECK_WORLD       reject occupied bins or ambiguous references
→ OBSERVE           use configured scene state or RGB-D/camera capture
→ PERCEIVE          detect/select the target object
→ PLAN              choose a bounded pick/place action sequence
→ ACT               call approved robot Skills/Tools only
→ VERIFY            verify grasp/place postconditions
→ RECOVER           classify failures and retry within the recovery budget
→ COMPLETE
→ IDLE
```

The agent prints one JSON event per turn and writes JSONL records under
`logs/tasks/`. The `agent_loop` field in command results lists the active loop
stages, and `world_state` records objects, bins, current task state, and history.

For simple industrial references, the perception layer uses deterministic
grounding rather than free-form model reasoning. For example, "左边的螺母" becomes
the normalized class `hex_nut` plus `spatial_constraint={"relation":"left",
"ordinal":1}`; `vision.dual_branch_detect` detects candidate instances, then the
spatial selector chooses from those existing candidates.

## 1. Simulation agent

Use this command on Ubuntu with ROS 2 Humble:

```bash
bash scripts/linux/run_sim_agent.sh
```

The launcher starts the industrial sorting Gazebo/MoveIt stack and then enters
the persistent competition session with:

```text
backend: sim
config:  configs/competition_sim.yaml
mode:    text
execute: true
```

Useful options:

```bash
bash scripts/linux/run_sim_agent.sh --mode voice
bash scripts/linux/run_sim_agent.sh --dry-run
bash scripts/linux/run_sim_agent.sh --no-start-stack
bash scripts/linux/run_sim_agent.sh --llm-grounding-mode fallback
bash scripts/linux/run_sim_agent.sh --no-llm-grounding
```

`--dry-run` switches robot execution to the fake backend. `--no-start-stack`
assumes Gazebo/MoveIt/bridge are already running.
Constrained LLM grounding is enabled by default in `assist` mode, so the LLM can
refine rule-ready intents within the same strict whitelist, add a missing
spatial selector, or request clarification for vague wording without being
allowed to output coordinates or robot actions. `--llm-grounding-mode fallback`
calls the LLM only after rule grounding fails. `--no-llm-grounding` disables
external LLM calls for offline/rules-only runs.

Example commands after the prompt appears:

```text
把离机械臂最近的滚柱放到三号格
把左边的六角螺母放到一号格
把所有滚柱放到一号格
状态
退出
```

The simulation path captures Gazebo RGB-D frames and uses
`vision.dual_branch_detect` for object perception. The configured ontology is
used only for language grounding and supported-class validation; object position
comes from the vision output consumed by the recovery DecisionTree.

Known industrial classes route to YOLO11-seg. Unknown/open-language targets
route to the GroundingDINO + SAM2 branch. GroundingDINO produces text-grounded
bboxes, and SAM2 refines the selected bbox into an instance mask for downstream
depth/point-cloud localization.

## 2. Hardware agent

The hardware launcher is safety-gated. By default it starts the hardware bridge
with `allow_motion:=false` and enters the same persistent agent loop without
enabling physical movement:

```bash
bash scripts/linux/run_hardware_agent.sh
```

To allow physical motion, run it only after workspace, camera, gripper, operator,
and emergency-stop checks are complete:

```bash
bash scripts/linux/run_hardware_agent.sh --enable-motion
```

If the Island-Arm package is installed outside `~/Island-Arm`, set
`SENSORAGENT_ISLAND_ARM_SETUP=/path/to/Island-Arm/install/setup.bash` before
starting the hardware launcher. `SENSORAGENT_ROS_SETUP` and
`SENSORAGENT_ROS_WS_SETUP` may also override the ROS 2 and SensorAgent workspace
setup files.

Useful options:

```bash
bash scripts/linux/run_hardware_agent.sh --mode voice
bash scripts/linux/run_hardware_agent.sh --no-start-stack
bash scripts/linux/run_hardware_agent.sh --llm-grounding-mode fallback
bash scripts/linux/run_hardware_agent.sh --no-llm-grounding
```

The hardware launcher uses:

```text
backend: hardware
config:  configs/competition_hardware.yaml
mode:    text
motion:  disabled unless --enable-motion is present
```

The hardware path captures real RGB/point-cloud input, runs
`vision.dual_branch_detect` to localize the requested object, selects the
configured pick profile, executes the approved pick/place actionlist, and
records the same JSON turn output. It does not bypass bridge safety limits or
issue arbitrary LLM-generated robot commands.

Because constrained LLM grounding is enabled by default, configure the text LLM
endpoint before running the normal competition launchers:

```bash
export SENSORAGENT_LLM_API_KEY=...
export SENSORAGENT_LLM_MODEL=...
export SENSORAGENT_LLM_BASE_URL=https://api.example.com
```

The text LLM may only output an allowed object class, action, target, quantity,
and spatial selector. Invalid output is ignored and the deterministic grounding
result is returned. The `assist` mode improves semantic flexibility but keeps
the same execution boundary: final robot motion still goes through approved
Workflow, Skill, Tool, and bridge checks.

For open visual grounding, fill the GroundingDINO and SAM2 paths in
`configs/competition_hardware.yaml`:

```yaml
integrations:
  vision:
    grounding_dino_model: models/vision/grounding-dino/industrial-open-vocab
    sam2_model_path: models/vision/sam2_t.pt
```

## Output contract

A successful or failed command prints one object like:

```json
{
  "type": "command",
  "success": true,
  "backend": "sim",
  "transcript": "把离机械臂最近的滚柱放到三号格",
  "intent": {
    "status": "ready",
    "action": "pick_place",
    "object_class": "roller",
    "target": "bin_cell_3"
  },
  "agent_loop": [
    "idle",
    "understand",
    "check_world",
    "observe",
    "perceive",
    "select",
    "plan",
    "act",
    "verify",
    "recover_if_needed",
    "complete"
  ],
  "execution": {
    "actionlist": "industrial.sorting_config_pick_place_actionlist",
    "recovery_attempts": 0
  },
  "world_state": {}
}
```

If the command is ambiguous or the target cell is occupied, the agent returns a
structured failure and waits for the next command instead of terminating.

## Failure detection

Failure detection is not a single vision-only module. The agent combines:

```text
robot / gripper state
tool and bridge errors
post-grasp verification
post-place verification
optional RGB-D visual re-detection
```

Visual checks are used for postconditions that require observing the object:

- `vision.verify_object_lifted` compares before/after object poses and reports
  `DROPPED_OBJECT` when the object did not move with the gripper.
- `vision.verify_object_in_bin` checks whether the observed object position is
  inside the requested bin cell and reports `WRONG_BIN` when it is outside.
- In live-perception workflows, `vision.capture_frame` and
  `vision.dual_branch_detect` can re-detect the object after a failed step so
  recovery can re-plan from the observed pose instead of a stale command pose.

Non-visual failures such as bridge timeout, gripper command failure, invalid
target, or motion planning failure are classified from structured tool/skill
evidence by `recovery.classify_failure`. The recovery policy then chooses a
bounded local action such as re-detect, re-pick, re-place, open gripper, or stop
and reset.

## Validation

Run the repository test suite from the project root:

```powershell
$env:PYTHONPATH = "$(Get-Location)\src"
python -m pytest -q tests
```

The tests are offline/static except for environment-specific ROS or hardware
manual acceptance. Model weights, datasets, logs, captured frames, and real
credentials remain outside Git.
