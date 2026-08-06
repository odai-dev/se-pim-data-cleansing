#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=scripts/_common.sh
source "$SCRIPT_DIR/_common.sh"
ORIG_ARGS=("$@")
IMAGE_NAME=${IMAGE_NAME:-sepim-impica@sha256:e5caacbf042ea2c2dd87a350ca35467d09aec2c0e4fac2a1de728bb1a93f308a}
maybe_reexec_in_container always "scripts/$(basename "$0")" "${ORIG_ARGS[@]}"

trap 'chown -R "${HOST_UID:-0}:${HOST_GID:-0}" \
  "$ROOT_DIR/results" "$ROOT_DIR/logs" 2>/dev/null || true' EXIT

LOG_FILE=$(setup_log "$ROOT_DIR/logs/run" "run_gate5_command_smoke")
start_logging "$LOG_FILE"

RUN_ID="gate5_sepim_cmd_smoke_$(date +%Y%m%d_%H%M%S)"
OUTDIR=${OUTDIR:-$ROOT_DIR/results/raw/$RUN_ID}

echo "[INFO] Running GATE 5 SE-PIM command smoke test"
OUTDIR="$OUTDIR" MEM_SIZE=2048MB SEPIM_KERNEL_MEM=1984MB \
  "$SCRIPT_DIR/run_baseline_fs.sh" --mode sepim_cmd_smoke

echo "[PASS] run_gate5_command_smoke.sh completed"
