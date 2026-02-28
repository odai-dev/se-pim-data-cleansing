#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=scripts/_common.sh
source "$SCRIPT_DIR/_common.sh"

LOG_FILE=$(setup_log "$ROOT_DIR/logs/run" "prepare_disk_image")
start_logging "$LOG_FILE"

IMPICA_DIR=${IMPICA_DIR:-$ROOT_DIR/IMPICA}
FS_BUNDLE_DIR=${FS_BUNDLE_DIR:-$ROOT_DIR/third_party/gem5_fs/aarch-system-2014-10}
DISK_IMAGE=${DISK_IMAGE:-$FS_BUNDLE_DIR/disks/aarch64-ubuntu-trusty-headless.img}
MOUNT_DIR=${MOUNT_DIR:-$ROOT_DIR/.mnt/aarch64-rootfs}
OFFSET_BYTES=${OFFSET_BYTES:-32256}
CHROOT_BUILD=${CHROOT_BUILD:-1}

cleanup() {
  set +e
  for sub in proc dev sys; do
    if mountpoint -q "$MOUNT_DIR/$sub"; then
      as_root umount "$MOUNT_DIR/$sub"
    fi
  done
  if mountpoint -q "$MOUNT_DIR"; then
    as_root umount "$MOUNT_DIR"
  fi
}
trap cleanup EXIT

if [[ ! -f "$DISK_IMAGE" ]]; then
  echo "[INFO] Disk image not found; attempting to fetch gem5 ARM FS bundle"
  "$SCRIPT_DIR/fetch_gem5_fs.sh"
  if [[ ! -f "$DISK_IMAGE" ]]; then
    fail_gate "GATE 3" "Disk image not found at $DISK_IMAGE after fetch" "$LOG_FILE"
    exit 1
  fi
fi

if [[ ! -d "$IMPICA_DIR/pim_driver" || ! -d "$IMPICA_DIR/workloads" ]]; then
  fail_gate "GATE 3" "IMPICA driver/workloads not found under $IMPICA_DIR" "$LOG_FILE"
  exit 1
fi

echo "[INFO] Mounting disk image: $DISK_IMAGE"
as_root mkdir -p "$MOUNT_DIR"
as_root mount -o loop,offset="$OFFSET_BYTES" "$DISK_IMAGE" "$MOUNT_DIR"

# Copy artifacts needed in guest image.
echo "[INFO] Copying pim_driver and workloads into guest /home"
as_root rsync -a --delete "$IMPICA_DIR/pim_driver" "$MOUNT_DIR/home/"
as_root rsync -a --delete "$IMPICA_DIR/workloads" "$MOUNT_DIR/home/"

echo "[INFO] Binding proc/dev/sys for optional chroot build"
for sub in proc dev sys; do
  as_root mount --bind "/$sub" "$MOUNT_DIR/$sub"
done

as_root cp /etc/resolv.conf "$MOUNT_DIR/etc/resolv.conf"

if [[ "$CHROOT_BUILD" == "1" ]]; then
  echo "[INFO] Building selected workloads in chroot"
  as_root chroot "$MOUNT_DIR" /bin/bash -lc '
    set -e
    cd /home/workloads/hashtable && make || true
    cd /home/workloads/btree && make || true
    cd /home/workloads/llubenchmark && make || true
  '
else
  echo "[INFO] CHROOT_BUILD=0; skipping in-image workload builds"
fi

echo "[PASS] prepare_disk_image.sh completed"
