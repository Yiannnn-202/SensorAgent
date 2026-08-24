#!/usr/bin/env python3
"""Generate randomized natural-language hardware demonstration tasks."""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path


OBJECTS = ("短螺栓", "六角螺母", "滚柱")
REFERENCES = ("左边的", "右边的", "中间的", "最左边的", "最右边的", "第二个")
VERBS = ("把", "抓取", "拿起")


def main() -> int:
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--count", type=int, default=100)
  parser.add_argument("--seed", type=int, default=None)
  parser.add_argument("--output", type=Path, default=Path("logs/datasets/hardware_demo_tasks_100.jsonl"))
  args = parser.parse_args()
  if args.count < 1:
    raise ValueError("--count must be positive")
  rng = random.Random(args.seed)
  args.output.parent.mkdir(parents=True, exist_ok=True)
  with args.output.open("w", encoding="utf-8") as stream:
    for index in range(1, args.count + 1):
      reference = rng.choice(REFERENCES)
      object_name = rng.choice(OBJECTS)
      target = rng.randint(1, 4)
      instruction = f"{rng.choice(VERBS)}{reference}{object_name}放到{target}号格子"
      stream.write(json.dumps({"index": index, "instruction": instruction}, ensure_ascii=False) + "\n")
  print(f"Generated {args.count} tasks: {args.output}")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
