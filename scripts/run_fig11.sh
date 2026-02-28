#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=scripts/_common.sh
source "$SCRIPT_DIR/_common.sh"

LOG_FILE=$(setup_log "$ROOT_DIR/logs/run" "run_fig11")
start_logging "$LOG_FILE"

echo "[INFO] Fig.11 automation scaffold"

if [[ -f "$ROOT_DIR/results/csv/fig11_kmeans_scaling.csv" ]]; then
  python3 "$ROOT_DIR/scripts/plot_fig11.py" \
    --input "$ROOT_DIR/results/csv/fig11_kmeans_scaling.csv" \
    --out "$ROOT_DIR/results/plots/fig11.png"
  echo "[PASS] Fig.11 plot generated"
else
  fail_gate "GATE 9" "Fig.11 CSV missing; k-means scaling runs not yet completed" "$LOG_FILE"
  exit 1
fi
