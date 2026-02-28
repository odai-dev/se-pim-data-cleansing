#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=scripts/_common.sh
source "$SCRIPT_DIR/_common.sh"

LOG_FILE=$(setup_log "$ROOT_DIR/logs/run" "run_fig10")
start_logging "$LOG_FILE"

echo "[INFO] Fig.10 automation scaffold"

if [[ -f "$ROOT_DIR/results/csv/fig10_controlled_access.csv" ]]; then
  python3 "$ROOT_DIR/scripts/plot_fig10.py" \
    --input "$ROOT_DIR/results/csv/fig10_controlled_access.csv" \
    --out "$ROOT_DIR/results/plots/fig10.png"
  echo "[PASS] Fig.10 plot generated"
else
  fail_gate "GATE 7" "Fig.10 CSV missing; controlled access benchmark not yet run" "$LOG_FILE"
  exit 1
fi
