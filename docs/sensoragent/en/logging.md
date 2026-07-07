# Logging

SensorAgent owns its own Agent-side logs. External runtime logs from robot, simulation, camera, or other modules are not stored here unless explicitly imported by an integration.

## Runtime log directory

Runtime logs are written under the repository-local `logs/` directory by default:

```text
logs/
├── app.log
├── tasks/
├── traces/
└── errors/
```

The `logs/` directory is ignored by Git.

## Human-readable logs

`logs/app.log` is intended for real-time observation during development and demos.

Examples:

```bash
tail -f logs/app.log
```

On Windows PowerShell:

```powershell
Get-Content logs\app.log -Wait
```

## Structured task logs

Task-level logs should be stored as JSONL files under `logs/tasks/`.

Example:

```json
{"event":"task_started","task_id":"...","input":"put the roller into cell 3"}
{"event":"tool_call_started","task_id":"...","tool":"vision.detect_object","input":{}}
{"event":"tool_call_finished","task_id":"...","tool":"vision.detect_object","output":{},"duration_ms":120}
{"event":"task_finished","task_id":"...","status":"success"}
```

## Trace logs

Trace logs under `logs/traces/` should capture detailed execution spans, such as Agent planning, skill execution, tool invocation, retries, and integration calls.

## Error logs

Unexpected runtime errors may be mirrored under `logs/errors/` for easier debugging.

## Configuration

The log directory and log level should be configurable through project config files and environment variables.

Recommended configuration shape:

```yaml
logging:
  level: info
  console: true
  file: logs/app.log
  task_dir: logs/tasks
  trace_dir: logs/traces
  error_dir: logs/errors
```

Recommended environment overrides:

```env
SENSORAGENT_LOG_DIR=logs
SENSORAGENT_LOG_LEVEL=debug
```
