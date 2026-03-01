#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=scripts/_common.sh
source "$SCRIPT_DIR/_common.sh"

LOG_FILE=$(setup_log "$ROOT_DIR/logs/run" "prepare_disk_image")
start_logging "$LOG_FILE"

IMPICA_DIR=${IMPICA_DIR:-$ROOT_DIR/IMPICA}
FS_BUNDLE_ROOT=${FS_BUNDLE_ROOT:-$ROOT_DIR/third_party/gem5_fs}
FS_BUNDLE_DIR=${FS_BUNDLE_DIR:-$FS_BUNDLE_ROOT/aarch-system-2014-10}
DISK_IMAGE=${DISK_IMAGE:-}
MOUNT_DIR=${MOUNT_DIR:-$ROOT_DIR/.mnt/aarch64-rootfs}
OFFSET_BYTES=${OFFSET_BYTES:-32256}
CHROOT_BUILD=${CHROOT_BUILD:-0}

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

inject_with_debugfs() {
  local sector_offset
  local part_img
  local ws_link
  local cmds_file
  local dbg_log
  local fsck_log
  local src_pim
  local src_work

  sector_offset=$((OFFSET_BYTES / 512))
  part_img="/tmp/sepim_rootfs_part_$$.img"
  ws_link="/tmp/sepim_ws_$$"
  cmds_file="/tmp/sepim_debugfs_cmds_$$.txt"
  dbg_log="/tmp/sepim_debugfs_$$.log"
  fsck_log="/tmp/sepim_e2fsck_$$.log"

  src_pim="$ws_link/IMPICA/pim_driver"
  src_work="$ws_link/IMPICA/workloads"

  ln -sfn "$ROOT_DIR" "$ws_link"

  echo "[INFO] Rootless fallback: extracting rootfs partition to $part_img"
  dd if="$DISK_IMAGE" of="$part_img" bs=512 skip="$sector_offset" status=none

  : > "$cmds_file"
  echo "mkdir /home/pim_driver" >> "$cmds_file"
  echo "mkdir /home/workloads" >> "$cmds_file"

  while IFS= read -r dir; do
    local rel
    rel="${dir#$src_pim/}"
    [[ "$dir" == "$src_pim" ]] && continue
    echo "mkdir /home/pim_driver/$rel" >> "$cmds_file"
  done < <(find "$src_pim" -type d | LC_ALL=C sort)

  while IFS= read -r file; do
    local rel
    rel="${file#$src_pim/}"
    echo "write $file /home/pim_driver/$rel" >> "$cmds_file"
  done < <(find "$src_pim" -type f | LC_ALL=C sort)

  while IFS= read -r dir; do
    local rel
    rel="${dir#$src_work/}"
    [[ "$dir" == "$src_work" ]] && continue
    echo "mkdir /home/workloads/$rel" >> "$cmds_file"
  done < <(find "$src_work" -type d | LC_ALL=C sort)

  while IFS= read -r file; do
    local rel
    rel="${file#$src_work/}"
    echo "write $file /home/workloads/$rel" >> "$cmds_file"
  done < <(find "$src_work" -type f | LC_ALL=C sort)

  echo "[INFO] Injecting IMPICA artifacts with debugfs"
  if ! debugfs -w -f "$cmds_file" "$part_img" >"$dbg_log" 2>&1; then
    fail_gate "GATE 3" "debugfs injection failed (see $dbg_log)" "$LOG_FILE"
    rm -f "$ws_link" "$cmds_file" "$part_img"
    exit 1
  fi

  echo "[INFO] Running e2fsck after debugfs write"
  e2fsck -fy "$part_img" >"$fsck_log" 2>&1 || true

  echo "[INFO] Writing patched partition back to disk image"
  dd if="$part_img" of="$DISK_IMAGE" bs=512 seek="$sector_offset" conv=notrunc status=none

  rm -f "$ws_link" "$cmds_file" "$part_img"
  echo "[INFO] Rootless fallback injection completed"
}

if ! resolve_bundle_dir; then
  echo "[INFO] Disk image not found; attempting to fetch gem5 ARM FS bundle"
  "$SCRIPT_DIR/fetch_gem5_fs.sh"
  if ! resolve_bundle_dir; then
    fail_gate "GATE 3" "FS bundle missing expected files under $FS_BUNDLE_ROOT after fetch" "$LOG_FILE"
    exit 1
  fi
fi

if [[ -z "$DISK_IMAGE" ]]; then
  DISK_IMAGE="$FS_BUNDLE_DIR/disks/aarch64-ubuntu-trusty-headless.img"
fi

if [[ ! -d "$IMPICA_DIR/pim_driver" || ! -d "$IMPICA_DIR/workloads" ]]; then
  fail_gate "GATE 3" "IMPICA driver/workloads not found under $IMPICA_DIR" "$LOG_FILE"
  exit 1
fi

echo "[INFO] Mounting disk image: $DISK_IMAGE"
as_root mkdir -p "$MOUNT_DIR" || true
if ! as_root mount -o loop,offset="$OFFSET_BYTES" "$DISK_IMAGE" "$MOUNT_DIR"; then
  echo "[WARN] Privileged mount path unavailable; using rootless debugfs fallback"
  inject_with_debugfs
  echo "[PASS] prepare_disk_image.sh completed"
  exit 0
fi

# Copy artifacts needed in guest image.
echo "[INFO] Copying pim_driver and workloads into guest /home"
as_root rsync -a --delete "$IMPICA_DIR/pim_driver" "$MOUNT_DIR/home/"
as_root rsync -a --delete "$IMPICA_DIR/workloads" "$MOUNT_DIR/home/"

echo "[INFO] Ensuring stock gem5 tty1 readfile flow (no custom rcS hook)"
as_root rm -f "$MOUNT_DIR/etc/rcS.d/S99gem5-readfile" "$MOUNT_DIR/etc/init.d/gem5-readfile"

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
