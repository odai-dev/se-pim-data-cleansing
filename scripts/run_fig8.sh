#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=scripts/_common.sh
source "$SCRIPT_DIR/_common.sh"

LOG_FILE=$(setup_log "$ROOT_DIR/logs/run" "run_fig8")
start_logging "$LOG_FILE"

MODE_ARG=${MODE_ARG:---quick}
echo "[INFO] Running GATE 8 pipeline via run_gate8_trace.sh $MODE_ARG"
"$ROOT_DIR/scripts/run_gate8_trace.sh" --backend fs "$MODE_ARG"
echo "[PASS] Fig.8 plot generated"
