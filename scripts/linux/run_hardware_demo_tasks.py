#!/usr/bin/env python3
"""Run a prepared hardware task file without interactive task entry."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
  sys.path.insert(0, str(SRC))

from sensoragent.config import load_config


def _validate_yolo_seg_batch_config(config_path: Path) -> None:
  """Reject batch runs that do not use YOLO-Seg and the dedicated part profiles."""

  config = load_config(config_path)
  if str(config.integrations.vision.get("backend", "")).casefold() != "yolo_seg":
    raise ValueError("Hardware batch requires integrations.vision.backend: yolo_seg")
  missing_profiles = [
    name for name in ("roller", "hex_nut")
    if not isinstance(config.scene.pick_profiles.get(name), dict)
  ]
  if missing_profiles:
    raise ValueError(
      "Hardware batch requires dedicated pick profiles: "
      + ", ".join(missing_profiles)
    )
  print(f"Batch config: {config_path} (vision=yolo_seg; profiles=roller, hex_nut)")

  

def main() -> int:
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--tasks", type=Path, default=Path("logs/datasets/hardware_demo_tasks_100.jsonl"))
  parser.add_argument("--config", type=Path, default=Path("configs/robot_hardware_yolo_seg.yaml"))
  parser.add_argument("--start", type=int, default=1)
  args = parser.parse_args()
  tasks = [json.loads(line) for line in args.tasks.read_text(encoding="utf-8").splitlines() if line.strip()]
  _validate_yolo_seg_batch_config(args.config)
  for task in tasks:
    index = int(task["index"])
    if index < args.start:
      continue
    instruction = str(task["instruction"])
    print(f"\n[{index}/{len(tasks)}] {instruction}")
    command = [
      sys.executable, "-m", "sensoragent.services.cli.main", "run-task", instruction,
      "--config", str(args.config), "--planner", "llm",
    ]
    completed = subprocess.run(command, env={**__import__("os").environ, "PYTHONPATH": "src"})
    if completed.returncode:
      print(f"Task {index} failed; inspect its task log before continuing.", file=sys.stderr)
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
