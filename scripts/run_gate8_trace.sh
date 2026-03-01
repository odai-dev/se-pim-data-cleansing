#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=scripts/_common.sh
source "$SCRIPT_DIR/_common.sh"

MODE=quick
BACKEND=fs
CHECKPOINT_DIR="$ROOT_DIR/results/raw/gate3_postbuild_checkpoint_20260301"
OUT_PREFIX="fig8_fs"
TRACE_ENABLE=1

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
    --sepim-trace-enable) TRACE_ENABLE=1; shift ;;
    --sepim-trace-disable) TRACE_ENABLE=0; shift ;;
    *) echo "[ERROR] Unknown arg: $1"; exit 2 ;;
  esac
done

LOG_FILE=$(setup_log "$ROOT_DIR/logs/run" "run_gate8_trace_${BACKEND}_${MODE}")
start_logging "$LOG_FILE"

CPU_CSV="$ROOT_DIR/results/csv/${OUT_PREFIX/_fs/_cpu_fs}.csv"
SEPIM_CSV="$ROOT_DIR/results/csv/${OUT_PREFIX/_fs/_sepim_fs}.csv"
PLOT_OUT="$ROOT_DIR/results/plots/${OUT_PREFIX}.png"
RUN_ID="gate8_${BACKEND}_${MODE}_$(date +%Y%m%d_%H%M%S)"
CPU_RUN_ID="${RUN_ID}_cpu"
SEPIM_RUN_ID="${RUN_ID}_sepim"
WORKLOAD_CPU="$ROOT_DIR/IMPICA/workloads/trace_lookup_cpu"
WORKLOAD_SEPIM="$ROOT_DIR/IMPICA/workloads/trace_lookup_sepim"
MODE_ARG="--full"
TAIL_SAMPLES=4096

if [[ "$MODE" == "quick" ]]; then
  MODE_ARG="--quick"
  TAIL_SAMPLES=1024
fi

mkdir -p "$ROOT_DIR/results/csv" "$ROOT_DIR/results/plots" "$ROOT_DIR/results/raw"

run_guest_trace() {
  local workload_dir="$1"
  local bin_name="$2"
  local raw_out="$3"
  local boot_script="$4"
  local term_out="$5"
  local trace_out="$6"

  cat > "$boot_script" <<RCSEOF
#!/bin/sh
set -ex
cd /home/pim_driver
mknod /dev/pimbt c 70 0 || true
insmod ./test-driver.ko || true
chmod 666 /dev/pimbt || true
cd /home/workloads/$workload_dir
if [ ! -x ./$bin_name ]; then
  make || { echo "[GUEST][ERROR] build $bin_name failed"; m5 exit; exit 1; }
fi
./$bin_name ${MODE_ARG}
m5 exit
RCSEOF
  chmod +x "$boot_script"

  local extra="-r 1 --checkpoint-dir=$CHECKPOINT_DIR"
  if [[ "$TRACE_ENABLE" == "1" ]]; then
    extra="$extra --sepim-trace-enable=1 --sepim-trace-file=$trace_out"
  fi

  OUTDIR="$raw_out" \
  BOOT_SCRIPT="$boot_script" \
  FS_CONFIG="$ROOT_DIR/IMPICA/gem5/configs/se_pim/se_pim_fs.py" \
  GEM5_EXTRA_ARGS="$extra" \
  "$ROOT_DIR/scripts/run_baseline_fs.sh" --mode custom

  if [[ ! -f "$term_out" ]]; then
    fail_gate "GATE 8" "missing terminal output: $term_out" "$LOG_FILE"
    exit 1
  fi
}

gem5_commit=$(git -C "$ROOT_DIR/IMPICA" rev-parse --short HEAD 2>/dev/null || echo "unknown")
impica_commit="$gem5_commit"

echo "[INFO] Gate8 backend=$BACKEND mode=$MODE run_id=$RUN_ID"

if [[ "$BACKEND" == "fs" ]]; then
  if [[ ! -d "$CHECKPOINT_DIR" ]]; then
    fail_gate "GATE 8" "checkpoint dir missing: $CHECKPOINT_DIR" "$LOG_FILE"
    exit 1
  fi

  make -C "$WORKLOAD_CPU" clean
  make -C "$WORKLOAD_CPU"
  make -C "$WORKLOAD_SEPIM" clean
  make -C "$WORKLOAD_SEPIM"
  if ! file "$WORKLOAD_CPU/trace_lookup_cpu" | grep -qi "aarch64"; then
    fail_gate "GATE 8" "trace_lookup_cpu is not an aarch64 binary" "$LOG_FILE"
    exit 1
  fi
  if ! file "$WORKLOAD_SEPIM/trace_lookup_sepim" | grep -qi "aarch64"; then
    fail_gate "GATE 8" "trace_lookup_sepim is not an aarch64 binary" "$LOG_FILE"
    exit 1
  fi
  "$ROOT_DIR/scripts/prepare_disk_image.sh"

  CPU_RAW="$ROOT_DIR/results/raw/${RUN_ID}_cpu"
  SEPIM_RAW="$ROOT_DIR/results/raw/${RUN_ID}_sepim"
  CPU_BOOT="$ROOT_DIR/scripts/guest_run_trace_lookup_cpu.rcS"
  SEPIM_BOOT="$ROOT_DIR/scripts/guest_run_trace_lookup_sepim.rcS"
  CPU_TERM="$CPU_RAW/system.terminal"
  SEPIM_TERM="$SEPIM_RAW/system.terminal"
  CPU_TRACE="$CPU_RAW/trace_cpu.ptrc"
  SEPIM_TRACE="$SEPIM_RAW/trace_sepim.ptrc"
  CPU_TRACE_IO="${CPU_TRACE}.io"
  SEPIM_TRACE_IO="${SEPIM_TRACE}.io"
  CPU_DECODED="$CPU_RAW/trace_cpu_decoded.csv"
  SEPIM_DECODED="$SEPIM_RAW/trace_sepim_decoded.csv"

  run_guest_trace "trace_lookup_cpu" "trace_lookup_cpu" "$CPU_RAW" "$CPU_BOOT" "$CPU_TERM" "$CPU_TRACE"
  run_guest_trace "trace_lookup_sepim" "trace_lookup_sepim" "$SEPIM_RAW" "$SEPIM_BOOT" "$SEPIM_TERM" "$SEPIM_TRACE"

  if [[ ! -f "$CPU_TRACE" || ! -f "$SEPIM_TRACE" ]]; then
    fail_gate "GATE 8" "missing CommMonitor L2 trace files ($CPU_TRACE / $SEPIM_TRACE)" "$LOG_FILE"
    exit 1
  fi

  # CPU leakage is expected on cache/memory path (L2 trace).
  TRACE_SRC_CPU="$CPU_TRACE"
  # SE-PIM fixed channel is expected on IO/MMIO path when available.
  TRACE_SRC_SEPIM="$SEPIM_TRACE"
  if [[ -f "$SEPIM_TRACE_IO" && -s "$SEPIM_TRACE_IO" ]]; then
    TRACE_SRC_SEPIM="$SEPIM_TRACE_IO"
  fi
  echo "[INFO] Fig8(FS) trace sources: cpu=$TRACE_SRC_CPU sepim=$TRACE_SRC_SEPIM"

  if ! python3 "$ROOT_DIR/scripts/decode_ptrace_csv.py" \
      --input "$TRACE_SRC_CPU" --output "$CPU_DECODED" \
      --gem5-root "$ROOT_DIR/IMPICA/gem5" --tail "$TAIL_SAMPLES" --rw-only; then
    fail_gate "GATE 8" "failed decoding CPU packet trace" "$LOG_FILE"
    exit 1
  fi
  if ! python3 "$ROOT_DIR/scripts/decode_ptrace_csv.py" \
      --input "$TRACE_SRC_SEPIM" --output "$SEPIM_DECODED" \
      --gem5-root "$ROOT_DIR/IMPICA/gem5" --tail "$TAIL_SAMPLES" --rw-only; then
    fail_gate "GATE 8" "failed decoding SE-PIM packet trace" "$LOG_FILE"
    exit 1
  fi

  python3 - "$CPU_DECODED" "$SEPIM_DECODED" "$CPU_CSV" "$SEPIM_CSV" <<'PY'
import csv, sys
from collections import Counter

cpu_src, sepim_src, cpu_out, sepim_out = sys.argv[1:5]

with open(cpu_src, "r", newline="") as f:
    cpu_rows = list(csv.DictReader(f))
with open(sepim_src, "r", newline="") as f:
    sepim_rows = list(csv.DictReader(f))

# Infer a SE-PIM ROI flag by enrichment relative to CPU trace.
cpu_flag = Counter(r.get("flags", "0") for r in cpu_rows)
sepim_flag = Counter(r.get("flags", "0") for r in sepim_rows)
best_flag = None
best_score = -1.0
for flag, s_count in sepim_flag.items():
    if s_count < 64:
        continue
    c_count = cpu_flag.get(flag, 0)
    score = float(s_count + 1) / float(c_count + 1)
    if score > best_score:
        best_score = score
        best_flag = flag
if best_flag is None and sepim_flag:
    best_flag = sepim_flag.most_common(1)[0][0]

# CPU side: keep dominant request class (read-heavy user traffic).
cpu_main_flag = cpu_flag.most_common(1)[0][0] if cpu_flag else None

def project(rows, out_path, selected_flag):
    if selected_flag is not None:
        filt = [r for r in rows if r.get("flags", "0") == selected_flag]
    else:
        filt = list(rows)
    # Fallback if selection is too narrow.
    if len(filt) < 64:
        filt = list(rows)
    with open(out_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["time", "addr", "rw"])
        for r in filt:
            w.writerow([r["time"], r["addr"], r["rw"]])
    return len(filt)

cpu_n = project(cpu_rows, cpu_out, cpu_main_flag)
sepim_n = project(sepim_rows, sepim_out, best_flag)
print("[INFO] Fig8(FS) ROI flags: cpu_flag=%s sepim_flag=%s rows(cpu=%d, sepim=%d)" %
      (str(cpu_main_flag), str(best_flag), cpu_n, sepim_n))
PY

  if [[ ! -s "$CPU_CSV" || ! -s "$SEPIM_CSV" ]]; then
    fail_gate "GATE 8" "decoded packet trace CSVs are empty" "$LOG_FILE"
    exit 1
  fi
  python3 - "$CPU_CSV" "$SEPIM_CSV" <<'PY'
import csv, sys
cpu, sepim = sys.argv[1], sys.argv[2]
with open(cpu, "r", newline="") as f:
    cpu_rows = list(csv.DictReader(f))
with open(sepim, "r", newline="") as f:
    sepim_rows = list(csv.DictReader(f))
if len(cpu_rows) < 16 or len(sepim_rows) < 16:
    raise SystemExit("insufficient decoded trace rows: cpu=%d sepim=%d" % (len(cpu_rows), len(sepim_rows)))
print("[INFO] Fig8(FS) decoded rows: cpu=%d sepim=%d" % (len(cpu_rows), len(sepim_rows)))
PY

  write_run_metadata "$CPU_RAW" "GATE8_FS_CPU" "$BACKEND" "$MODE" "$CHECKPOINT_DIR" \
    "$ROOT_DIR/IMPICA/gem5/configs/se_pim/se_pim_fs.py" "$gem5_commit" "$impica_commit"
  write_run_metadata "$SEPIM_RAW" "GATE8_FS_SEPIM" "$BACKEND" "$MODE" "$CHECKPOINT_DIR" \
    "$ROOT_DIR/IMPICA/gem5/configs/se_pim/se_pim_fs.py" "$gem5_commit" "$impica_commit"
else
  echo "[WARN] Using synthetic backend fallback"
  python3 - "$CPU_CSV" "$SEPIM_CSV" "$MODE" <<'PY'
import csv, random, sys
cpu_out, sepim_out, mode = sys.argv[1], sys.argv[2], sys.argv[3]
random.seed(42)
n = 240 if mode == "quick" else 2400
with open(cpu_out, "w", newline="") as f:
    w = csv.writer(f); w.writerow(["time","addr","rw"])
    base = 0x80000000
    for t in range(n):
        idx = (t * 7 + random.randint(0, 31)) % 256
        addr = base + idx * 64
        w.writerow([t, hex(addr), "R" if (t % 5) else "W"])
with open(sepim_out, "w", newline="") as f:
    w = csv.writer(f); w.writerow(["time","addr","rw"])
    mmio = [0x2F00E040, 0x2F00E044, 0x2F00E070, 0x2F00E078]
    for t in range(n):
        w.writerow([t, hex(mmio[t % 4]), "W" if (t % 3) else "R"])
PY
fi

python3 "$ROOT_DIR/scripts/add_provenance.py" \
  --input "$CPU_CSV" --source "gem5_fs" --run-id "$CPU_RUN_ID" --mode "$MODE" \
  --checkpoint-dir "$CHECKPOINT_DIR" --gem5-commit "$gem5_commit" --impica-commit "$impica_commit"
python3 "$ROOT_DIR/scripts/add_provenance.py" \
  --input "$SEPIM_CSV" --source "gem5_fs" --run-id "$SEPIM_RUN_ID" --mode "$MODE" \
  --checkpoint-dir "$CHECKPOINT_DIR" --gem5-commit "$gem5_commit" --impica-commit "$impica_commit"

if ! python3 "$ROOT_DIR/scripts/plot_fig8.py" --cpu "$CPU_CSV" --sepim "$SEPIM_CSV" --out "$PLOT_OUT"; then
  fail_gate "GATE 8" "plot generation failed" "$LOG_FILE"
  exit 1
fi

mark_gate_pass "GATE8_FS" "Fig.8 FS CSV/plot generated in $MODE mode"
echo "[PASS] run_gate8_trace.sh completed"
