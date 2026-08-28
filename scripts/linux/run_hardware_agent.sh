#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CONFIG="${ROOT}/configs/competition_hardware.yaml"
MODE="text"
ENABLE_MOTION="false"
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
    --enable-motion)
      ENABLE_MOTION="true"
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

HW_PID=""
cleanup() {
  if [[ -n "${HW_PID}" ]] && kill -0 "${HW_PID}" >/dev/null 2>&1; then
    curl --silent --show-error --max-time 2 -X POST http://127.0.0.1:8766/stop >/dev/null || true
    kill "${HW_PID}" >/dev/null 2>&1 || true
    wait "${HW_PID}" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT INT TERM

cd "${ROOT}"
if [[ "${START_STACK}" == "true" ]]; then
  echo "[SensorAgent] Starting hardware bridge stack (allow_motion=${ENABLE_MOTION})..."
  bash "${ROOT}/scripts/linux/start_hardware_stack.sh" "allow_motion:=${ENABLE_MOTION}" &
  HW_PID="$!"
fi

if [[ "${ENABLE_MOTION}" != "true" ]]; then
  echo "[SensorAgent] Hardware motion is disabled. Add --enable-motion only after operator safety checks."
fi

SESSION_ARGS=(
  "${ROOT}/scripts/linux/run_competition_sorting_session.py"
  --backend hardware
  --config "${CONFIG}"
  --mode "${MODE}"
)
if [[ "${ENABLE_MOTION}" == "true" ]]; then
  SESSION_ARGS+=(--execute)
fi
SESSION_ARGS+=("${EXTRA_ARGS[@]}")

echo "[SensorAgent] Starting industrial hardware agent loop..."
PYTHONPATH="${ROOT}/src" python3 "${SESSION_ARGS[@]}"
