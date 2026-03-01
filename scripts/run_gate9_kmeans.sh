#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=scripts/_common.sh
source "$SCRIPT_DIR/_common.sh"

MODE=quick
BACKEND=fs
CHECKPOINT_DIR="$ROOT_DIR/results/raw/gate3_postbuild_checkpoint_20260301"
OUT_PREFIX="fig11_fs"

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

LOG_FILE=$(setup_log "$ROOT_DIR/logs/run" "run_gate9_kmeans_${BACKEND}_${MODE}")
start_logging "$LOG_FILE"

CSV_OUT="$ROOT_DIR/results/csv/${OUT_PREFIX/_fs/_kmeans_scaling_fs}.csv"
PLOT_OUT="$ROOT_DIR/results/plots/${OUT_PREFIX}.png"
TMP_CSV="$ROOT_DIR/results/csv/.fig11_tmp.csv"
WORKLOAD_DIR="$ROOT_DIR/IMPICA/workloads/kmeans_sepim_fs"
RUN_ID="gate9_${BACKEND}_${MODE}_$(date +%Y%m%d_%H%M%S)"
RAW_OUTDIR="$ROOT_DIR/results/raw/$RUN_ID"
BOOT_SCRIPT="$ROOT_DIR/scripts/guest_run_kmeans_sepim_fs.rcS"
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

echo "[INFO] Gate9 backend=$BACKEND mode=$MODE run_id=$RUN_ID"

if [[ "$BACKEND" == "fs" ]]; then
  if [[ ! -d "$CHECKPOINT_DIR" ]]; then
    fail_gate "GATE 9" "checkpoint dir missing: $CHECKPOINT_DIR" "$LOG_FILE"
    exit 1
  fi

  make -C "$WORKLOAD_DIR" clean
  if ! make -C "$WORKLOAD_DIR"; then
    fail_gate "GATE 9" "failed to build kmeans_sepim_fs" "$LOG_FILE"
    exit 1
  fi
  if ! file "$WORKLOAD_DIR/kmeans_sepim_fs" | grep -qi "aarch64"; then
    fail_gate "GATE 9" "kmeans_sepim_fs is not an aarch64 binary" "$LOG_FILE"
    exit 1
  fi
  "$ROOT_DIR/scripts/prepare_disk_image.sh"

  cat > "$BOOT_SCRIPT" <<RCSEOF
#!/bin/sh
set -ex
cd /home/pim_driver
mknod /dev/pimbt c 70 0 || true
insmod ./test-driver.ko || true
chmod 666 /dev/pimbt || true
cd /home/workloads/kmeans_sepim_fs
if [ ! -x ./kmeans_sepim_fs ]; then
  make || { echo "[GUEST][ERROR] build kmeans_sepim_fs failed"; m5 exit; exit 1; }
fi
./kmeans_sepim_fs ${MODE_ARG}
m5 exit
RCSEOF
  chmod +x "$BOOT_SCRIPT"

  OUTDIR="$RAW_OUTDIR" \
  BOOT_SCRIPT="$BOOT_SCRIPT" \
  GEM5_EXTRA_ARGS="-r 1 --checkpoint-dir=$CHECKPOINT_DIR" \
  "$ROOT_DIR/scripts/run_baseline_fs.sh" --mode custom

  if [[ ! -f "$TERM_OUT" ]]; then
    fail_gate "GATE 9" "missing terminal output: $TERM_OUT" "$LOG_FILE"
    exit 1
  fi
  extract_fscsv "$TERM_OUT" "$TMP_CSV"
  if [[ ! -s "$TMP_CSV" ]]; then
    fail_gate "GATE 9" "no FSCSV payload found in $TERM_OUT" "$LOG_FILE"
    exit 1
  fi
  mv "$TMP_CSV" "$CSV_OUT"
else
  echo "[WARN] Using synthetic backend fallback"
  make -C "$ROOT_DIR/IMPICA/workloads/kmeans_sepim" clean
  make -C "$ROOT_DIR/IMPICA/workloads/kmeans_sepim"
  "$ROOT_DIR/IMPICA/workloads/kmeans_sepim/kmeans_sepim" > "$CSV_OUT"
fi

python3 "$ROOT_DIR/scripts/add_provenance.py" \
  --input "$CSV_OUT" \
  --source "gem5_fs" \
  --run-id "$RUN_ID" \
  --mode "$MODE" \
  --checkpoint-dir "$CHECKPOINT_DIR" \
  --gem5-commit "$gem5_commit" \
  --impica-commit "$impica_commit"

if ! python3 "$ROOT_DIR/scripts/plot_fig11.py" --input "$CSV_OUT" --out "$PLOT_OUT"; then
  fail_gate "GATE 9" "plot generation failed" "$LOG_FILE"
  exit 1
fi

write_run_metadata "$RAW_OUTDIR" "GATE9_FS" "$BACKEND" "$MODE" "$CHECKPOINT_DIR" \
  "$ROOT_DIR/IMPICA/gem5/configs/example/fs.py" "$gem5_commit" "$impica_commit"

python3 - "$CSV_OUT" <<'PY'
import csv, sys
rows = list(csv.DictReader(open(sys.argv[1], "r", newline="")))
for r in rows:
    if int(float(r["dataset_mb"])) == 512 and int(float(r["pim_cores"])) == 8:
        print("[INFO] Fig11(FS) 512MB/8core sepim=%.3fs speedup=%.3fx overhead=%.3f%%" %
              (float(r["sepim_sec"]), float(r["speedup_vs_cpu"]), float(r["overhead_pct"])))
        break
PY

mark_gate_pass "GATE9_FS" "Fig.11 FS CSV/plot generated in $MODE mode"
echo "[PASS] run_gate9_kmeans.sh completed"
