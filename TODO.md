# TODO

This file tracks SensorAgent development progress by framework maturity. The current priority is to build the generic Agent architecture before adding competition-specific workflows.

## Phase 0 - Project skeleton and documentation

Goal: make the project understandable to new contributors and keep repository boundaries clear.

- [x] Define SensorAgent as an agent-side orchestration module.
- [x] Remove out-of-scope robot runtime, ROS 2, simulation, and hardware-driver content.
- [x] Establish Python `src/` package layout.
- [x] Add root `README.md`.
- [x] Organize project, team, and related-module documentation under `docs/`.
- [x] Add SensorAgent module positioning document.
- [x] Add `src/sensoragent/README.md` describing package layout.
- [x] Initialize `pyproject.toml`.

## Phase 1 - Minimal MCP/API to Skill to Tool pipeline

Goal: make the first complete local call chain work before expanding abstractions.

Target chain:

```text
mock MCP/API request
→ Agent runtime
→ Skill registry
→ Skill runtime
→ Tool registry
→ Tool runtime
→ mock tool result
→ skill result
→ Agent response
→ structured log trace
```

- [x] Define minimal call/result schemas: `AgentRequest`, `AgentResponse`.
- [x] Define minimal tool schemas: `ToolSpec`, `ToolCall`, `ToolResult`.
- [x] Define minimal skill schemas: `SkillSpec`, `SkillCall`, `SkillResult`.
- [x] Define minimal event/log schemas: `LogRecord`, `TraceContext`.
- [x] Implement tool base protocol.
- [x] Implement skill base protocol.
- [x] Implement tool registry.
- [x] Implement skill registry.
- [x] Implement a mock vision tool, e.g. `vision.mock_detect`.
- [x] Implement a mock audio tool, e.g. `audio.mock_transcribe`.
- [x] Implement a mock robot tool, e.g. `robot.mock_pick` or `robot.mock_place`.
- [x] Implement one mock skill that calls at least one tool.
- [x] Add a minimal Agent runtime that can invoke a skill by name.
- [x] Expose the mock skill invocation through a minimal MCP/API-shaped entry point.
- [x] Return a structured result from the full chain.
- [x] Record one full task/tool-call log trace.
- [x] Add `tests/unit/` for schema, registry, and logger basics.
- [x] Add `tests/e2e/` for mock MCP/API -> Agent -> Skill -> Tool.
- [x] Add `tests/fixtures/` directory structure for future mock inputs.
- [x] Add e2e assertions for final result, called tools, and generated logs.
- [ ] Add example configuration files only as needed for this mock chain.

## Phase 2 - Tool and skill framework

Goal: make capabilities discoverable, callable, logged, and testable.

- [ ] Implement tool base protocol.
- [ ] Implement tool registry.
- [ ] Implement tool runtime with timeout and error handling.
- [ ] Implement tool-call logging hooks.
- [ ] Implement skill base protocol.
- [ ] Implement skill registry.
- [ ] Implement skill runtime.
- [ ] Add mock tools for local development.
- [ ] Add unit tests for tool and skill registration/invocation.

## Phase 3 - Workflow runtime

Goal: execute task-specific procedures through ActionLists and DecisionTrees.

- [ ] Implement ActionList schema and runtime.
- [ ] Implement DecisionTree node schema and runtime.
- [ ] Support conditional branching.
- [ ] Support retries and recoverable failures.
- [ ] Support workflow-level context passing.
- [ ] Integrate workflow execution with structured logging.
- [ ] Add workflow registry and selection.
- [ ] Add unit tests for successful, failed, and retried workflows.

## Phase 4 - Agent runtime and service entry points

Goal: connect schemas, tools, skills, workflows, and state into a working Agent runtime.

- [ ] Implement Agent runtime loop.
- [ ] Implement planner interface.
- [ ] Implement workflow selector.
- [ ] Implement task/session state handling.
- [ ] Implement API service entry point.
- [ ] Implement WebSocket event stream.
- [ ] Implement CLI entry point.
- [ ] Add end-to-end mock task execution test.

## Phase 5 - Integrations and MCP/API collaboration

Goal: connect SensorAgent to external modules owned by other teams.

- [ ] Implement MCP client adapter.
- [ ] Implement MCP server adapter or wrapper if needed.
- [ ] Implement HTTP API integration client.
- [ ] Implement WebSocket integration client.
- [ ] Define capability discovery behavior.
- [ ] Add vision-agent adapter.
- [ ] Add audio-agent adapter.
- [ ] Add robot-runtime adapter.
- [ ] Add integration configuration examples.
- [ ] Add mocked integration tests.

## Phase 6 - Competition workflows and evaluation

Goal: implement competition-specific task logic after the generic framework is stable.

- [ ] Define industrial pick-and-place task schema.
- [ ] Add industrial pick-and-place ActionList workflow.
- [ ] Add industrial pick-and-place DecisionTree workflow.
- [ ] Add visual verification workflow branch.
- [ ] Add retry and recovery branches.
- [ ] Add task log export for reports and replay.
- [ ] Add evaluation metrics logging.
- [ ] Add demo CLI/API command for the competition task.

## Notes

- Logger is framework infrastructure, not a normal skill.
- Low-level robot control, Isaac Sim deployment, ROS 2 drivers, and physical safety belong to external runtime modules.
- SensorAgent collaborates with external modules through API, MCP, WebSocket, or documented adapters.
