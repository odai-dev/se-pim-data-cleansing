#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=scripts/_common.sh
source "$SCRIPT_DIR/_common.sh"

LOG_FILE=$(setup_log "$ROOT_DIR/logs/run" "run_baseline_fs")
start_logging "$LOG_FILE"

IMPICA_DIR=${IMPICA_DIR:-$ROOT_DIR/IMPICA}
GEM5_DIR=${GEM5_DIR:-$IMPICA_DIR/gem5}
GEM5_BIN=${GEM5_BIN:-$GEM5_DIR/build/ARM/gem5.opt}
FS_BUNDLE_DIR=${FS_BUNDLE_DIR:-$ROOT_DIR/third_party/gem5_fs/aarch-system-2014-10}
DISK_IMAGE=${DISK_IMAGE:-$FS_BUNDLE_DIR/disks/aarch64-ubuntu-trusty-headless.img}
KERNEL=${KERNEL:-$FS_BUNDLE_DIR/binaries/vmlinux.aarch64.20140821}
DTB=${DTB:-$FS_BUNDLE_DIR/binaries/vexpress.aarch64.20140821.dtb}
FS_CONFIG=${FS_CONFIG:-$GEM5_DIR/configs/example/fs.py}
OUTDIR=${OUTDIR:-$ROOT_DIR/results/raw/baseline_fs_boot}
CPUS=${CPUS:-4}
MEM_SIZE=${MEM_SIZE:-2048MB}

BOOT_SCRIPT=${BOOT_SCRIPT:-$ROOT_DIR/scripts/guest_boot_checkpoint.rcS}

if [[ ! -x "$GEM5_BIN" ]]; then
  fail_gate "GATE 3" "gem5 binary not found at $GEM5_BIN" "$LOG_FILE"
  exit 1
fi

if [[ ! -f "$DISK_IMAGE" || ! -f "$KERNEL" || ! -f "$DTB" ]]; then
  echo "[INFO] FS artifacts missing; attempting to fetch gem5 ARM FS bundle"
  "$SCRIPT_DIR/fetch_gem5_fs.sh"
  if [[ ! -f "$DISK_IMAGE" || ! -f "$KERNEL" || ! -f "$DTB" ]]; then
    fail_gate "GATE 3" "FS artifacts missing under $FS_BUNDLE_DIR after fetch" "$LOG_FILE"
    exit 1
  fi
fi

mkdir -p "$OUTDIR"

if [[ ! -f "$BOOT_SCRIPT" ]]; then
  cat > "$BOOT_SCRIPT" <<'RCSEOF'
#!/bin/sh
m5 checkpoint
m5 exit
RCSEOF
  chmod +x "$BOOT_SCRIPT"
fi

echo "[INFO] Running baseline full-system boot"
M5_PATH="$FS_BUNDLE_DIR" "$GEM5_BIN" \
  --outdir="$OUTDIR" \
  "$FS_CONFIG" \
  --machine-type=VExpress_EMM64 \
  -n "$CPUS" \
  --mem-size="$MEM_SIZE" \
  --disk-image="$DISK_IMAGE" \
  --dtb-file="$DTB" \
  --kernel="$KERNEL" \
  --script="$BOOT_SCRIPT"

echo "[PASS] run_baseline_fs.sh completed"
