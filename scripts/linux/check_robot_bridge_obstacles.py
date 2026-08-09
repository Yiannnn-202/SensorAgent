#!/usr/bin/env python3
"""Print static MoveIt obstacles currently exposed by the robot bridge."""

from __future__ import annotations

import json
import sys
import urllib.request


def main() -> int:
  endpoint = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8765"
  url = endpoint.rstrip("/") + "/scene/obstacles"
  with urllib.request.urlopen(url, timeout=5.0) as response:
    data = json.load(response)
  print(json.dumps(data, ensure_ascii=False, indent=2))

  objects = {
    item.get("id")
    for item in data.get("state", {}).get("collision_objects", [])
    if isinstance(item, dict)
  }
  required = {
    "sensoragent_camera_left_post",
    "sensoragent_camera_right_post",
    "sensoragent_camera_crossbar",
    "sensoragent_camera_body",
  }
  missing = sorted(required - objects)
  if missing:
    print(f"Missing camera-rig obstacles: {missing}", file=sys.stderr)
    return 1
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
