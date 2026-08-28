#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CONFIG="${ROOT}/configs/competition_sim.yaml"
MODE="text"
EXECUTE="true"
START_STACK="true"
EXTRA_ARGS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --mode)
      MODE="$2"
      shift 2
      ;;
    --config)
      CONFIG="$2"
      shift 2
      ;;
    --dry-run|--no-execute)
      EXECUTE="false"
      shift
      ;;
    --no-start-stack)
      START_STACK="false"
      shift
      ;;
    *)
      EXTRA_ARGS+=("$1")
      shift
      ;;
  esac
done

SIM_PID=""
cleanup() {
  if [[ -n "${SIM_PID}" ]] && kill -0 "${SIM_PID}" >/dev/null 2>&1; then
    kill "${SIM_PID}" >/dev/null 2>&1 || true
    wait "${SIM_PID}" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT INT TERM

cd "${ROOT}"
if [[ "${START_STACK}" == "true" && "${EXECUTE}" == "true" ]]; then
  echo "[SensorAgent] Starting Gazebo/MoveIt simulation stack..."
  bash "${ROOT}/scripts/linux/run_industrial_sorting_metal_sim.sh" &
  SIM_PID="$!"
fi

SESSION_ARGS=(
  "${ROOT}/scripts/linux/run_competition_sorting_session.py"
  --backend sim
  --config "${CONFIG}"
  --mode "${MODE}"
)
if [[ "${EXECUTE}" == "true" ]]; then
  SESSION_ARGS+=(--execute)
fi
SESSION_ARGS+=("${EXTRA_ARGS[@]}")

echo "[SensorAgent] Starting industrial simulation agent loop..."
PYTHONPATH="${ROOT}/src" python3 "${SESSION_ARGS[@]}"
