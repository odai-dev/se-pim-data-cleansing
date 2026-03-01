#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=scripts/_common.sh
source "$SCRIPT_DIR/_common.sh"
ORIG_ARGS=("$@")
IMAGE_NAME=${IMAGE_NAME:-sepim-impica:ubuntu18}

MODE=quick
CHECKPOINT_DIR="$ROOT_DIR/results/raw/gate3_postbuild_checkpoint_20260301"
CORRUPTION=0.10
SEED=7
DATASET_MB=512
PIM_CORES=8
BLOCK_SIZE=4096
POINTS=131072
DIMS=8

while [[ $# -gt 0 ]]; do
  case "$1" in
    --quick) MODE=quick; shift ;;
    --full) MODE=full; shift ;;
    --checkpoint-dir) CHECKPOINT_DIR="$2"; shift 2 ;;
    --checkpoint-dir=*) CHECKPOINT_DIR="${1#*=}"; shift ;;
    --corruption|--dirty-frac) CORRUPTION="$2"; shift 2 ;;
    --corruption=*|--dirty-frac=*) CORRUPTION="${1#*=}"; shift ;;
    --seed) SEED="$2"; shift 2 ;;
    --seed=*) SEED="${1#*=}"; shift ;;
    --dataset-mb) DATASET_MB="$2"; shift 2 ;;
    --dataset-mb=*) DATASET_MB="${1#*=}"; shift ;;
    --pim-cores) PIM_CORES="$2"; shift 2 ;;
    --pim-cores=*) PIM_CORES="${1#*=}"; shift ;;
    --block-size|--block_size) BLOCK_SIZE="$2"; shift 2 ;;
    --block-size=*|--block_size=*) BLOCK_SIZE="${1#*=}"; shift ;;
    --points) POINTS="$2"; shift 2 ;;
    --points=*) POINTS="${1#*=}"; shift ;;
    --dims) DIMS="$2"; shift 2 ;;
    --dims=*) DIMS="${1#*=}"; shift ;;
    *) echo "[ERROR] Unknown arg: $1"; exit 2 ;;
  esac
done

if ! command -v aarch64-linux-gnu-gcc >/dev/null 2>&1; then
  if [[ "${SEPIM_IN_CONTAINER:-0}" == "1" ]]; then
    echo "[ERROR] aarch64-linux-gnu-gcc is missing inside container image: $IMAGE_NAME"
    exit 1
  fi
  if ! command -v docker >/dev/null 2>&1; then
    echo "[ERROR] aarch64-linux-gnu-gcc not found on host and docker is unavailable."
    echo "[HINT] Install cross toolchain: sudo apt-get install gcc-aarch64-linux-gnu"
    exit 1
  fi
  if ! docker image inspect "$IMAGE_NAME" >/dev/null 2>&1; then
    echo "[ERROR] Docker image not found: $IMAGE_NAME"
    echo "[HINT] Build it first: tools/docker/build_image.sh"
    exit 1
  fi
  echo "[WARN] aarch64-linux-gnu-gcc not found on host; re-running inside Docker image $IMAGE_NAME"
  quoted_args=$(printf '%q ' "${ORIG_ARGS[@]}")
  exec docker run --rm --privileged \
    -v "$ROOT_DIR:/workspace" \
    -w /workspace \
    -e SEPIM_IN_CONTAINER=1 \
    -e IMAGE_NAME="$IMAGE_NAME" \
    "$IMAGE_NAME" \
    /bin/bash -lc "set -euo pipefail; scripts/$(basename "$0") ${quoted_args}"
fi

RUN_ID="cleaning_pim_${MODE}_$(date +%Y%m%d_%H%M%S)"
RAW_OUT="$ROOT_DIR/results/raw/$RUN_ID"
LOG_FILE=$(setup_log "$ROOT_DIR/logs/run" "run_kmeans_cleaning_pim_${MODE}")
CSV_OUT="$ROOT_DIR/results/csv/cleaning_pim.csv"
PLOT_OUT="$ROOT_DIR/results/plots/cleaning_pim.png"
STATS_OUT="$ROOT_DIR/results/raw/${RUN_ID}.stats"
BOOT_SCRIPT="$ROOT_DIR/scripts/guest_run_kmeans_cleaning_pim.rcS"
TERM_OUT="$RAW_OUT/system.terminal"
MODE_ARG=""

if [[ "$MODE" == "quick" ]]; then
  MODE_ARG="--quick"
fi

start_logging "$LOG_FILE"
mkdir -p "$ROOT_DIR/results/raw" "$ROOT_DIR/results/csv" "$ROOT_DIR/results/plots" "$RAW_OUT"
BOOT_SCRIPT="$RAW_OUT/guest_run_kmeans_cleaning_pim.rcS"

echo "[INFO] Cleaning/PIM run_id=$RUN_ID mode=$MODE"

if [[ ! -d "$CHECKPOINT_DIR" ]]; then
  fail_gate "CLEANING_PIM" "checkpoint dir missing: $CHECKPOINT_DIR" "$LOG_FILE"
  exit 1
fi

"$ROOT_DIR/scripts/make_dirty_dataset.sh" \
  --points "$POINTS" \
  --dims "$DIMS" \
  --dirty-frac "$CORRUPTION" \
  --seed "$SEED"

make -C "$ROOT_DIR/IMPICA/workloads/kmeans_sepim_fs" clean
make -C "$ROOT_DIR/IMPICA/workloads/kmeans_sepim_fs"
if ! file "$ROOT_DIR/IMPICA/workloads/kmeans_sepim_fs/kmeans_sepim_fs" | grep -qi 'aarch64'; then
  fail_gate "CLEANING_PIM" "kmeans_sepim_fs is not an aarch64 binary" "$LOG_FILE"
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
./kmeans_sepim_fs ${MODE_ARG} --cleaning=off --dataset=./data/kmeans_clean.bin --dataset-mb=${DATASET_MB} --pim-cores=${PIM_CORES} --corruption=0 --seed=${SEED} --block-size=${BLOCK_SIZE}
./kmeans_sepim_fs ${MODE_ARG} --cleaning=off --dataset=./data/kmeans_dirty_10pct.bin --dataset-mb=${DATASET_MB} --pim-cores=${PIM_CORES} --corruption=${CORRUPTION} --seed=${SEED} --block-size=${BLOCK_SIZE}
./kmeans_sepim_fs ${MODE_ARG} --cleaning=pim --dataset=./data/kmeans_dirty_10pct.bin --dataset-mb=${DATASET_MB} --pim-cores=${PIM_CORES} --corruption=${CORRUPTION} --seed=${SEED} --block-size=${BLOCK_SIZE}
m5 exit
RCSEOF
chmod +x "$BOOT_SCRIPT"

OUTDIR="$RAW_OUT" \
BOOT_SCRIPT="$BOOT_SCRIPT" \
GEM5_EXTRA_ARGS="-r 1 --checkpoint-dir=$CHECKPOINT_DIR" \
"$ROOT_DIR/scripts/run_baseline_fs.sh" --mode custom

if [[ ! -f "$TERM_OUT" ]]; then
  fail_gate "CLEANING_PIM" "missing terminal output: $TERM_OUT" "$LOG_FILE"
  exit 1
fi

python3 - "$TERM_OUT" "$CSV_OUT" <<'PY'
import csv, io, sys
term, out_csv = sys.argv[1], sys.argv[2]
text = open(term, 'rb').read().replace(b'\x00', b'').decode('utf-8', 'ignore').replace('\r', '')
rows = []
collect = False
block = []
for ln in text.splitlines():
    if ln.strip() == 'FSCSV_BEGIN':
        collect = True
        block = []
        continue
    if ln.strip() == 'FSCSV_END':
        collect = False
        if block:
            rdr = csv.DictReader(io.StringIO('\n'.join(block) + '\n'))
            rows.extend(list(rdr))
        block = []
        continue
    if collect:
        block.append(ln)
if not rows:
    raise SystemExit('no FSCSV rows found')
with open(out_csv, 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    w.writeheader(); w.writerows(rows)
print('[INFO] extracted rows=%d -> %s' % (len(rows), out_csv))
PY

gem5_commit=$(git -C "$ROOT_DIR/IMPICA" rev-parse --short HEAD 2>/dev/null || echo unknown)
python3 "$ROOT_DIR/scripts/add_provenance.py" \
  --input "$CSV_OUT" --source gem5_fs --run-id "$RUN_ID" --mode "$MODE" \
  --checkpoint-dir "$CHECKPOINT_DIR" --gem5-commit "$gem5_commit" --impica-commit "$gem5_commit"

python3 "$ROOT_DIR/scripts/plot_cleaning.py" --input "$CSV_OUT" --out "$PLOT_OUT"

python3 - "$CSV_OUT" "$STATS_OUT" <<'PY'
import csv, sys
rows = list(csv.DictReader(open(sys.argv[1], 'r', newline='')))
out = []
out.append('rows=%d' % len(rows))
for r in rows:
    out.append('mode=%s total_sec=%s scan_sec=%s clean_sec=%s kmeans_sec=%s dirty_found=%s dirty_remaining=%s' % (
        r.get('cleaning_mode'), r.get('total_sec'), r.get('scan_sec'), r.get('clean_sec'), r.get('kmeans_sec'),
        r.get('dirty_found'), r.get('dirty_remaining')))
open(sys.argv[2], 'w', encoding='utf-8').write('\n'.join(out) + '\n')
print('[INFO] wrote stats:', sys.argv[2])
PY

write_run_metadata "$RAW_OUT" "CLEANING_PIM" "fs" "$MODE" "$CHECKPOINT_DIR" \
  "$ROOT_DIR/IMPICA/gem5/configs/example/fs.py" "$gem5_commit" "$gem5_commit"

echo "[PASS] run_kmeans_cleaning_pim.sh completed"
