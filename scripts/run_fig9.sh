#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=scripts/_common.sh
source "$SCRIPT_DIR/_common.sh"

LOG_FILE=$(setup_log "$ROOT_DIR/logs/run" "run_fig9")
start_logging "$LOG_FILE"

echo "[INFO] Fig.9 automation scaffold"
echo "[INFO] This script expects DMA benchmark results CSV at results/csv/fig9_dma.csv"

if [[ -f "$ROOT_DIR/results/csv/fig9_dma.csv" ]]; then
  python3 "$ROOT_DIR/scripts/plot_fig9.py" \
    --input "$ROOT_DIR/results/csv/fig9_dma.csv" \
    --out "$ROOT_DIR/results/plots/fig9.png"
  echo "[PASS] Fig.9 plot generated"
else
  fail_gate "GATE 6" "Fig.9 CSV missing; run DMA benchmark first" "$LOG_FILE"
  exit 1
fi
