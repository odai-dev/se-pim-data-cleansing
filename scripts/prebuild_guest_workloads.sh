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
FAST_INPUT_SIZE=${FAST_INPUT_SIZE:-0}
FAST_INPUT_FILE="$HASHTABLE_DIR/input_fast.c"
META_FILE="$HASHTABLE_DIR/.prebuilt_mode"

if [[ ! -d "$HASHTABLE_DIR" ]]; then
  fail_gate "GATE 3" "Missing workload directory: $HASHTABLE_DIR" "$LOG_FILE"
  exit 1
fi

if ! command -v "$CROSS_CXX" >/dev/null 2>&1; then
  fail_gate "GATE 3" "Missing cross compiler: $CROSS_CXX" "$LOG_FILE"
  exit 1
fi

use_fast_input=0
make_cpps="./hashtable.c ./input.c"
input_size_flag=""
mode_cflags=""
build_mode="full"
if [[ "$FAST_INPUT_SIZE" =~ ^[0-9]+$ ]] && (( FAST_INPUT_SIZE > 0 )); then
  use_fast_input=1
  build_mode="fast:$FAST_INPUT_SIZE:safev2"
  echo "[INFO] FAST_INPUT_SIZE=$FAST_INPUT_SIZE; generating compact input table"
  {
    echo '#include "hashtable.h"'
    echo
    echo 'input_item input_table[] = {'
    awk -v n="$FAST_INPUT_SIZE" '
      /^input_item input_table\[\] = \{/ { in_table=1; next }
      in_table && /^\};/ { exit }
      in_table && copied < n {
        print
        copied++
      }
      END {
        if (copied == 0) {
          exit 2
        }
      }
    ' "$HASHTABLE_DIR/input.c"
    echo '};'
  } > "$FAST_INPUT_FILE"
  make_cpps="./hashtable.c ./input_fast.c"
  input_size_flag="-DINPUT_SIZE=$FAST_INPUT_SIZE"
  # Fast mode is for GATE 3 bring-up; avoid in-workload checkpoints and pre-grab page-table path.
  mode_cflags="-DDISABLE_GRAB_PAGE_TABLE=1 -DDISABLE_GEM5_CHECKPOINT=1"

  if ! grep -q "DISABLE_GRAB_PAGE_TABLE" "$HASHTABLE_DIR/hashtable.c"; then
    echo "[INFO] Patching hashtable.c to support DISABLE_GRAB_PAGE_TABLE in fast mode"
    tmp_src=$(mktemp)
    while IFS= read -r line; do
      if [[ "$line" == *"grab_pim_table();"* ]]; then
        echo "#if !defined(DISABLE_GRAB_PAGE_TABLE)" >> "$tmp_src"
        echo "$line" >> "$tmp_src"
        echo "#endif" >> "$tmp_src"
      else
        echo "$line" >> "$tmp_src"
      fi
    done < "$HASHTABLE_DIR/hashtable.c"
    mv "$tmp_src" "$HASHTABLE_DIR/hashtable.c"
  fi

  if ! grep -q "DISABLE_GEM5_CHECKPOINT" "$HASHTABLE_DIR/hashtable.c"; then
    echo "[INFO] Patching hashtable.c to support DISABLE_GEM5_CHECKPOINT in fast mode"
    tmp_src=$(mktemp)
    while IFS= read -r line; do
      if [[ "$line" == *"m5_checkpoint(0, 0);"* ]]; then
        echo "#if !defined(DISABLE_GEM5_CHECKPOINT)" >> "$tmp_src"
        echo "$line" >> "$tmp_src"
        echo "#endif" >> "$tmp_src"
      else
        echo "$line" >> "$tmp_src"
      fi
    done < "$HASHTABLE_DIR/hashtable.c"
    mv "$tmp_src" "$HASHTABLE_DIR/hashtable.c"
  fi
fi

needs_rebuild=1
if [[ -x "$HASHTABLE_DIR/hashtable" ]]; then
  if [[ "$HASHTABLE_DIR/hashtable" -nt "$HASHTABLE_DIR/hashtable.c" && \
        "$HASHTABLE_DIR/hashtable" -nt "$HASHTABLE_DIR/input.c" && \
        "$HASHTABLE_DIR/hashtable" -nt "$HASHTABLE_DIR/m5op_arm_A64.S" ]] && \
     file "$HASHTABLE_DIR/hashtable" | grep -q "ARM aarch64"; then
    if [[ -f "$META_FILE" ]] && [[ "$(cat "$META_FILE")" == "$build_mode" ]]; then
      needs_rebuild=0
    fi
  fi
fi

if [[ "$needs_rebuild" == "0" ]]; then
  echo "[INFO] Reusing existing prebuilt AArch64 hashtable binary ($build_mode)"
  if [[ "$use_fast_input" == "1" ]]; then
    rm -f "$FAST_INPUT_FILE"
  fi
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
    CPPS="$make_cpps" \
    CFLAGS="-O2 -std=c++0x -I. $input_size_flag $mode_cflags" \
    LDFLAGS="-O2 -pthread -lrt -std=c++0x -static -static-libstdc++ -static-libgcc" \
    hashtable
  static_rc=$?
  set -e

  if [[ $static_rc -ne 0 ]]; then
    echo "[WARN] Static link failed; retrying dynamic link"
    rm -rf obj hashtable
    mkdir -p obj
    make CC="$CROSS_CXX" \
      CPPS="$make_cpps" \
      CFLAGS="-O2 -std=c++0x -I. $input_size_flag $mode_cflags" \
      LDFLAGS="-O2 -pthread -lrt -std=c++0x" \
      hashtable
  fi

  # Keep only final binary to minimize disk image sync time.
  rm -f obj/*.o obj/deps
)

if [[ "$use_fast_input" == "1" ]]; then
  rm -f "$FAST_INPUT_FILE"
fi

if ! file "$HASHTABLE_DIR/hashtable" | grep -q "ARM aarch64"; then
  fail_gate "GATE 3" "Prebuilt hashtable is not an AArch64 binary" "$LOG_FILE"
  exit 1
fi

echo "$build_mode" > "$META_FILE"

echo "[PASS] prebuild_guest_workloads.sh completed"
