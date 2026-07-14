#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
workspace="${repo_root}/ros2_ws"
ros_distro="${ROS_DISTRO:-humble}"
ros_setup="/opt/ros/${ros_distro}/setup.bash"
workspace_setup="${workspace}/install/setup.bash"

if [[ ! -f "${ros_setup}" ]]; then
  echo "ROS 2 setup file not found: ${ros_setup}" >&2
  exit 1
fi

if [[ ! -f "${workspace_setup}" ]]; then
  echo "The ROS 2 workspace has not been built." >&2
  echo "Run this once first:" >&2
  echo "  bash scripts/linux/prepare_rm65_b_sim.sh" >&2
  exit 1
fi

# shellcheck disable=SC1090
source "${ros_setup}"
# shellcheck disable=SC1090
source "${workspace_setup}"

exec ros2 launch \
  sensoragent_rm65_b_bringup \
  full_demo.launch.py \
  "$@"
