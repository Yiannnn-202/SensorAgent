#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ros_distro="${ROS_DISTRO:-humble}"
ros_setup="${ROS_SETUP:-${SENSORAGENT_ROS_SETUP:-/opt/ros/${ros_distro}/setup.bash}}"
workspace_setup="${SENSORAGENT_ROS_WS_SETUP:-${ROOT}/ros2_ws/install/local_setup.bash}"

if [[ ! -f "${ros_setup}" ]]; then
  echo "ROS 2 setup file not found: ${ros_setup}" >&2
  echo "Install ROS 2 or set ROS_SETUP=/path/to/setup.bash." >&2
  exit 1
fi

if [[ ! -f "${workspace_setup}" ]]; then
  echo "SensorAgent ROS workspace setup file not found: ${workspace_setup}" >&2
  echo "Run scripts/linux/prepare_hardware_stack.sh or set SENSORAGENT_ROS_WS_SETUP." >&2
  exit 1
fi

unset AMENT_PREFIX_PATH COLCON_PREFIX_PATH CMAKE_PREFIX_PATH PYTHONPATH LD_LIBRARY_PATH
set +u
source "${ros_setup}"
source "${workspace_setup}"
set -u
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export ROS_DOMAIN_ID=0
echo "[SensorAgent] Using integrated ROS 2 workspace: ${workspace_setup}"
exec ros2 launch sensoragent_hardware_bridge hardware_stack.launch.py "$@"
