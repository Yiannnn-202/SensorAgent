"""JSON Schema-style validation helpers for tool contracts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sensoragent.tools.errors import ToolValidationError


def validate_schema(value: Any, schema: dict[str, Any], path: str = "$") -> None:
  """Validate a value against the small JSON Schema subset used by contracts."""

  expected_type = schema.get("type")
  if expected_type == "object":
    if not isinstance(value, dict):
      raise ToolValidationError(f"{path} expected object")
    for field in schema.get("required", []):
      if field not in value:
        raise ToolValidationError(f"{path}.{field} is required")
    properties = schema.get("properties", {})
    for field, field_value in value.items():
      if field in properties:
        validate_schema(field_value, properties[field], f"{path}.{field}")
    return

  if expected_type == "array":
    if not isinstance(value, list):
      raise ToolValidationError(f"{path} expected array")
    item_schema = schema.get("items")
    if item_schema:
      for index, item in enumerate(value):
        validate_schema(item, item_schema, f"{path}[{index}]")
    return

  if expected_type == "string":
    if not isinstance(value, str):
      raise ToolValidationError(f"{path} expected string")
    return

  if expected_type == "boolean":
    if not isinstance(value, bool):
      raise ToolValidationError(f"{path} expected boolean")
    return

  if expected_type == "number":
    if not isinstance(value, (int, float)) or isinstance(value, bool):
      raise ToolValidationError(f"{path} expected number")
    return

  if expected_type is not None:
    raise ToolValidationError(f"{path} unsupported schema type: {expected_type}")


class ContractValidator:
  """Loads tool contracts and validates tool input/output payloads."""

  def __init__(
    self,
    contract_root: Path = Path("contracts"),
    require_contract: bool = False,
  ) -> None:
    self._contract_root = contract_root
    self._require_contract = require_contract

  def load_tool_contract(self, tool_name: str) -> dict[str, Any] | None:
    path = self._contract_root / "tools" / f"{tool_name}.schema.json"
    if not path.exists():
      if self._require_contract:
        raise ToolValidationError(f"Missing contract for tool: {tool_name}")
      return None
    return json.loads(path.read_text(encoding="utf-8"))

  def validate_tool_input(self, tool_name: str, input_data: dict) -> None:
    contract = self.load_tool_contract(tool_name)
    if contract is None:
      return
    validate_schema(input_data, contract["input_schema"])

  def validate_tool_output(self, tool_name: str, output_data: dict | None) -> None:
    contract = self.load_tool_contract(tool_name)
    if contract is None:
      return
    validate_schema(output_data, contract["output_schema"])
