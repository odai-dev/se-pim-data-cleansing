#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=scripts/_common.sh
source "$SCRIPT_DIR/_common.sh"

LOG_FILE=$(setup_log "$ROOT_DIR/logs/run" "run_gate5_command_smoke")
start_logging "$LOG_FILE"

OUTDIR=${OUTDIR:-$ROOT_DIR/results/raw/gate5_sepim_cmd_smoke}

echo "[INFO] Running GATE 5 SE-PIM command smoke test"
OUTDIR="$OUTDIR" "$SCRIPT_DIR/run_baseline_fs.sh" --mode sepim_cmd_smoke

echo "[PASS] run_gate5_command_smoke.sh completed"
