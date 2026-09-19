#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ros_distro="${ROS_DISTRO:-humble}"
ros_setup="${SENSORAGENT_ROS_SETUP:-/opt/ros/${ros_distro}/setup.bash}"

if [[ ! -f "${ros_setup}" ]]; then
  echo "ROS 2 setup file not found: ${ros_setup}" >&2
  exit 1
fi

set +u
source "${ros_setup}"
set -u

rosdep install \
  --from-paths \
    "${ROOT}/ros2_ws/src/island_arm" \
    "${ROOT}/ros2_ws/src/rm_description" \
    "${ROOT}/ros2_ws/src/sensoragent_hardware_bridge" \
  --ignore-src \
  --rosdistro "${ros_distro}" \
  --skip-keys "ament_python librealsense2 librealsense2-dev" \
  -r -y

export CMAKE_BUILD_PARALLEL_LEVEL="${CMAKE_BUILD_PARALLEL_LEVEL:-1}"
colcon --log-base "${ROOT}/ros2_ws/log" build \
  --base-paths "${ROOT}/ros2_ws/src" \
  --build-base "${ROOT}/ros2_ws/build" \
  --install-base "${ROOT}/ros2_ws/install" \
  --executor sequential \
  --symlink-install \
  --packages-up-to \
    sensoragent_hardware_bridge \
    rm_driver \
    arm_control \
    op_control \
    vision_dep

echo "SensorAgent integrated physical hardware stack is ready."
