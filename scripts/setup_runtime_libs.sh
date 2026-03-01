#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=scripts/_common.sh
source "$SCRIPT_DIR/_common.sh"

LOG_FILE=$(setup_log "$ROOT_DIR/logs/build" "setup_runtime_libs")
start_logging "$LOG_FILE"

RUNTIME_ROOT=${RUNTIME_ROOT:-$ROOT_DIR/third_party/runtime_libs}
PKG_DIR="$RUNTIME_ROOT/pkgs"
EXTRACT_DIR="$RUNTIME_ROOT/rootfs"

mkdir -p "$PKG_DIR" "$EXTRACT_DIR"

download_deb() {
  local url="$1"
  local out="$2"
  if [[ -f "$out" ]]; then
    echo "[INFO] Reusing $out"
    return 0
  fi
  echo "[INFO] Downloading $(basename "$out")"
  wget -q -O "$out" "$url"
}

download_deb \
  "http://archive.ubuntu.com/ubuntu/pool/main/p/protobuf/libprotobuf10_3.0.0-9.1ubuntu1_amd64.deb" \
  "$PKG_DIR/libprotobuf10_3.0.0-9.1ubuntu1_amd64.deb"
download_deb \
  "http://archive.ubuntu.com/ubuntu/pool/main/p/python2.7/libpython2.7_2.7.15~rc1-1_amd64.deb" \
  "$PKG_DIR/libpython2.7_2.7.15~rc1-1_amd64.deb"
download_deb \
  "http://archive.ubuntu.com/ubuntu/pool/main/p/python2.7/libpython2.7-minimal_2.7.15~rc1-1_amd64.deb" \
  "$PKG_DIR/libpython2.7-minimal_2.7.15~rc1-1_amd64.deb"
download_deb \
  "http://archive.ubuntu.com/ubuntu/pool/main/p/python2.7/libpython2.7-stdlib_2.7.15~rc1-1_amd64.deb" \
  "$PKG_DIR/libpython2.7-stdlib_2.7.15~rc1-1_amd64.deb"

rm -rf "$EXTRACT_DIR"
mkdir -p "$EXTRACT_DIR"

for deb in "$PKG_DIR"/*.deb; do
  echo "[INFO] Extracting $(basename "$deb")"
  dpkg-deb -x "$deb" "$EXTRACT_DIR"
done

if [[ ! -f "$EXTRACT_DIR/usr/lib/x86_64-linux-gnu/libpython2.7.so.1.0" ]]; then
  fail_gate "GATE 3" "Missing libpython2.7.so.1.0 after extraction" "$LOG_FILE"
  exit 1
fi
if [[ ! -f "$EXTRACT_DIR/usr/lib/x86_64-linux-gnu/libprotobuf.so.10" ]]; then
  fail_gate "GATE 3" "Missing libprotobuf.so.10 after extraction" "$LOG_FILE"
  exit 1
fi

cat <<EOF
[INFO] Runtime libs ready at: $EXTRACT_DIR
[INFO] Suggested runtime env:
  LD_LIBRARY_PATH=$EXTRACT_DIR/usr/lib/x86_64-linux-gnu:\$LD_LIBRARY_PATH
  PYTHONHOME=$EXTRACT_DIR/usr
  PYTHONPATH=$EXTRACT_DIR/usr/lib/python2.7:$EXTRACT_DIR/usr/lib/python2.7/lib-dynload:\$PYTHONPATH
EOF

echo "[PASS] setup_runtime_libs.sh completed"
