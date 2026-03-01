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
FAST_INPUT_SIZE=${FAST_INPUT_SIZE:-0}
RUN_ID=${RUN_ID:-$(date -u +%Y%m%dT%H%M%SZ)}
HOST_UID=${HOST_UID:-$(id -u)}
HOST_GID=${HOST_GID:-$(id -g)}
BASELINE_CHECKPOINT_DIR=${BASELINE_CHECKPOINT_DIR:-/workspace/results/raw/baseline_fs_checkpoint}

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
    --run-id)
      if [[ $# -lt 2 ]]; then
        echo "[ERROR] --run-id requires a value"
        exit 2
      fi
      RUN_ID="$2"
      shift 2
      ;;
    --run-id=*)
      RUN_ID="${1#*=}"
      shift
      ;;
    *)
      echo "[ERROR] Unknown argument: $1"
      echo "[INFO] Usage: scripts/run_gate3_container.sh [--fast-input-size N] [--reuse-checkpoint 0|1] [--run-hash-table 0|1] [--run-id ID]"
      exit 2
      ;;
  esac
done

CHECKPOINT_OUTDIR=${CHECKPOINT_OUTDIR:-/workspace/results/raw/gate3_${RUN_ID}_checkpoint}
HASH_OUTDIR=${HASH_OUTDIR:-/workspace/results/raw/gate3_${RUN_ID}_hash_table}

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

CMD="scripts/fetch_gem5_fs.sh && scripts/prebuild_guest_workloads.sh && scripts/prepare_disk_image.sh && RESTORE_CKPT_DIR=\"\""
if [[ "$REUSE_CHECKPOINT" == "1" ]]; then
  CMD="$CMD && if ls \"$CHECKPOINT_OUTDIR\"/cpt.* >/dev/null 2>&1; then echo '[INFO] Reusing existing run-specific checkpoint'; RESTORE_CKPT_DIR=\"$CHECKPOINT_OUTDIR\"; elif ls \"$BASELINE_CHECKPOINT_DIR\"/cpt.* >/dev/null 2>&1; then echo '[INFO] Reusing existing baseline checkpoint at $BASELINE_CHECKPOINT_DIR'; mkdir -p \"$CHECKPOINT_OUTDIR\"; echo \"$BASELINE_CHECKPOINT_DIR\" > \"$CHECKPOINT_OUTDIR/REUSED_FROM_BASELINE_CHECKPOINT\"; RESTORE_CKPT_DIR=\"$BASELINE_CHECKPOINT_DIR\"; else OUTDIR=\"$CHECKPOINT_OUTDIR\" scripts/run_baseline_fs.sh --mode checkpoint; RESTORE_CKPT_DIR=\"$CHECKPOINT_OUTDIR\"; fi"
else
  CMD="$CMD && OUTDIR=\"$CHECKPOINT_OUTDIR\" scripts/run_baseline_fs.sh --mode checkpoint && RESTORE_CKPT_DIR=\"$CHECKPOINT_OUTDIR\""
fi
if [[ "$RUN_HASH_TABLE" == "1" ]]; then
  CMD="$CMD && if [[ -z \"\$RESTORE_CKPT_DIR\" ]]; then echo '[ERROR] Missing restore checkpoint directory'; exit 1; fi && echo \"[INFO] Restoring hash_table run from checkpoint dir: \$RESTORE_CKPT_DIR\" && GEM5_EXTRA_ARGS=\"-r 1 --checkpoint-dir=\$RESTORE_CKPT_DIR\" OUTDIR=\"$HASH_OUTDIR\" scripts/run_baseline_fs.sh --mode hash_table"
fi

echo "[INFO] Running GATE 3 inside container image: $IMAGE_NAME"
echo "[INFO] RUN_ID=$RUN_ID REUSE_CHECKPOINT=$REUSE_CHECKPOINT FAST_INPUT_SIZE=$FAST_INPUT_SIZE"
echo "[INFO] CHECKPOINT_OUTDIR=$CHECKPOINT_OUTDIR"
echo "[INFO] HASH_OUTDIR=$HASH_OUTDIR"
echo "[INFO] BASELINE_CHECKPOINT_DIR=$BASELINE_CHECKPOINT_DIR"
set +e
"${RUNTIME[@]}" run --rm --privileged \
  --name "$CONTAINER_NAME" \
  -e CHROOT_BUILD=0 \
  -e RUN_HASH_TABLE="$RUN_HASH_TABLE" \
  -e REUSE_CHECKPOINT="$REUSE_CHECKPOINT" \
  -e FAST_INPUT_SIZE="$FAST_INPUT_SIZE" \
  -e HOST_UID="$HOST_UID" \
  -e HOST_GID="$HOST_GID" \
  -e BASELINE_CHECKPOINT_DIR="$BASELINE_CHECKPOINT_DIR" \
  -v "$ROOT_DIR:/workspace" \
  -w /workspace \
  "$IMAGE_NAME" \
  /bin/bash -lc "set -euo pipefail; trap 'chown -R \"\$HOST_UID:\$HOST_GID\" /workspace/IMPICA/workloads/hashtable /workspace/IMPICA/workloads/sepim_cmd /workspace/results /workspace/logs /workspace/scripts/guest_boot_checkpoint.rcS /workspace/scripts/guest_boot_probe.rcS /workspace/scripts/guest_run_hashtable.rcS /workspace/scripts/guest_run_sepim_cmd.rcS 2>/dev/null || true' EXIT; $CMD"
RC=$?
set -e

if [[ $RC -ne 0 ]]; then
  fail_gate "GATE 3" "Containerized GATE 3 flow failed" "$LOG_FILE"
  exit "$RC"
fi

trap - INT TERM EXIT
cleanup_container

if [[ -f "$ROOT_DIR/logs/FAILED_GATE.txt" ]]; then
  rm -f "$ROOT_DIR/logs/FAILED_GATE.txt"
fi
{
  echo "timestamp=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "gate=GATE 3"
  echo "status=PASS"
  echo "log_file=$LOG_FILE"
  echo "checkpoint_outdir=${CHECKPOINT_OUTDIR}"
  echo "hash_outdir=${HASH_OUTDIR}"
} > "$ROOT_DIR/logs/PASSED_GATE3.txt"

echo "[PASS] run_gate3_container.sh completed"
