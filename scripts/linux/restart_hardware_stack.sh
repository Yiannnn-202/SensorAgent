#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# Stop an active motion before terminating the process tree.
curl --silent --show-error --max-time 2 -X POST http://127.0.0.1:8766/stop >/dev/null || true

for pattern in \
  'ros2 launch sensoragent_hardware_bridge hardware_stack.launch.py' \
  'sensoragent_hardware_bridge.*hardware_bridge' \
  'op_control.*op_control_node' \
  'arm_control.*arm_control_server' \
  'rm_driver.*rm_driver' \
  'vision_dep.*dep_cam'; do
  pkill -TERM -f "$pattern" || true
done
sleep 2

op_port="${OP_PORT:-}"
if [[ -z "$op_port" ]]; then
  for candidate in /dev/ttyUSB*; do
    if [[ -e "$candidate" ]]; then
      op_port="$candidate"
      break
    fi
  done
fi

if [[ -z "$op_port" ]]; then
  printf 'No OmniPicker serial device found. Set OP_PORT=/dev/ttyUSB<n> and retry.\n' >&2
  exit 1
fi

exec "$ROOT/scripts/linux/start_hardware_stack.sh" op_port:="$op_port"
