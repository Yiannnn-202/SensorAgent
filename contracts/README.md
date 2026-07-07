# Contracts

Contracts define cross-module input/output formats. They are language-neutral interface documents for tools, resources, and shared message structures.

They are different from internal Python schemas:

```text
contracts/                  Cross-module interface contracts
src/sensoragent/schemas/    SensorAgent internal Python data structures
```

External modules do not need to import SensorAgent's Python code. They only need to implement the agreed contracts.

## Layout

```text
contracts/
├── common/
│   ├── error.schema.json
│   └── trace-context.schema.json
└── tools/
    ├── vision.mock_detect.schema.json
    ├── audio.mock_transcribe.schema.json
    ├── robot.mock_pick.schema.json
    └── robot.mock_place.schema.json
```

## Tool contract shape

Each tool contract should include:

```text
name
version
description
input_schema
output_schema
errors
```

`input_schema` and `output_schema` use JSON Schema-style objects. During development, tests validate mock tool inputs and outputs against these contracts.

## Usage

Contracts are used to:

- communicate expected tool formats to other teams;
- validate mock and real tool adapters;
- generate or document MCP tool definitions;
- align HTTP/API/WebSocket payloads with Agent-side tool calls.

## Rule of thumb

- One tool, one contract file.
- File names should match tool names, e.g. `robot.mock_pick.schema.json`.
- Contracts describe the interface, not the implementation.
- Changes to contracts should be treated as interface changes.
