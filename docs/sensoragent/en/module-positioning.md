# SensorAgent Module Positioning

## 1. Module Identity

SensorAgent is the decision and orchestration module of the larger embodied intelligence project. It is not the robot runtime, simulation stack, hardware driver, or low-level perception/control implementation.

Its role is to organize external capabilities into task-level behavior:

```text
User / multimodal input
→ Agent task understanding
→ Workflow selection
→ Skill and tool invocation
→ API / MCP collaboration with other modules
→ Structured task logging
→ Final result or next-step decision
```

In short, SensorAgent is the module that decides **what should be done, which capability should be called, in what order, and how the task process should be recorded**.

## 2. Relationship to the Overall Project

The overall project can be understood as two major sides:

```text
GECA: agent-side cognition and decision-making
ECOS: robot-side runtime, perception, control, simulation, and hardware execution
```

SensorAgent mainly implements the GECA-side orchestration layer.

| Overall concept | SensorAgent responsibility |
|---|---|
| **GECA** | Agent runtime, planner, skills, tools, workflows, logger |
| **ECOS** | External runtime consumed through API or MCP |
| **Isaac Sim** | External simulation environment, not owned by this repository |
| **Robot control** | External runtime capability exposed as tools |
| **Vision / audio** | Local tools or external agent/service adapters |
| **MCP bus** | One of the main collaboration protocols between modules |

SensorAgent is therefore the "brain-side orchestrator" of the system, while robot execution, simulation deployment, and hardware control are owned by other modules or teams.

## 3. Responsibility Boundary

SensorAgent owns:

```text
task understanding
tool discovery and invocation
skill composition
ActionList runtime
DecisionTree runtime
agent state management
structured task logging
external module adapters
API / CLI entry points
```

SensorAgent does not own:

```text
Isaac Sim scene deployment
ROS 2 driver packages
MoveIt2 configuration
robot firmware
physical robot safety layer
real camera bringup
mechanical arm trajectory execution
```

Those capabilities should be exposed to SensorAgent through tools, skills, API endpoints, MCP servers, WebSocket services, or other documented integration contracts.

## 4. Why This Module Is Separated

The Agent should not be tightly coupled to a specific robot, simulator, camera, or ROS topic. If the Agent directly depends on low-level robot infrastructure, it becomes difficult to reuse and evolve.

Instead, SensorAgent depends on abstract capabilities:

```text
vision.detect_object
vision.segment_object
audio.transcribe
audio.speak
robot.pick
robot.place
robot.get_state
sim.get_state
```

The implementation behind those capabilities may be:

```text
local Python functions
HTTP APIs
WebSocket services
MCP servers
ROS 2 bridges
other Agent modules
```

This makes the Agent portable across different robots, simulation environments, and perception stacks.

## 5. Core Abstractions

### Tool

A tool is the smallest callable capability. It should have:

```text
stable input schema
stable output schema
failure semantics
timeout behavior
structured logging
testability
```

Examples:

```text
vision.detect_object
vision.segment_object
audio.transcribe
audio.speak
robot.pick
robot.place
robot.get_state
```

### Skill

A skill composes one or more tools into a higher-level capability.

Examples:

```text
inspect_scene
pick_and_place
verify_object_placement
recover_from_failure
```

Skills describe reusable capability patterns. They are broader than tools but should still avoid embedding task-specific competition logic when possible.

### Workflow

A workflow is a task-specific execution policy. It may be:

```text
ActionList: an ordered sequence of actions
DecisionTree: a branching task policy with conditions, retries, and recovery
```

Competition-specific task logic should mainly live in workflows.

### Logger

The logger is a framework-level infrastructure module, not a regular skill. It should automatically record:

```text
task id
user input
parsed intent
selected workflow
tool calls
tool inputs and outputs
duration
errors
retry decisions
final status
```

Logging should be handled by the Agent, workflow, skill, and tool runtimes through middleware, decorators, spans, or context objects. The Agent should not need to explicitly choose a "logging skill" during normal task execution.

## 6. Role in the Industrial Pick-and-Place Competition Task

For the industrial object perception and instruction-interaction competition, SensorAgent should be responsible for:

```text
understanding natural language tasks
extracting target object and target location
selecting the industrial pick-and-place workflow
calling vision tools to obtain target information
calling robot tools to execute pick/place actions
calling verification tools to check task result
choosing retry or recovery branches when needed
recording the full task trace
```

Example instruction:

```text
Put the silver roller on the left into the third bin cell.
```

SensorAgent should turn it into a workflow such as:

```text
parse_instruction
→ detect_target_object
→ detect_target_cell
→ pick
→ place
→ verify
→ recover_if_failed
```

However, it should not implement the low-level details of:

```text
SAM3 / DINO-X inference internals
camera drivers
RM65 trajectory planning
Isaac Sim scene construction
gripper firmware control
```

Those are external capabilities consumed through tools.

## 7. Collaboration With Other Modules

SensorAgent collaborates with other Agent modules or runtime modules through documented APIs or MCP contracts.

Example integration configuration:

```yaml
agents:
  vision_agent:
    protocol: mcp
    endpoint: ws://vision-agent:7002
    tools:
      - vision.detect_object
      - vision.segment_object

  robot_agent:
    protocol: api
    endpoint: http://robot-runtime:7003
    tools:
      - robot.pick
      - robot.place

  audio_agent:
    protocol: api
    endpoint: http://audio-agent:7004
    tools:
      - audio.transcribe
      - audio.speak
```

The exact transport can vary, but the contract should remain stable: discoverable capability, typed input, typed output, timeout, error semantics, and logs.

## 8. Current Development Priority

The near-term priority is not to implement a full competition demo immediately. The first long phase is to build the generic Agent architecture:

```text
MCP / API collaboration mechanism
tool registry
skill registry
ActionList runtime
DecisionTree runtime
structured logger
configuration and integration loading
minimal API / CLI entry points
unit tests for each core runtime
```

After this framework stabilizes, concrete competition workflows can be added under:

```text
src/sensoragent/workflows/actionlists/
src/sensoragent/workflows/decision_trees/
```

## 9. Summary

SensorAgent is the GECA-side orchestration module of the larger embodied intelligence system. It is responsible for thinking, planning, invoking, coordinating, and logging. It does not own low-level simulation, drivers, or robot execution.

Its long-term value is extensibility: new vision modules, audio modules, robot runtimes, simulation systems, and competition tasks can be integrated as tools, skills, and workflows without rewriting the Agent core.
