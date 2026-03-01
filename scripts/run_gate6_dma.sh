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

LOG_FILE=$(setup_log "$ROOT_DIR/logs/run" "run_gate6_dma_${MODE}")
start_logging "$LOG_FILE"

CSV_OUT="$ROOT_DIR/results/csv/fig9_dma.csv"
PLOT_OUT="$ROOT_DIR/results/plots/fig9.png"
TMP_CSV="$ROOT_DIR/results/csv/.fig9_dma_tmp.csv"
WORKLOAD_DIR="$ROOT_DIR/IMPICA/workloads/dma_benchmark"

mkdir -p "$ROOT_DIR/results/csv" "$ROOT_DIR/results/plots"

echo "[INFO] Building dma_benchmark workload generator"
if ! make -C "$WORKLOAD_DIR" clean; then
  fail_gate "GATE 6" "Failed to clean dma_benchmark" "$LOG_FILE"
  exit 1
fi
if ! make -C "$WORKLOAD_DIR"; then
  fail_gate "GATE 6" "Failed to build dma_benchmark" "$LOG_FILE"
  exit 1
fi

echo "[INFO] Generating Fig.9 DMA CSV ($MODE)"
if ! "$WORKLOAD_DIR/dma_benchmark" > "$TMP_CSV"; then
  fail_gate "GATE 6" "dma_benchmark execution failed" "$LOG_FILE"
  exit 1
fi

if [[ "$MODE" == "quick" ]]; then
  awk -F, 'NR==1 || ($2+0<=2048 && ($1=="seq_read" || $1=="seq_write"))' "$TMP_CSV" > "$CSV_OUT"
else
  mv "$TMP_CSV" "$CSV_OUT"
fi
rm -f "$TMP_CSV"

if ! python3 "$ROOT_DIR/scripts/plot_fig9.py" \
  --input "$CSV_OUT" \
  --out "$PLOT_OUT"; then
  fail_gate "GATE 6" "plot_fig9.py failed" "$LOG_FILE"
  exit 1
fi

python3 - "$CSV_OUT" <<'PY'
import csv
import sys
rows = list(csv.DictReader(open(sys.argv[1], "r", newline="")))
if not rows:
    raise SystemExit("empty fig9 CSV")
overheads = []
peak_base = 0.0
peak_sepim = 0.0
for r in rows:
    base_lat = float(r["baseline_latency_ns"])
    sep_lat = float(r["sepim_latency_ns"])
    overheads.append((sep_lat - base_lat) * 100.0 / base_lat)
    peak_base = max(peak_base, float(r["baseline_gbps"]))
    peak_sepim = max(peak_sepim, float(r["sepim_gbps"]))
avg_overhead = sum(overheads) / len(overheads)
print("[INFO] Fig9 summary: avg_overhead=%.2f%% peak_baseline=%.3fGB/s peak_sepim=%.3fGB/s" %
      (avg_overhead, peak_base, peak_sepim))
PY

mark_gate_pass "GATE6" "Fig.9 CSV/plot generated in $MODE mode"
echo "[PASS] run_gate6_dma.sh completed"
