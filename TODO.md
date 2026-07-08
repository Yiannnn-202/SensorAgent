# TODO

This file tracks SensorAgent development progress by framework maturity. The current priority is to build a reliable Agent architecture before adding competition-specific workflows.

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
- [x] Add root `.gitignore`.
- [x] Add logging documentation.
- [x] Add root `TODO.md`.

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
- [x] Implement tool runtime with basic logging and exception wrapping.
- [x] Implement skill runtime with basic logging and exception wrapping.
- [x] Implement a mock vision tool: `vision.mock_detect`.
- [x] Implement a mock audio tool: `audio.mock_transcribe`.
- [x] Implement mock robot tools: `robot.mock_pick`, `robot.mock_place`.
- [x] Implement one mock skill: `mock.pick_and_place`.
- [x] Add a minimal Agent runtime that invokes one skill by name.
- [x] Expose the mock skill invocation through a minimal MCP/API-shaped entry point.
- [x] Return a structured result from the full chain.
- [x] Record one full task/tool-call log trace.
- [x] Add `tests/unit/` for registry and logger basics.
- [x] Add `tests/e2e/` for mock MCP/API -> Agent -> Skill -> Tool.
- [x] Add `tests/fixtures/` directory structure for future mock inputs.
- [x] Add e2e assertions for final result, called tools, and generated logs.

## Phase 1.1 - Config-driven mock pipeline

Goal: make the current mock chain configurable instead of hard-coded in tests.

- [x] Add `configs/mock.yaml`.
- [x] Define minimal config schema for enabled tools and skills.
- [x] Implement config loader in `src/sensoragent/config/loader.py`.
- [x] Implement config schema in `src/sensoragent/config/schema.py`.
- [x] Add environment selection, e.g. `SENSORAGENT_ENV=mock`.
- [x] Add registry builder that creates tool and skill registries from config.
- [x] Move mock tool/skill registration out of e2e test setup.
- [x] Update e2e test to build runtime from `configs/mock.yaml`.
- [x] Document config loading in dedicated config docs.

## Phase 1.2 - Tool contracts

Goal: document cross-module tool input/output formats before real integrations begin.

- [x] Add root `contracts/` directory.
- [x] Add `contracts/README.md` explaining contracts vs internal schemas.
- [x] Add `contracts/tools/vision.mock_detect.schema.json`.
- [x] Add `contracts/tools/audio.mock_transcribe.schema.json`.
- [x] Add `contracts/tools/robot.mock_pick.schema.json`.
- [x] Add `contracts/tools/robot.mock_place.schema.json`.
- [x] Add shared error format contract.
- [x] Add shared trace context contract.
- [x] Add a simple contract validation helper for tests.
- [x] Validate mock tool inputs against contracts in tests.
- [x] Validate mock tool outputs against contracts in tests.

## Phase 1.3 - Manual runnable mock demo

Goal: let teammates run the mock Agent chain without reading test code.

- [x] Add CLI module `src/sensoragent/services/cli/main.py`.
- [x] Add command for running `mock.pick_and_place`.
- [x] Add CLI arguments: `--object-query`, `--target`, `--log-path`.
- [x] Write logs to `logs/tasks/` by default when run manually.
- [x] Print final `AgentResponse` in human-readable form.
- [x] Add script `scripts/run_mock_pipeline.*` if useful.
- [x] Add README instructions for running the mock chain.
- [x] Add e2e test for CLI execution.

## Phase 2 - Runtime hardening

Goal: make the minimal runtime safer, clearer, and easier to extend.

- [x] Replace broad tool exception handling with typed errors.
- [x] Replace broad skill exception handling with typed errors.
- [x] Add timeout support to `ToolRuntime`.
- [x] Add optional retry support to `ToolRuntime`.
- [x] Add input validation hook before tool invocation.
- [x] Add output validation hook after tool invocation.
- [x] Add richer `ToolError` and `SkillError` schemas.
- [x] Add tool/skill metadata such as version, tags, and enabled state.
- [x] Add duplicate registration tests.
- [x] Add unknown tool/skill tests.
- [x] Add failure-path e2e tests.
- [x] Add JSONL log shape tests.

## Phase 3 - ActionList workflow runtime

Goal: move fixed multi-step task procedures out of skills and into workflows.

- [x] Define ActionList schema.
- [x] Define ActionStep schema.
- [x] Implement sequential ActionList runtime.
- [x] Support passing step output into later steps.
- [x] Support named variables in workflow context.
- [x] Support stop-on-failure behavior.
- [x] Support per-step logging.
- [x] Recreate mock pick-and-place as an ActionList.
- [x] Add e2e test for ActionList mock pick-and-place.
- [x] Allow `AgentRuntime` to run an ActionList directly.
- [x] Keep `mock.pick_and_place` as a skill-level smoke test.
- [x] Use `mock.pick_place_actionlist` as the workflow-level demo.

## Phase 4 - DecisionTree workflow runtime

Goal: support branching task policies with retries and recovery.

- [ ] Define DecisionTree node schema.
- [ ] Define condition schema.
- [ ] Implement branch evaluation.
- [ ] Implement success/failure branches.
- [ ] Implement retry counters.
- [ ] Implement recoverable vs terminal failure states.
- [ ] Add mock failure tools for testing.
- [ ] Add e2e test for retry after mock pick failure.
- [ ] Add e2e test for branch when object is not found.

## Phase 5 - Agent runtime expansion

Goal: evolve AgentRuntime from single-skill dispatch into task orchestration.

- [ ] Add task/session state object.
- [ ] Add workflow selector interface.
- [ ] Add planner interface.
- [ ] Add prompt placeholder structure for future LLM planner.
- [ ] Add task lifecycle states: pending, running, succeeded, failed, cancelled.
- [ ] Add cancellation hook.
- [ ] Add event stream abstraction.
- [ ] Add task result persistence hook.
- [ ] Add end-to-end test for task lifecycle.

## Phase 6 - API, WebSocket, and MCP service entry points

Goal: expose SensorAgent to users, frontend, and other modules.

- [ ] Decide first real service framework.
- [ ] Add minimal HTTP API entry point.
- [ ] Add `POST /tasks` mock endpoint.
- [ ] Add `GET /tasks/{task_id}` mock endpoint.
- [ ] Add WebSocket event stream for task logs/events.
- [ ] Add minimal MCP server wrapper if needed.
- [ ] Add MCP client adapter for external tools if needed.
- [ ] Add service-level tests with mock runtime.
- [ ] Document API/MCP usage.

## Phase 7 - External integrations

Goal: connect SensorAgent to modules owned by other teams through stable adapters.

- [ ] Define integration config format.
- [ ] Implement HTTP integration client.
- [ ] Implement WebSocket integration client.
- [ ] Implement MCP integration client.
- [ ] Add vision-agent adapter.
- [ ] Add audio-agent adapter.
- [ ] Add robot-runtime adapter.
- [ ] Add simulation-runtime adapter if needed.
- [ ] Add mocked integration tests.
- [ ] Add contract tests for external adapters.

## Phase 8 - Competition workflows and evaluation

Goal: implement competition-specific task logic after the generic framework is stable.

- [ ] Define industrial pick-and-place task schema.
- [ ] Add industrial pick-and-place ActionList workflow.
- [ ] Add industrial pick-and-place DecisionTree workflow.
- [ ] Add visual verification workflow branch.
- [ ] Add retry and recovery branches.
- [ ] Add task log export for reports and replay.
- [ ] Add evaluation metrics logging.
- [ ] Add demo CLI/API command for the competition task.
- [ ] Add fixture-based e2e tests for competition task logic.

## Notes

- Logger is framework infrastructure, not a normal skill.
- Low-level robot control, Isaac Sim deployment, ROS 2 drivers, and physical safety belong to external runtime modules.
- SensorAgent collaborates with external modules through API, MCP, WebSocket, or documented adapters.
- Internal Python schemas are not the same as cross-module contracts; contracts should be language-neutral.
