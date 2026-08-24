#!/usr/bin/env bash
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
unset AMENT_PREFIX_PATH COLCON_PREFIX_PATH CMAKE_PREFIX_PATH PYTHONPATH LD_LIBRARY_PATH
source /opt/ros/humble/setup.bash
source /home/hcn/Island-Arm/install/setup.bash
source "$ROOT/ros2_ws/install/local_setup.bash"
set -euo pipefail
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export ROS_DOMAIN_ID=0
exec ros2 launch sensoragent_hardware_bridge hardware_stack.launch.py "$@"
