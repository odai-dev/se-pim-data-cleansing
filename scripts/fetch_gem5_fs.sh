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
FLAT_DIR="$FS_ROOT"

URLS=(
  "https://dist.gem5.org/dist/current/arm/$ARCHIVE_NAME"
  "http://dist.gem5.org/dist/current/arm/$ARCHIVE_NAME"
  "https://www.gem5.org/dist/current/arm/$ARCHIVE_NAME"
  "http://www.gem5.org/dist/current/arm/$ARCHIVE_NAME"
)

mkdir -p "$FS_ROOT"

bundle_ready() {
  local candidate
  for candidate in "$EXTRACTED_DIR" "$FLAT_DIR"; do
    if [[ -f "$candidate/disks/aarch64-ubuntu-trusty-headless.img" && \
          -f "$candidate/binaries/vmlinux.aarch64.20140821" && \
          -f "$candidate/binaries/vexpress.aarch64.20140821.dtb" ]]; then
      BUNDLE_DIR="$candidate"
      return 0
    fi
  done
  return 1
}

if bundle_ready; then
  echo "[INFO] FS bundle already present at $BUNDLE_DIR"
  echo "[PASS] fetch_gem5_fs.sh completed"
  exit 0
fi

archive_valid() {
  [[ -f "$ARCHIVE_PATH" ]] && tar -tJf "$ARCHIVE_PATH" >/dev/null 2>&1
}

download_archive() {
  local downloaded=0

  for url in "${URLS[@]}"; do
    echo "[INFO] Trying: $url"
    if command -v curl >/dev/null 2>&1; then
      if curl -fL --retry 8 --retry-delay 2 --retry-all-errors \
        --connect-timeout 20 --speed-time 120 --speed-limit 1024 \
        -C - -o "$ARCHIVE_PATH" "$url"; then
        downloaded=1
        break
      fi
    elif command -v wget >/dev/null 2>&1; then
      if wget -c -O "$ARCHIVE_PATH" "$url"; then
        downloaded=1
        break
      fi
    else
      fail_gate "GATE 3" "Neither curl nor wget is available for FS bundle download" "$LOG_FILE"
      exit 1
    fi
  done

  if [[ "$downloaded" -ne 1 ]]; then
    return 1
  fi
  archive_valid
}

if archive_valid; then
  echo "[INFO] Using existing valid archive: $ARCHIVE_PATH"
else
  if [[ -f "$ARCHIVE_PATH" ]]; then
    echo "[WARN] Existing archive is incomplete/corrupt; attempting resume download: $ARCHIVE_PATH"
  else
    echo "[INFO] Downloading $ARCHIVE_NAME"
  fi
  if ! download_archive; then
    fail_gate "GATE 3" "Failed to download a valid $ARCHIVE_NAME from all known URLs" "$LOG_FILE"
    exit 1
  fi
fi

echo "[INFO] Extracting $ARCHIVE_PATH into $FS_ROOT"
rm -rf "$EXTRACTED_DIR" "$FS_ROOT/binaries" "$FS_ROOT/disks"
tar -xJf "$ARCHIVE_PATH" -C "$FS_ROOT"

if ! bundle_ready; then
  fail_gate "GATE 3" "Extracted FS bundle missing expected files under $FS_ROOT (checked nested and flat layouts)" "$LOG_FILE"
  exit 1
fi

echo "[INFO] FS bundle ready at $BUNDLE_DIR"

echo "[PASS] fetch_gem5_fs.sh completed"
