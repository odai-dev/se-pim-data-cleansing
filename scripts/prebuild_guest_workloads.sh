#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=scripts/_common.sh
source "$SCRIPT_DIR/_common.sh"

LOG_FILE=$(setup_log "$ROOT_DIR/logs/build" "prebuild_guest_workloads")
start_logging "$LOG_FILE"

IMPICA_DIR=${IMPICA_DIR:-$ROOT_DIR/IMPICA}
HASHTABLE_DIR="$IMPICA_DIR/workloads/hashtable"
CROSS_CXX=${CROSS_CXX:-aarch64-linux-gnu-g++}

if [[ ! -d "$HASHTABLE_DIR" ]]; then
  fail_gate "GATE 3" "Missing workload directory: $HASHTABLE_DIR" "$LOG_FILE"
  exit 1
fi

if ! command -v "$CROSS_CXX" >/dev/null 2>&1; then
  fail_gate "GATE 3" "Missing cross compiler: $CROSS_CXX" "$LOG_FILE"
  exit 1
fi

needs_rebuild=1
if [[ -x "$HASHTABLE_DIR/hashtable" ]]; then
  if [[ "$HASHTABLE_DIR/hashtable" -nt "$HASHTABLE_DIR/hashtable.c" && \
        "$HASHTABLE_DIR/hashtable" -nt "$HASHTABLE_DIR/input.c" && \
        "$HASHTABLE_DIR/hashtable" -nt "$HASHTABLE_DIR/m5op_arm_A64.S" ]] && \
     file "$HASHTABLE_DIR/hashtable" | grep -q "ARM aarch64"; then
    needs_rebuild=0
  fi
fi

if [[ "$needs_rebuild" == "0" ]]; then
  echo "[INFO] Reusing existing prebuilt AArch64 hashtable binary"
  echo "[PASS] prebuild_guest_workloads.sh completed"
  exit 0
fi

echo "[INFO] Prebuilding hashtable workload for AArch64 outside gem5"
(
  cd "$HASHTABLE_DIR"
  rm -rf obj
  mkdir -p obj

  set +e
  make CC="$CROSS_CXX" \
    CFLAGS="-O2 -std=c++0x -I." \
    LDFLAGS="-O2 -pthread -lrt -std=c++0x -static -static-libstdc++ -static-libgcc" \
    hashtable
  static_rc=$?
  set -e

  if [[ $static_rc -ne 0 ]]; then
    echo "[WARN] Static link failed; retrying dynamic link"
    rm -rf obj hashtable
    mkdir -p obj
    make CC="$CROSS_CXX" \
      CFLAGS="-O2 -std=c++0x -I." \
      LDFLAGS="-O2 -pthread -lrt -std=c++0x" \
      hashtable
  fi

  # Keep only final binary to minimize disk image sync time.
  rm -f obj/*.o obj/deps
)

if ! file "$HASHTABLE_DIR/hashtable" | grep -q "ARM aarch64"; then
  fail_gate "GATE 3" "Prebuilt hashtable is not an AArch64 binary" "$LOG_FILE"
  exit 1
fi

echo "[PASS] prebuild_guest_workloads.sh completed"
