#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=scripts/_common.sh
source "$SCRIPT_DIR/_common.sh"

LOG_FILE=$(setup_log "$ROOT_DIR/logs/run" "run_fig8")
start_logging "$LOG_FILE"

echo "[INFO] Fig.8 automation scaffold"
echo "[INFO] This script expects SE-PIM tracer-enabled config and workloads to be implemented."

echo "[TODO] 1) run CPU-only hash lookup scenario"
echo "[TODO] 2) run SE-PIM psearch scenario"
echo "[TODO] 3) produce results/csv/fig8_cpu.csv + fig8_sepim.csv"
echo "[TODO] 4) invoke plot_fig8.py"

if [[ -f "$ROOT_DIR/results/csv/fig8_cpu.csv" && -f "$ROOT_DIR/results/csv/fig8_sepim.csv" ]]; then
  python3 "$ROOT_DIR/scripts/plot_fig8.py" \
    --cpu "$ROOT_DIR/results/csv/fig8_cpu.csv" \
    --sepim "$ROOT_DIR/results/csv/fig8_sepim.csv" \
    --out "$ROOT_DIR/results/plots/fig8.png"
  echo "[PASS] Fig.8 plot generated from existing CSVs"
else
  fail_gate "GATE 8" "Fig.8 inputs missing; tracer pipeline not yet executed" "$LOG_FILE"
  exit 1
fi
