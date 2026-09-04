#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ros_distro="${ROS_DISTRO:-humble}"
ros_setup="${ROS_SETUP:-${SENSORAGENT_ROS_SETUP:-/opt/ros/${ros_distro}/setup.bash}}"
island_arm_setup="${ISLAND_ARM_SETUP:-${SENSORAGENT_ISLAND_ARM_SETUP:-}}"
workspace_setup="${SENSORAGENT_ROS_WS_SETUP:-${ROOT}/ros2_ws/install/local_setup.bash}"

if [[ -z "${island_arm_setup}" ]]; then
  for candidate in "${HOME}/Island-Arm/install/setup.bash"; do
    if [[ -f "${candidate}" ]]; then
      island_arm_setup="${candidate}"
      break
    fi
  done
fi

if [[ ! -f "${ros_setup}" ]]; then
  echo "ROS 2 setup file not found: ${ros_setup}" >&2
  echo "Install ROS 2 or set ROS_SETUP=/path/to/setup.bash." >&2
  exit 1
fi

if [[ -z "${island_arm_setup}" || ! -f "${island_arm_setup}" ]]; then
  echo "Island-Arm setup file not found." >&2
  echo "Set ISLAND_ARM_SETUP=/path/to/Island-Arm/install/setup.bash." >&2
  exit 1
fi

if [[ ! -f "${workspace_setup}" ]]; then
  echo "SensorAgent ROS workspace setup file not found: ${workspace_setup}" >&2
  echo "Run scripts/linux/prepare_rm65_b_sim.sh or set SENSORAGENT_ROS_WS_SETUP." >&2
  exit 1
fi

unset AMENT_PREFIX_PATH COLCON_PREFIX_PATH CMAKE_PREFIX_PATH PYTHONPATH LD_LIBRARY_PATH
set +u
source "${ros_setup}"
source "${island_arm_setup}"
source "${workspace_setup}"
set -u
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export ROS_DOMAIN_ID=0
exec ros2 launch sensoragent_hardware_bridge hardware_stack.launch.py "$@"
