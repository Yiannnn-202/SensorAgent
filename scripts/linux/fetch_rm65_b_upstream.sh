#!/usr/bin/env bash
set -euo pipefail

readonly UPSTREAM_URL="https://github.com/RealManRobot/ros2_rm_robot.git"
readonly UPSTREAM_BRANCH="humble"
readonly UPSTREAM_COMMIT="c941b565e4f9174afa36561f143ef5fbbb744750"

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cache_root="${XDG_CACHE_HOME:-${HOME}/.cache}/sensoragent"
clone_dir="${cache_root}/ros2_rm_robot"
ros2_src="${repo_root}/ros2_ws/src"

rm -rf "${clone_dir}"
mkdir -p "${cache_root}"

git clone \
  --depth 1 \
  --filter=blob:none \
  --sparse \
  --single-branch \
  --branch "${UPSTREAM_BRANCH}" \
  "${UPSTREAM_URL}" \
  "${clone_dir}"

git -C "${clone_dir}" fetch --depth 1 origin "${UPSTREAM_COMMIT}"
git -C "${clone_dir}" checkout --detach "${UPSTREAM_COMMIT}"

git -C "${clone_dir}" sparse-checkout set --no-cone \
  "/rm_description/CMakeLists.txt" \
  "/rm_description/package.xml" \
  "/rm_description/config/joint_names_rm_65_description.yaml" \
  "/rm_description/launch/rm_65_display.launch.py" \
  "/rm_description/meshes/rm_65_arm/" \
  "/rm_description/rviz/rm_65.rviz" \
  "/rm_description/urdf/rm_65.urdf" \
  "/rm_description/urdf/rm_65_gazebo.urdf" \
  "/rm_gazebo/CMakeLists.txt" \
  "/rm_gazebo/package.xml" \
  "/rm_gazebo/config/gazebo_65*" \
  "/rm_gazebo/launch/gazebo_65*" \
  "/rm_gazebo/launch/gz_demo_common.py" \
  "/rm_moveit2_config/rm_65_config/"

actual_commit="$(git -C "${clone_dir}" rev-parse HEAD)"
if [[ "${actual_commit}" != "${UPSTREAM_COMMIT}" ]]; then
  echo "Unexpected upstream commit: ${actual_commit}" >&2
  exit 1
fi

description_dir="${ros2_src}/rm_description"
gazebo_dir="${ros2_src}/rm_gazebo"
moveit_dir="${ros2_src}/rm_65_config"

rm -rf "${description_dir}" "${gazebo_dir}" "${moveit_dir}"
mkdir -p "${description_dir}" "${gazebo_dir}" "${moveit_dir}"
touch \
  "${description_dir}/.gitkeep" \
  "${gazebo_dir}/.gitkeep" \
  "${moveit_dir}/.gitkeep"

copy_file() {
  local source_path="$1"
  local destination_path="$2"
  install -D -m 0644 "${clone_dir}/${source_path}" "${destination_path}"
}

copy_file "rm_description/CMakeLists.txt" "${description_dir}/CMakeLists.txt"
copy_file "rm_description/package.xml" "${description_dir}/package.xml"
copy_file \
  "rm_description/config/joint_names_rm_65_description.yaml" \
  "${description_dir}/config/joint_names_rm_65_description.yaml"
copy_file \
  "rm_description/launch/rm_65_display.launch.py" \
  "${description_dir}/launch/rm_65_display.launch.py"
copy_file "rm_description/rviz/rm_65.rviz" "${description_dir}/rviz/rm_65.rviz"

for mesh in base_link.STL link1.STL link2.STL link3.STL link4.STL link5.STL link6.STL; do
  copy_file \
    "rm_description/meshes/rm_65_arm/${mesh}" \
    "${description_dir}/meshes/rm_65_arm/${mesh}"
done

for model_file in rm_65.urdf rm_65_gazebo.urdf; do
  copy_file \
    "rm_description/urdf/${model_file}" \
    "${description_dir}/urdf/${model_file}"
done

copy_file "rm_gazebo/CMakeLists.txt" "${gazebo_dir}/CMakeLists.txt"
copy_file "rm_gazebo/package.xml" "${gazebo_dir}/package.xml"
copy_file \
  "rm_gazebo/config/gazebo_65_description.urdf.xacro" \
  "${gazebo_dir}/config/gazebo_65_description.urdf.xacro"
copy_file \
  "rm_gazebo/launch/gazebo_65_demo.launch.py" \
  "${gazebo_dir}/launch/gazebo_65_demo.launch.py"
copy_file \
  "rm_gazebo/launch/gz_demo_common.py" \
  "${gazebo_dir}/launch/gz_demo_common.py"

copy_file \
  "rm_moveit2_config/rm_65_config/.setup_assistant" \
  "${moveit_dir}/.setup_assistant"
copy_file \
  "rm_moveit2_config/rm_65_config/CMakeLists.txt" \
  "${moveit_dir}/CMakeLists.txt"
copy_file \
  "rm_moveit2_config/rm_65_config/package.xml" \
  "${moveit_dir}/package.xml"

for config_file in \
  initial_positions.yaml \
  joint_limits.yaml \
  kinematics.yaml \
  moveit.rviz \
  moveit_controllers.yaml \
  pilz_cartesian_limits.yaml \
  rm_65_description.ros2_control.xacro \
  rm_65_description.srdf \
  rm_65_description.urdf.xacro \
  ros2_controllers.yaml; do
  copy_file \
    "rm_moveit2_config/rm_65_config/config/${config_file}" \
    "${moveit_dir}/config/${config_file}"
done

for launch_file in \
  demo.launch.py \
  gazebo_moveit_demo.launch.py \
  move_group.launch.py \
  moveit_rviz.launch.py \
  rsp.launch.py \
  setup_assistant.launch.py \
  spawn_controllers.launch.py \
  static_virtual_joint_tfs.launch.py \
  warehouse_db.launch.py; do
  copy_file \
    "rm_moveit2_config/rm_65_config/launch/${launch_file}" \
    "${moveit_dir}/launch/${launch_file}"
done

python3 - \
  "${description_dir}/CMakeLists.txt" \
  "${gazebo_dir}/package.xml" \
  "${moveit_dir}/package.xml" <<'PY'
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

description_cmake = Path(sys.argv[1])
gazebo_package = Path(sys.argv[2])
moveit_package = Path(sys.argv[3])

cmake = description_cmake.read_text(encoding="utf-8")
cmake = cmake.replace(
    "DIRECTORY launch urdf meshes rviz",
    "DIRECTORY config launch urdf meshes rviz",
)
cmake = cmake.replace(
    "\ninstall(\n  PROGRAMS scripts/dual_arm_joint_state_bridge.py\n"
    "  DESTINATION lib/${PROJECT_NAME}\n)\n",
    "\n",
)
description_cmake.write_text(cmake, encoding="utf-8")

tree = ET.parse(gazebo_package)
root = tree.getroot()
excluded = {
    "rm_63_config",
    "rm_75_config",
    "rm_eco62_config",
    "rm_eco63_config",
    "rm_eco65_config",
    "rm_gen72_config",
    "rm_rx75_config",
}
for dependency in list(root.findall("exec_depend")):
    if dependency.text in excluded:
        root.remove(dependency)
ET.indent(tree, space="  ")
tree.write(gazebo_package, encoding="utf-8", xml_declaration=True)

tree = ET.parse(moveit_package)
root = tree.getroot()
for dependency in root.findall("exec_depend"):
    if dependency.text == "rm_65_description":
        dependency.text = "rm_description"
ET.indent(tree, space="  ")
tree.write(moveit_package, encoding="utf-8", xml_declaration=True)
PY

echo "Imported RM65-B simulation files from ${UPSTREAM_COMMIT}."
