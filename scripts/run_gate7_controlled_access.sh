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

LOG_FILE=$(setup_log "$ROOT_DIR/logs/run" "run_gate7_controlled_${MODE}")
start_logging "$LOG_FILE"

CSV_OUT="$ROOT_DIR/results/csv/fig10_controlled_access.csv"
PLOT_OUT="$ROOT_DIR/results/plots/fig10.png"
TMP_CSV="$ROOT_DIR/results/csv/.fig10_tmp.csv"
WORKLOAD_DIR="$ROOT_DIR/IMPICA/workloads/controlled_access_bench"

mkdir -p "$ROOT_DIR/results/csv" "$ROOT_DIR/results/plots"

echo "[INFO] Building controlled_access_bench workload generator"
if ! make -C "$WORKLOAD_DIR"; then
  fail_gate "GATE 7" "Failed to build controlled_access_bench" "$LOG_FILE"
  exit 1
fi

echo "[INFO] Generating Fig.10 controlled access CSV ($MODE)"
"$WORKLOAD_DIR/controlled_access_bench" > "$TMP_CSV"
if [[ "$MODE" == "quick" ]]; then
  awk -F, 'NR==1 || $1+0<=32' "$TMP_CSV" > "$CSV_OUT"
else
  mv "$TMP_CSV" "$CSV_OUT"
fi
rm -f "$TMP_CSV"

python3 "$ROOT_DIR/scripts/plot_fig10.py" \
  --input "$CSV_OUT" \
  --out "$PLOT_OUT"

python3 - "$CSV_OUT" <<'PY'
import csv
import sys
rows = list(csv.DictReader(open(sys.argv[1], "r", newline="")))
for r in rows:
    if int(float(r["block_kb"])) == 64:
        print("[INFO] Fig10 summary: controlled@64KB=%.1f MB/s" % float(r["controlled_mbps"]))
    if int(float(r["block_kb"])) == 128:
        print("[INFO] Fig10 summary: controlled@128KB=%.1f MB/s" % float(r["controlled_mbps"]))
PY

mark_gate_pass "GATE7" "Fig.10 CSV/plot generated in $MODE mode"
echo "[PASS] run_gate7_controlled_access.sh completed"
