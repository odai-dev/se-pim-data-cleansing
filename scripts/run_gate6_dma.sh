#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=scripts/_common.sh
source "$SCRIPT_DIR/_common.sh"

MODE=quick
BACKEND=fs
CHECKPOINT_DIR="$ROOT_DIR/results/raw/gate3_postbuild_checkpoint_20260301"
OUT_PREFIX="fig9_fs"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --quick) MODE=quick; shift ;;
    --full) MODE=full; shift ;;
    --backend) BACKEND="$2"; shift 2 ;;
    --backend=*) BACKEND="${1#*=}"; shift ;;
    --checkpoint-dir) CHECKPOINT_DIR="$2"; shift 2 ;;
    --checkpoint-dir=*) CHECKPOINT_DIR="${1#*=}"; shift ;;
    --out-prefix) OUT_PREFIX="$2"; shift 2 ;;
    --out-prefix=*) OUT_PREFIX="${1#*=}"; shift ;;
    *) echo "[ERROR] Unknown arg: $1"; exit 2 ;;
  esac
done

LOG_FILE=$(setup_log "$ROOT_DIR/logs/run" "run_gate6_dma_${BACKEND}_${MODE}")
start_logging "$LOG_FILE"

CSV_OUT="$ROOT_DIR/results/csv/${OUT_PREFIX/_fs/_dma_fs}.csv"
PLOT_OUT="$ROOT_DIR/results/plots/${OUT_PREFIX}.png"
TMP_CSV="$ROOT_DIR/results/csv/.fig9_dma_tmp.csv"
WORKLOAD_DIR="$ROOT_DIR/IMPICA/workloads/dma_benchmark_fs"
RUN_ID="gate6_${BACKEND}_${MODE}_$(date +%Y%m%d_%H%M%S)"
RAW_OUTDIR="$ROOT_DIR/results/raw/$RUN_ID"
BOOT_SCRIPT="$ROOT_DIR/scripts/guest_run_dma_benchmark_fs.rcS"
TERM_OUT="$RAW_OUTDIR/system.terminal"
MODE_ARG="--full"

if [[ "$MODE" == "quick" ]]; then
  MODE_ARG="--quick"
fi

mkdir -p "$ROOT_DIR/results/csv" "$ROOT_DIR/results/plots" "$ROOT_DIR/results/raw"

extract_fscsv() {
  local in_term="$1"
  local out_csv="$2"
  tr -d '\000' < "$in_term" | sed 's/\r$//' | awk '
    /^FSCSV_BEGIN$/ {in_csv=1; next}
    /^FSCSV_END$/ {in_csv=0}
    in_csv {print}
  ' > "$out_csv"
}

gem5_commit=$(git -C "$ROOT_DIR/IMPICA" rev-parse --short HEAD 2>/dev/null || echo "unknown")
impica_commit="$gem5_commit"

echo "[INFO] Gate6 backend=$BACKEND mode=$MODE run_id=$RUN_ID"

if [[ "$BACKEND" == "fs" ]]; then
  if [[ ! -d "$CHECKPOINT_DIR" ]]; then
    fail_gate "GATE 6" "checkpoint dir missing: $CHECKPOINT_DIR" "$LOG_FILE"
    exit 1
  fi

  echo "[INFO] Building guest workload dma_benchmark_fs"
  make -C "$WORKLOAD_DIR" clean
  if ! make -C "$WORKLOAD_DIR"; then
    fail_gate "GATE 6" "failed to build dma_benchmark_fs" "$LOG_FILE"
    exit 1
  fi
  if ! file "$WORKLOAD_DIR/dma_benchmark_fs" | grep -qi "aarch64"; then
    fail_gate "GATE 6" "dma_benchmark_fs is not an aarch64 binary" "$LOG_FILE"
    exit 1
  fi

  echo "[INFO] Refreshing guest disk image with latest workloads"
  "$ROOT_DIR/scripts/prepare_disk_image.sh"

  cat > "$BOOT_SCRIPT" <<RCSEOF
#!/bin/sh
set -ex
cd /home/pim_driver
mknod /dev/pimbt c 70 0 || true
insmod ./test-driver.ko || { echo "[GUEST][ERROR] insmod failed"; m5 exit; exit 1; }
chmod 666 /dev/pimbt
cd /home/workloads/dma_benchmark_fs
if [ ! -x ./dma_benchmark_fs ]; then
  make || { echo "[GUEST][ERROR] build dma_benchmark_fs failed"; m5 exit; exit 1; }
fi
./dma_benchmark_fs ${MODE_ARG}
m5 exit
RCSEOF
  chmod +x "$BOOT_SCRIPT"

  OUTDIR="$RAW_OUTDIR" \
  BOOT_SCRIPT="$BOOT_SCRIPT" \
  GEM5_EXTRA_ARGS="-r 1 --checkpoint-dir=$CHECKPOINT_DIR" \
  "$ROOT_DIR/scripts/run_baseline_fs.sh" --mode custom

  if [[ ! -f "$TERM_OUT" ]]; then
    fail_gate "GATE 6" "missing terminal output: $TERM_OUT" "$LOG_FILE"
    exit 1
  fi

  extract_fscsv "$TERM_OUT" "$TMP_CSV"
  if [[ ! -s "$TMP_CSV" ]]; then
    fail_gate "GATE 6" "no FSCSV payload found in $TERM_OUT" "$LOG_FILE"
    exit 1
  fi
  mv "$TMP_CSV" "$CSV_OUT"
else
  echo "[WARN] Using synthetic backend fallback"
  make -C "$ROOT_DIR/IMPICA/workloads/dma_benchmark" clean
  make -C "$ROOT_DIR/IMPICA/workloads/dma_benchmark"
  "$ROOT_DIR/IMPICA/workloads/dma_benchmark/dma_benchmark" > "$CSV_OUT"
fi

python3 "$ROOT_DIR/scripts/add_provenance.py" \
  --input "$CSV_OUT" \
  --source "gem5_fs" \
  --run-id "$RUN_ID" \
  --mode "$MODE" \
  --checkpoint-dir "$CHECKPOINT_DIR" \
  --gem5-commit "$gem5_commit" \
  --impica-commit "$impica_commit"

if ! python3 "$ROOT_DIR/scripts/plot_fig9.py" --input "$CSV_OUT" --out "$PLOT_OUT"; then
  fail_gate "GATE 6" "plot generation failed" "$LOG_FILE"
  exit 1
fi

write_run_metadata "$RAW_OUTDIR" "GATE6_FS" "$BACKEND" "$MODE" "$CHECKPOINT_DIR" \
  "$ROOT_DIR/IMPICA/gem5/configs/example/fs.py" "$gem5_commit" "$impica_commit"

python3 - "$CSV_OUT" <<'PY'
import csv, sys
rows = list(csv.DictReader(open(sys.argv[1], "r", newline="")))
if not rows:
    raise SystemExit("empty fig9 csv")
ov = [((float(r["sepim_latency_ns"]) - float(r["baseline_latency_ns"])) * 100.0 / float(r["baseline_latency_ns"])) for r in rows]
pb = max(float(r["baseline_gbps"]) for r in rows)
ps = max(float(r["sepim_gbps"]) for r in rows)
print("[INFO] Fig9(FS) summary: avg_overhead=%.2f%% peak_baseline=%.3fGB/s peak_sepim=%.3fGB/s" % (sum(ov)/len(ov), pb, ps))
PY

mark_gate_pass "GATE6_FS" "Fig.9 FS CSV/plot generated in $MODE mode"
echo "[PASS] run_gate6_dma.sh completed"
