#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
workspace="${repo_root}/ros2_ws"
ros_distro="${ROS_DISTRO:-humble}"
ros_setup="/opt/ros/${ros_distro}/setup.bash"

if [[ ! -f "${ros_setup}" ]]; then
  echo "ROS 2 setup file not found: ${ros_setup}" >&2
  echo "Install ROS 2 Humble or set ROS_DISTRO to the installed distribution." >&2
  exit 1
fi

for command_name in rosdep colcon; do
  if ! command -v "${command_name}" >/dev/null 2>&1; then
    echo "Required command not found: ${command_name}" >&2
    echo "Install python3-rosdep and python3-colcon-common-extensions first." >&2
    exit 1
  fi
done

# shellcheck disable=SC1090
set +u
source "${ros_setup}"
set -u

rosdep install \
  --from-paths \
    "${workspace}/src/rm_description" \
    "${workspace}/src/rm_gazebo" \
    "${workspace}/src/rm_65_config" \
    "${workspace}/src/robotiq_description" \
    "${workspace}/src/sensoragent_robot_bridge" \
    "${workspace}/src/sensoragent_rm65_b_bringup" \
  --ignore-src \
  --rosdistro "${ros_distro}" \
  --skip-keys "ament_python" \
  -r -y

cd "${workspace}"
colcon build \
  --symlink-install \
  --packages-select \
    rm_description \
    rm_65_config \
    rm_gazebo \
    robotiq_description \
    sensoragent_robot_bridge \
    sensoragent_rm65_b_bringup

echo
echo "RM65-B simulation is ready."
echo "Start it with:"
echo "  bash scripts/linux/run_rm65_b_sim.sh"
