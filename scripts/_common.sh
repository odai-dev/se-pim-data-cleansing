#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)

setup_log() {
  local log_dir="$1"
  local log_name="$2"
  mkdir -p "$log_dir"
  local log_file="$log_dir/${log_name}_$(date +%Y%m%d_%H%M%S).log"
  echo "$log_file"
}

start_logging() {
  local log_file="$1"
  exec > >(tee -a "$log_file") 2>&1
}

fail_gate() {
  local gate="$1"
  local reason="$2"
  local log_file="$3"
  local out="$ROOT_DIR/logs/FAILED_GATE.txt"

  {
    echo "timestamp=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "gate=$gate"
    echo "reason=$reason"
    echo "log_file=$log_file"
    echo ""
    echo "last_50_log_lines:"
    if [[ -f "$log_file" ]]; then
      tail -n 50 "$log_file"
    else
      echo "(log file not found)"
    fi
  } > "$out"

  echo "[FAIL] $gate: $reason"
  echo "[FAIL] Wrote $out"
}

as_root() {
  if [[ ${EUID:-$(id -u)} -eq 0 ]]; then
    "$@"
  else
    sudo "$@"
  fi
}
