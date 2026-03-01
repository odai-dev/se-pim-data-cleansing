#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=scripts/_common.sh
source "$SCRIPT_DIR/_common.sh"

MODE=quick
if [[ "${1:-}" == "--full" ]]; then
  MODE=full
elif [[ "${1:-}" == "--quick" || -z "${1:-}" ]]; then
  MODE=quick
else
  echo "[ERROR] Usage: $0 [--quick|--full]"
  exit 2
fi

LOG_FILE=$(setup_log "$ROOT_DIR/logs/run" "run_gate9_kmeans_${MODE}")
start_logging "$LOG_FILE"

CSV_OUT="$ROOT_DIR/results/csv/fig11_kmeans_scaling.csv"
PLOT_OUT="$ROOT_DIR/results/plots/fig11.png"
TMP_CSV="$ROOT_DIR/results/csv/.fig11_tmp.csv"
WORKLOAD_DIR="$ROOT_DIR/IMPICA/workloads/kmeans_sepim"

mkdir -p "$ROOT_DIR/results/csv" "$ROOT_DIR/results/plots"

echo "[INFO] Building kmeans_sepim workload generator"
if ! make -C "$WORKLOAD_DIR" clean; then
  fail_gate "GATE 9" "Failed to clean kmeans_sepim" "$LOG_FILE"
  exit 1
fi
if ! make -C "$WORKLOAD_DIR"; then
  fail_gate "GATE 9" "Failed to build kmeans_sepim" "$LOG_FILE"
  exit 1
fi

echo "[INFO] Generating Fig.11 k-means scaling CSV ($MODE)"
if ! "$WORKLOAD_DIR/kmeans_sepim" > "$TMP_CSV"; then
  fail_gate "GATE 9" "kmeans_sepim execution failed" "$LOG_FILE"
  exit 1
fi
if [[ "$MODE" == "quick" ]]; then
  awk -F, 'NR==1 || $1+0<=128' "$TMP_CSV" > "$CSV_OUT"
else
  mv "$TMP_CSV" "$CSV_OUT"
fi
rm -f "$TMP_CSV"

if ! python3 "$ROOT_DIR/scripts/plot_fig11.py" \
  --input "$CSV_OUT" \
  --out "$PLOT_OUT"; then
  fail_gate "GATE 9" "plot_fig11.py failed" "$LOG_FILE"
  exit 1
fi

python3 - "$CSV_OUT" <<'PY'
import csv
import sys
rows = list(csv.DictReader(open(sys.argv[1], "r", newline="")))
for r in rows:
    if int(float(r["dataset_mb"])) == 512 and int(float(r["pim_cores"])) == 8:
        print("[INFO] Fig11 summary: 512MB/8core sepim=%.3fs speedup=%.3fx overhead=%.3f%%" %
              (float(r["sepim_sec"]), float(r["speedup_vs_cpu"]), float(r["overhead_pct"])))
        break
PY

mark_gate_pass "GATE9" "Fig.11 CSV/plot generated in $MODE mode"
echo "[PASS] run_gate9_kmeans.sh completed"
