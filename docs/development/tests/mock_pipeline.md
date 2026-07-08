# Mock Pipeline Test

This document describes how to verify the current Phase 1 mock Agent chain.

## Purpose

The mock pipeline proves that SensorAgent can execute the minimum Agent-side call path without any real robot, camera, audio service, Isaac Sim scene, or external module.

Verified chain:

```text
Mock MCP/API entry
→ AgentRuntime
→ SkillRuntime
→ mock.pick_and_place
→ ToolRuntime
→ vision.mock_detect
→ robot.mock_pick
→ robot.mock_place
→ AgentResponse
→ structured JSONL log
```

This is an end-to-end smoke test for the Agent framework. It verifies orchestration, registry lookup, tool invocation, result propagation, and structured logging.

## Related files

```text
configs/mock.yaml
src/sensoragent/agent/bootstrap.py
src/sensoragent/mcp/mock.py
src/sensoragent/skills/mock.py
src/sensoragent/tools/vision/mock.py
src/sensoragent/tools/robot/mock.py
src/sensoragent/tools/audio/mock.py
tests/e2e/test_mock_pipeline.py
tests/e2e/test_cli.py
tests/unit/test_contracts.py
```

## What is mocked

| Mock tool | Purpose |
|---|---|
| `vision.mock_detect` | Pretends to detect an object and returns a deterministic object ID and 3D pose. |
| `audio.mock_transcribe` | Pretends to transcribe speech into text. |
| `robot.mock_pick` | Pretends to pick an object successfully. |
| `robot.mock_place` | Pretends to place an object successfully. |

The current mock skill is:

```text
mock.pick_and_place
```

It calls:

```text
vision.mock_detect
→ robot.mock_pick
→ robot.mock_place
```

## Run all tests

From the repository root:

```powershell
$env:PYTHONPATH = "$(Get-Location)\src"
python -m unittest discover -s tests -p 'test_*.py'
```

Expected result:

```text
OK
```

At the time this document was written, the suite contains unit tests for registries, logging, config loading, contract validation, and end-to-end mock execution.

## Run the mock CLI manually

From the repository root:

```powershell
$env:PYTHONPATH = "$(Get-Location)\src"
python -m sensoragent.services.cli.main mock-pick-place --config configs\mock.yaml --object-query "silver roller" --target "third bin cell"
```

Or use the helper script:

```powershell
.\scripts\run_mock_pipeline.ps1 --object-query "silver roller" --target "third bin cell"
```

Expected behavior:

```text
1. The command prints a JSON AgentResponse.
2. response.success is true.
3. response.result.object.label equals the object query.
4. response.result.place.target equals the target.
5. A JSONL task log is written under logs/tasks/.
```

## Run through the planner lifecycle

The `run-task` command exercises the task lifecycle and planner path.

Static planner:

```powershell
$env:PYTHONPATH = "$(Get-Location)\src"
python -m sensoragent.services.cli.main run-task "put the silver roller into the third bin cell" --config configs\mock.yaml --planner static --object-query "silver roller" --target "third bin cell"
```

DeepSeek-backed LLM planner:

```powershell
$env:PYTHONPATH = "$(Get-Location)\src"
python -m sensoragent.services.cli.main run-task "put the silver roller into the third bin cell" --config configs\mock.yaml --planner llm
```

The LLM planner requires a local `.env` with:

```env
SENSORAGENT_LLM_PROVIDER=deepseek
SENSORAGENT_LLM_BASE_URL=https://api.deepseek.com
SENSORAGENT_LLM_API_KEY=...
SENSORAGENT_LLM_MODEL=deepseek-v4-flash
```

## Logs

Manual CLI runs write task logs under:

```text
logs/tasks/
```

The log format is JSONL. Each line is one structured event.

Typical events:

```text
agent_request_started
skill_call_started
tool_call_started
tool_call_finished
skill_call_finished
agent_request_finished
```

The `logs/` directory is ignored by Git and should not be committed.

## Pass criteria

The mock pipeline passes when:

```text
the CLI exits with code 0
AgentResponse.success is true
vision.mock_detect is called before robot.mock_pick
robot.mock_pick is called before robot.mock_place
structured logs are emitted
task log file is created for manual runs
all unittest tests pass
```

## What this does not test

The mock pipeline does not test:

```text
real MCP transport
real HTTP/WebSocket APIs
real vision models
real ASR/TTS services
real robot execution
Isaac Sim
hardware safety
```

The CLI and unit tests now cover planner lifecycle, ActionList, and DecisionTree mock paths. They still do not cover real external modules or real MCP/HTTP/WebSocket transport.
