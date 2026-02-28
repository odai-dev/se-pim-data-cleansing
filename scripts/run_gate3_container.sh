#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=scripts/_common.sh
source "$SCRIPT_DIR/_common.sh"

LOG_FILE=$(setup_log "$ROOT_DIR/logs/run" "gate3_container")
start_logging "$LOG_FILE"

IMAGE_NAME=${IMAGE_NAME:-sepim-impica:ubuntu18}
RUN_HASH_TABLE=${RUN_HASH_TABLE:-1}
REUSE_CHECKPOINT=${REUSE_CHECKPOINT:-1}
FAST_INPUT_SIZE=${FAST_INPUT_SIZE:-4096}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --fast-input-size)
      if [[ $# -lt 2 ]]; then
        echo "[ERROR] --fast-input-size requires a numeric value"
        exit 2
      fi
      FAST_INPUT_SIZE="$2"
      shift 2
      ;;
    --fast-input-size=*)
      FAST_INPUT_SIZE="${1#*=}"
      shift
      ;;
    --reuse-checkpoint)
      if [[ $# -lt 2 ]]; then
        echo "[ERROR] --reuse-checkpoint requires 0 or 1"
        exit 2
      fi
      REUSE_CHECKPOINT="$2"
      shift 2
      ;;
    --reuse-checkpoint=*)
      REUSE_CHECKPOINT="${1#*=}"
      shift
      ;;
    --run-hash-table)
      if [[ $# -lt 2 ]]; then
        echo "[ERROR] --run-hash-table requires 0 or 1"
        exit 2
      fi
      RUN_HASH_TABLE="$2"
      shift 2
      ;;
    --run-hash-table=*)
      RUN_HASH_TABLE="${1#*=}"
      shift
      ;;
    *)
      echo "[ERROR] Unknown argument: $1"
      echo "[INFO] Usage: scripts/run_gate3_container.sh [--fast-input-size N] [--reuse-checkpoint 0|1] [--run-hash-table 0|1]"
      exit 2
      ;;
  esac
done

if command -v docker >/dev/null 2>&1; then
  if docker info >/dev/null 2>&1; then
    RUNTIME=(docker)
  elif sudo -n docker info >/dev/null 2>&1; then
    RUNTIME=(sudo -n docker)
  else
    fail_gate "GATE 3" "Docker installed but not accessible non-interactively; run this script as root/sudo" "$LOG_FILE"
    exit 1
  fi
elif command -v podman >/dev/null 2>&1; then
  RUNTIME=(podman)
else
  fail_gate "GATE 3" "No docker/podman runtime found" "$LOG_FILE"
  exit 1
fi

CONTAINER_NAME="sepim-gate3-$$"
cleanup_container() {
  "${RUNTIME[@]}" rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true
}
trap cleanup_container INT TERM EXIT

CMD="scripts/fetch_gem5_fs.sh && scripts/prebuild_guest_workloads.sh && scripts/prepare_disk_image.sh"
if [[ "$REUSE_CHECKPOINT" == "1" ]]; then
  CMD="$CMD && if ls /workspace/results/raw/baseline_fs_checkpoint/cpt.* >/dev/null 2>&1; then echo '[INFO] Reusing existing baseline checkpoint'; else scripts/run_baseline_fs.sh --mode checkpoint; fi"
else
  CMD="$CMD && scripts/run_baseline_fs.sh --mode checkpoint"
fi
if [[ "$RUN_HASH_TABLE" == "1" ]]; then
  CMD="$CMD && scripts/run_baseline_fs.sh --mode hash_table"
fi

echo "[INFO] Running GATE 3 inside container image: $IMAGE_NAME"
echo "[INFO] REUSE_CHECKPOINT=$REUSE_CHECKPOINT FAST_INPUT_SIZE=$FAST_INPUT_SIZE"
set +e
"${RUNTIME[@]}" run --rm --privileged \
  --name "$CONTAINER_NAME" \
  -e CHROOT_BUILD=0 \
  -e RUN_HASH_TABLE="$RUN_HASH_TABLE" \
  -e REUSE_CHECKPOINT="$REUSE_CHECKPOINT" \
  -e FAST_INPUT_SIZE="$FAST_INPUT_SIZE" \
  -v "$ROOT_DIR:/workspace" \
  -w /workspace \
  "$IMAGE_NAME" \
  /bin/bash -lc "$CMD"
RC=$?
set -e

if [[ $RC -ne 0 ]]; then
  fail_gate "GATE 3" "Containerized GATE 3 flow failed" "$LOG_FILE"
  exit "$RC"
fi

trap - INT TERM EXIT
cleanup_container

echo "[PASS] run_gate3_container.sh completed"
