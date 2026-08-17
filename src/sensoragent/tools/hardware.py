"""One-click physical hardware startup tool."""
from __future__ import annotations
import os
from pathlib import Path
import subprocess
from sensoragent.schemas import ToolCall, ToolResult, ToolSpec


class HardwareStartStackTool:
  spec = ToolSpec(name="hardware.start_stack", description="Start the SensorAgent physical hardware stack.", tags=("hardware", "startup"), timeout_seconds=10.0)

  def run(self, call: ToolCall) -> ToolResult:
    del call
    root = Path(__file__).resolve().parents[3]
    log_dir = root / "logs" / "hardware"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "hardware_stack.log"
    with log_path.open("ab") as stream:
      process = subprocess.Popen([str(root / "scripts/linux/start_hardware_stack.sh")], stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
    return ToolResult(tool=self.spec.name, success=True, output={"pid": process.pid, "log_path": str(log_path)})
