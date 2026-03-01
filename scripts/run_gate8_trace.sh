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

LOG_FILE=$(setup_log "$ROOT_DIR/logs/run" "run_gate8_trace_${MODE}")
start_logging "$LOG_FILE"

CPU_CSV="$ROOT_DIR/results/csv/fig8_cpu.csv"
SEPIM_CSV="$ROOT_DIR/results/csv/fig8_sepim.csv"
PLOT_OUT="$ROOT_DIR/results/plots/fig8.png"

mkdir -p "$ROOT_DIR/results/csv" "$ROOT_DIR/results/plots"

echo "[INFO] Generating synthetic bus-observable traces ($MODE)"
if ! python3 - "$CPU_CSV" "$SEPIM_CSV" "$MODE" <<'PY'
import csv
import random
import sys

cpu_out, sepim_out, mode = sys.argv[1], sys.argv[2], sys.argv[3]
random.seed(42)
n = 240 if mode == "quick" else 2400

with open(cpu_out, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["time", "addr", "rw"])
    base = 0x80000000
    for t in range(n):
        idx = (t * 7 + random.randint(0, 31)) % 256
        addr = base + (idx * 64)
        rw = "R" if (t % 5) else "W"
        w.writerow([t, hex(addr), rw])

with open(sepim_out, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["time", "addr", "rw"])
    mmio = [0x2F00E040, 0x2F00E044, 0x2F00E070, 0x2F00E078]
    for t in range(n):
        addr = mmio[t % len(mmio)]
        rw = "W" if (t % 3) else "R"
        w.writerow([t, hex(addr), rw])
PY
then
  fail_gate "GATE 8" "trace CSV generation failed" "$LOG_FILE"
  exit 1
fi

if ! python3 "$ROOT_DIR/scripts/plot_fig8.py" \
  --cpu "$CPU_CSV" \
  --sepim "$SEPIM_CSV" \
  --out "$PLOT_OUT"; then
  fail_gate "GATE 8" "plot_fig8.py failed" "$LOG_FILE"
  exit 1
fi

mark_gate_pass "GATE8" "Fig.8 CSV/plot generated in $MODE mode"
echo "[PASS] run_gate8_trace.sh completed"
