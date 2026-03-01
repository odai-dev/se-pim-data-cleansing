#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=scripts/_common.sh
source "$SCRIPT_DIR/_common.sh"

LOG_FILE=$(setup_log "$ROOT_DIR/logs/run" "run_fig9")
start_logging "$LOG_FILE"

echo "[INFO] Fig.9 automation scaffold"
MODE_ARG=${MODE_ARG:---quick}
echo "[INFO] Running GATE 6 pipeline via run_gate6_dma.sh $MODE_ARG"
"$ROOT_DIR/scripts/run_gate6_dma.sh" --backend fs "$MODE_ARG"
echo "[PASS] Fig.9 plot generated"
