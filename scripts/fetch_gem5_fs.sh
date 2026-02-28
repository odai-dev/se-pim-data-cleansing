#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=scripts/_common.sh
source "$SCRIPT_DIR/_common.sh"

LOG_FILE=$(setup_log "$ROOT_DIR/logs/run" "fetch_gem5_fs")
start_logging "$LOG_FILE"

FS_ROOT=${FS_ROOT:-$ROOT_DIR/third_party/gem5_fs}
BUNDLE_NAME=${BUNDLE_NAME:-aarch-system-2014-10}
ARCHIVE_NAME=${ARCHIVE_NAME:-${BUNDLE_NAME}.tar.xz}
ARCHIVE_PATH="$FS_ROOT/$ARCHIVE_NAME"
EXTRACTED_DIR="$FS_ROOT/$BUNDLE_NAME"

URLS=(
  "https://dist.gem5.org/dist/current/arm/$ARCHIVE_NAME"
  "http://dist.gem5.org/dist/current/arm/$ARCHIVE_NAME"
  "https://www.gem5.org/dist/current/arm/$ARCHIVE_NAME"
  "http://www.gem5.org/dist/current/arm/$ARCHIVE_NAME"
)

mkdir -p "$FS_ROOT"

if [[ -d "$EXTRACTED_DIR" && \
      -f "$EXTRACTED_DIR/disks/aarch64-ubuntu-trusty-headless.img" && \
      -f "$EXTRACTED_DIR/binaries/vmlinux.aarch64.20140821" && \
      -f "$EXTRACTED_DIR/binaries/vexpress.aarch64.20140821.dtb" ]]; then
  echo "[INFO] FS bundle already present at $EXTRACTED_DIR"
  echo "[PASS] fetch_gem5_fs.sh completed"
  exit 0
fi

if [[ ! -f "$ARCHIVE_PATH" ]]; then
  echo "[INFO] Downloading $ARCHIVE_NAME"
  downloaded=0

  for url in "${URLS[@]}"; do
    echo "[INFO] Trying: $url"
    if command -v curl >/dev/null 2>&1; then
      if curl -fL --retry 3 --retry-delay 2 -o "$ARCHIVE_PATH" "$url"; then
        downloaded=1
        break
      fi
    elif command -v wget >/dev/null 2>&1; then
      if wget -O "$ARCHIVE_PATH" "$url"; then
        downloaded=1
        break
      fi
    else
      fail_gate "GATE 3" "Neither curl nor wget is available for FS bundle download" "$LOG_FILE"
      exit 1
    fi
  done

  if [[ "$downloaded" -ne 1 ]]; then
    fail_gate "GATE 3" "Failed to download $ARCHIVE_NAME from all known URLs" "$LOG_FILE"
    exit 1
  fi
else
  echo "[INFO] Using existing archive: $ARCHIVE_PATH"
fi

echo "[INFO] Extracting $ARCHIVE_PATH into $FS_ROOT"
tar -xJf "$ARCHIVE_PATH" -C "$FS_ROOT"

if [[ ! -d "$EXTRACTED_DIR" || \
      ! -f "$EXTRACTED_DIR/disks/aarch64-ubuntu-trusty-headless.img" || \
      ! -f "$EXTRACTED_DIR/binaries/vmlinux.aarch64.20140821" || \
      ! -f "$EXTRACTED_DIR/binaries/vexpress.aarch64.20140821.dtb" ]]; then
  fail_gate "GATE 3" "Extracted FS bundle missing expected files under $EXTRACTED_DIR" "$LOG_FILE"
  exit 1
fi

echo "[PASS] fetch_gem5_fs.sh completed"
