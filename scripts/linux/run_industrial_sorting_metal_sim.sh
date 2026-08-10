#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

exec bash "${repo_root}/scripts/linux/run_rm65_b_sim.sh" \
  world_file:=industrial_sorting_metal_pgs.sdf \
  robot_mount_yaw:=3.141592653589793 \
  robot_mount_y:=0.0 \
  "$@"
