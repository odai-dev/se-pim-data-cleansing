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
FS_BUNDLE_ROOT=${FS_BUNDLE_ROOT:-$ROOT_DIR/third_party/gem5_fs}
FS_BUNDLE_DIR=${FS_BUNDLE_DIR:-$FS_BUNDLE_ROOT/aarch-system-2014-10}
DISK_IMAGE=${DISK_IMAGE:-}
KERNEL=${KERNEL:-}
DTB=${DTB:-}
FS_CONFIG=${FS_CONFIG:-$GEM5_DIR/configs/example/fs.py}
MODE=${MODE:-checkpoint}
OUTDIR=${OUTDIR:-}
CPUS=${CPUS:-4}
MEM_SIZE=${MEM_SIZE:-2048MB}
RUNTIME_LIB_ROOT=${RUNTIME_LIB_ROOT:-$ROOT_DIR/third_party/runtime_libs/rootfs}
GEM5_EXTRA_ARGS=${GEM5_EXTRA_ARGS:-}

BOOT_SCRIPT=${BOOT_SCRIPT:-$ROOT_DIR/scripts/guest_boot_checkpoint.rcS}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --mode)
      if [[ $# -lt 2 ]]; then
        echo "[ERROR] --mode requires a value: checkpoint|hash_table|sepim_cmd_smoke|boot_probe"
        exit 2
      fi
      MODE="$2"
      shift 2
      ;;
    --mode=*)
      MODE="${1#*=}"
      shift
      ;;
    *)
      echo "[ERROR] Unknown argument: $1"
      echo "[INFO] Usage: scripts/run_baseline_fs.sh [--mode checkpoint|hash_table|sepim_cmd_smoke|boot_probe]"
      exit 2
      ;;
  esac
done

if [[ -z "$OUTDIR" ]]; then
  OUTDIR="$ROOT_DIR/results/raw/baseline_fs_${MODE}"
fi

if [[ ! -x "$GEM5_BIN" ]]; then
  fail_gate "GATE 3" "gem5 binary not found at $GEM5_BIN" "$LOG_FILE"
  exit 1
fi

if [[ -f "$RUNTIME_LIB_ROOT/usr/lib/x86_64-linux-gnu/libpython2.7.so.1.0" ]]; then
  export LD_LIBRARY_PATH="$RUNTIME_LIB_ROOT/usr/lib/x86_64-linux-gnu:${LD_LIBRARY_PATH:-}"
  export PYTHONHOME="${PYTHONHOME:-$RUNTIME_LIB_ROOT/usr}"
  export PYTHONPATH="$RUNTIME_LIB_ROOT/usr/lib/python2.7:$RUNTIME_LIB_ROOT/usr/lib/python2.7/lib-dynload:${PYTHONPATH:-}"
fi

if ldd "$GEM5_BIN" | grep -q "not found"; then
  fail_gate "GATE 3" "gem5 runtime dependencies missing; run scripts/setup_runtime_libs.sh first" "$LOG_FILE"
  exit 1
fi

resolve_bundle_dir() {
  local candidate
  for candidate in "$FS_BUNDLE_DIR" "$FS_BUNDLE_ROOT"; do
    if [[ -f "$candidate/disks/aarch64-ubuntu-trusty-headless.img" && \
          -f "$candidate/binaries/vmlinux.aarch64.20140821" && \
          -f "$candidate/binaries/vexpress.aarch64.20140821.dtb" ]]; then
      FS_BUNDLE_DIR="$candidate"
      return 0
    fi
  done
  return 1
}

if ! resolve_bundle_dir; then
  echo "[INFO] FS artifacts missing; attempting to fetch gem5 ARM FS bundle"
  "$SCRIPT_DIR/fetch_gem5_fs.sh"
  if ! resolve_bundle_dir; then
    fail_gate "GATE 3" "FS artifacts missing under $FS_BUNDLE_ROOT after fetch" "$LOG_FILE"
    exit 1
  fi
fi

if [[ -z "$DISK_IMAGE" ]]; then
  DISK_IMAGE="$FS_BUNDLE_DIR/disks/aarch64-ubuntu-trusty-headless.img"
fi
if [[ -z "$KERNEL" ]]; then
  KERNEL="$FS_BUNDLE_DIR/binaries/vmlinux.aarch64.20140821"
fi
if [[ -z "$DTB" ]]; then
  DTB="$FS_BUNDLE_DIR/binaries/vexpress.aarch64.20140821.dtb"
fi

mkdir -p "$OUTDIR"

case "$MODE" in
  checkpoint)
    BOOT_SCRIPT="$ROOT_DIR/scripts/guest_boot_checkpoint.rcS"
    cat > "$BOOT_SCRIPT" <<'RCSEOF'
#!/bin/sh
set -ex

# GEM5_CHECKPOINT_BOOTSTRAP_SENTINEL
# This bootstrap script creates a checkpoint, then dispatches to the
# host-provided readfile payload after restore.
M5=/sbin/m5
if [ ! -x "$M5" ]; then
  M5=m5
fi

# Create an initial checkpoint exactly once from a cold boot.
if [ "${RUNSCRIPT_VAR:-0}" -eq 0 ]; then
  export RUNSCRIPT_VAR=1
  "$M5" checkpoint
fi

# Read the current host-supplied script. In the checkpoint-creation run this
# will still be this bootstrap script; in restored runs it should be the target
# workload script (hash_table, sepim_cmd_smoke, etc).
"$M5" readfile > /tmp/runscript || true
chmod 755 /tmp/runscript || true

# Avoid recursive self-exec during checkpoint creation.
if grep -Fq "GEM5_CHECKPOINT_BOOTSTRAP_SENTINEL" /tmp/runscript 2>/dev/null; then
  "$M5" exit
fi

if [ -s /tmp/runscript ]; then
  exec /tmp/runscript
fi

"$M5" exit
RCSEOF
    ;;
  hash_table)
    BOOT_SCRIPT="$ROOT_DIR/scripts/guest_run_hashtable.rcS"
    cat > "$BOOT_SCRIPT" <<'RCSEOF'
#!/bin/sh
set -ex

cd /home/pim_driver
mknod /dev/pimbt c 70 0 || true
if ! insmod ./test-driver.ko; then
  echo "[GUEST][ERROR] Failed to insert /home/pim_driver/test-driver.ko"
  dmesg | tail -n 50 || true
  m5 exit
  exit 1
fi
chmod 666 /dev/pimbt

cd /home/workloads/hashtable
if [ -x ./hashtable ]; then
  echo "[GUEST][INFO] Using prebuilt /home/workloads/hashtable/hashtable"
else
  echo "[GUEST][INFO] Prebuilt hashtable missing; building in guest"
  mkdir -p obj
  if ! make; then
    echo "[GUEST][ERROR] Hashtable build failed"
    m5 exit
    exit 1
  fi
fi
if ! ./hashtable; then
  echo "[GUEST][ERROR] Hashtable run failed"
  m5 exit
  exit 1
fi

m5 exit
RCSEOF
    ;;
  sepim_cmd_smoke)
    BOOT_SCRIPT="$ROOT_DIR/scripts/guest_run_sepim_cmd.rcS"
    cat > "$BOOT_SCRIPT" <<'RCSEOF'
#!/bin/sh
set -ex

cd /home/pim_driver
mknod /dev/pimbt c 70 0 || true
if ! insmod ./test-driver.ko; then
  echo "[GUEST][ERROR] Failed to insert /home/pim_driver/test-driver.ko"
  dmesg | tail -n 50 || true
  m5 exit
  exit 1
fi
chmod 666 /dev/pimbt

cd /home/workloads/sepim_cmd
if [ -x ./sepim_cmd ]; then
  echo "[GUEST][INFO] Using prebuilt /home/workloads/sepim_cmd/sepim_cmd"
else
  echo "[GUEST][INFO] Building /home/workloads/sepim_cmd/sepim_cmd in guest"
  if ! make; then
    echo "[GUEST][ERROR] sepim_cmd build failed"
    m5 exit
    exit 1
  fi
fi
if ! ./sepim_cmd; then
  echo "[GUEST][ERROR] sepim_cmd run failed"
  m5 exit
  exit 1
fi

m5 exit
RCSEOF
    ;;
  boot_probe)
    BOOT_SCRIPT="$ROOT_DIR/scripts/guest_boot_probe.rcS"
    cat > "$BOOT_SCRIPT" <<'RCSEOF'
#!/bin/sh
set -ex
echo "[GUEST][PROBE] readfile executed"
m5 exit
RCSEOF
    ;;
  *)
    fail_gate "GATE 3" "Unsupported MODE=$MODE (expected checkpoint, hash_table, sepim_cmd_smoke, or boot_probe)" "$LOG_FILE"
    exit 1
    ;;
esac

chmod +x "$BOOT_SCRIPT"

if [[ "$MODE" == "hash_table" ]]; then
  echo "[INFO] Hash-table mode selected: guest will install driver and run prebuilt hashtable workload"
elif [[ "$MODE" == "sepim_cmd_smoke" ]]; then
  echo "[INFO] SE-PIM command smoke mode selected: guest will run /home/workloads/sepim_cmd/sepim_cmd"
elif [[ "$MODE" == "boot_probe" ]]; then
  echo "[INFO] Boot-probe mode selected: guest will print probe marker then exit"
fi

echo "[INFO] Running baseline full-system boot (mode=$MODE)"
# shellcheck disable=SC2086
M5_PATH="$FS_BUNDLE_DIR" "$GEM5_BIN" \
  --outdir="$OUTDIR" \
  "$FS_CONFIG" \
  --machine-type=VExpress_EMM64 \
  -n "$CPUS" \
  --mem-size="$MEM_SIZE" \
  --disk-image="$DISK_IMAGE" \
  --dtb-file="$DTB" \
  --kernel="$KERNEL" \
  --script="$BOOT_SCRIPT" \
  $GEM5_EXTRA_ARGS

if [[ "$MODE" == "hash_table" || "$MODE" == "sepim_cmd_smoke" ]]; then
  if [[ -f "$OUTDIR/system.terminal" ]] && \
     tr -d '\000' < "$OUTDIR/system.terminal" | grep -Fq "[GUEST][ERROR]"; then
    fail_gate "GATE 3" "Guest workload run reported error; inspect $OUTDIR/system.terminal" "$LOG_FILE"
    exit 1
  fi
fi

echo "[PASS] run_baseline_fs.sh completed"
