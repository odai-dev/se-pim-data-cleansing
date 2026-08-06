#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=scripts/_common.sh
source "$SCRIPT_DIR/_common.sh"

# maybe_reexec_in_container intentionally forwards only a small fixed
# environment.  Preserve an explicitly supplied DISK_IMAGE as a command-line
# argument so the checkpoint can be created from a disposable disk clone.
ORIG_ARGS=("$@")
if [[ "${SEPIM_IN_CONTAINER:-0}" != "1" ]]; then
  container_args=()
  disk_arg_present=0
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --disk-image)
        if [[ $# -lt 2 ]]; then
          echo "[ERROR] --disk-image requires a path"
          exit 2
        fi
        host_disk=$(realpath -m "$2")
        case "$host_disk" in
          "$ROOT_DIR"/*)
            container_args+=(--disk-image "/workspace/${host_disk#"$ROOT_DIR"/}")
            ;;
          *)
            echo "[ERROR] Custom disk image must be inside the mounted workspace: $host_disk"
            exit 1
            ;;
        esac
        disk_arg_present=1
        shift 2
        ;;
      --disk-image=*)
        host_disk=$(realpath -m "${1#*=}")
        case "$host_disk" in
          "$ROOT_DIR"/*)
            container_args+=(--disk-image "/workspace/${host_disk#"$ROOT_DIR"/}")
            ;;
          *)
            echo "[ERROR] Custom disk image must be inside the mounted workspace: $host_disk"
            exit 1
            ;;
        esac
        disk_arg_present=1
        shift
        ;;
      --parent-checkpoint)
        if [[ $# -lt 2 ]]; then
          echo "[ERROR] --parent-checkpoint requires a path"
          exit 2
        fi
        host_parent=$(realpath -m "$2")
        case "$host_parent" in
          "$ROOT_DIR"/*)
            container_args+=(--parent-checkpoint "/workspace/${host_parent#"$ROOT_DIR"/}")
            ;;
          *)
            echo "[ERROR] Parent checkpoint must be inside the mounted workspace: $host_parent"
            exit 1
            ;;
        esac
        shift 2
        ;;
      --parent-checkpoint=*)
        host_parent=$(realpath -m "${1#*=}")
        case "$host_parent" in
          "$ROOT_DIR"/*)
            container_args+=(--parent-checkpoint "/workspace/${host_parent#"$ROOT_DIR"/}")
            ;;
          *)
            echo "[ERROR] Parent checkpoint must be inside the mounted workspace: $host_parent"
            exit 1
            ;;
        esac
        shift
        ;;
      *)
        container_args+=("$1")
        shift
        ;;
    esac
  done
  ORIG_ARGS=("${container_args[@]}")
  if [[ "$disk_arg_present" == "0" && -n "${DISK_IMAGE:-}" ]]; then
    host_disk=$(realpath -m "$DISK_IMAGE")
    case "$host_disk" in
      "$ROOT_DIR"/*)
        ORIG_ARGS+=(--disk-image "/workspace/${host_disk#"$ROOT_DIR"/}")
        ;;
      *)
        echo "[ERROR] Custom DISK_IMAGE must be inside the mounted workspace: $host_disk"
        exit 1
        ;;
    esac
  fi
fi
IMAGE_NAME=${IMAGE_NAME:-sepim-impica@sha256:b4935cb7b1343fcaef5dcf19bb7644a7cfc3843522b81b0fbf04c741ad11c296}
maybe_reexec_in_container always "scripts/$(basename "$0")" "${ORIG_ARGS[@]}"

OUTDIR=""
CPU_TYPE="timing"
CUSTOM_DISK_IMAGE=""
PARENT_CHECKPOINT=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --out-dir) OUTDIR="$2"; shift 2 ;;
    --out-dir=*) OUTDIR="${1#*=}"; shift ;;
    --cpu-type) CPU_TYPE="$2"; shift 2 ;;
    --cpu-type=*) CPU_TYPE="${1#*=}"; shift ;;
    --disk-image) CUSTOM_DISK_IMAGE="$2"; shift 2 ;;
    --disk-image=*) CUSTOM_DISK_IMAGE="${1#*=}"; shift ;;
    --parent-checkpoint) PARENT_CHECKPOINT="$2"; shift 2 ;;
    --parent-checkpoint=*) PARENT_CHECKPOINT="${1#*=}"; shift ;;
    --help|-h)
      echo "Usage: scripts/create_native_checkpoint.sh [--out-dir DIR] [--cpu-type timing|atomic] [--disk-image IMAGE] [--parent-checkpoint DIR]"
      echo "  timing (default): checkpoint for publication-oriented timing runs"
      echo "  atomic: functional/smoke checkpoint only"
      echo "  --disk-image: injected guest disk to bind into checkpoint provenance"
      echo "  --parent-checkpoint: emit a TimingSimpleCPU checkpoint from a validated parent restore"
      exit 0
      ;;
    *) echo "[ERROR] Unknown argument: $1"; exit 2 ;;
  esac
done

case "$CPU_TYPE" in
  timing|atomic) ;;
  *) echo "[ERROR] --cpu-type must be timing or atomic, got: $CPU_TYPE"; exit 2 ;;
esac

if [[ -n "$PARENT_CHECKPOINT" && "$CPU_TYPE" != "timing" ]]; then
  echo "[ERROR] --parent-checkpoint is supported only with --cpu-type timing"
  exit 2
fi

if [[ -z "$OUTDIR" ]]; then
  OUTDIR="$ROOT_DIR/results/raw/native_reserved_${CPU_TYPE}_checkpoint_$(date -u +%Y%m%dT%H%M%SZ)"
elif [[ "$OUTDIR" != /* ]]; then
  OUTDIR="$ROOT_DIR/$OUTDIR"
fi
if [[ -e "$OUTDIR" ]]; then
  echo "[ERROR] Refusing to overwrite checkpoint output: $OUTDIR"
  exit 1
fi

trap 'chown -R "${HOST_UID:-0}:${HOST_GID:-0}" \
  "$ROOT_DIR/results" "$ROOT_DIR/logs" 2>/dev/null || true' EXIT

PROVENANCE_HELPER="$SCRIPT_DIR/checkpoint_provenance.py"
PROVENANCE_SNAPSHOT="$OUTDIR/.checkpoint_inputs.pre.json"
PROVENANCE_OUTPUT="$OUTDIR/checkpoint_provenance.json"
IMPICA_DIR=${IMPICA_DIR:-$ROOT_DIR/IMPICA}
GEM5_DIR=${GEM5_DIR:-$IMPICA_DIR/gem5}
GEM5_BIN=${GEM5_BIN:-$GEM5_DIR/build/ARM/gem5.opt}
FS_BUNDLE_ROOT=${FS_BUNDLE_ROOT:-$ROOT_DIR/third_party/gem5_fs}
FS_BUNDLE_DIR=${FS_BUNDLE_DIR:-$FS_BUNDLE_ROOT/aarch-system-2014-10}
KERNEL=${KERNEL:-}
DTB=${DTB:-}
BOOTLOADER=${BOOTLOADER:-}
CPUS=4
MEM_SIZE=2048MB
KERNEL_MEM_LIMIT=1984MB

absolute_existing_path() {
  local path="$1"
  if [[ "$path" != /* ]]; then
    path="$ROOT_DIR/$path"
  fi
  if [[ ! -e "$path" ]]; then
    echo "[ERROR] Required checkpoint input is missing: $path" >&2
    return 1
  fi
  realpath "$path"
}

resolve_bundle_dir() {
  local candidate
  for candidate in "$FS_BUNDLE_DIR" "$FS_BUNDLE_ROOT"; do
    if [[ -f "$candidate/disks/aarch64-ubuntu-trusty-headless.img" && \
          -f "$candidate/binaries/vmlinux.aarch64.20140821" && \
          -f "$candidate/binaries/vexpress.aarch64.20140821.dtb" && \
          -f "$candidate/binaries/boot_emm.arm64" ]]; then
      FS_BUNDLE_DIR=$(realpath "$candidate")
      return 0
    fi
  done
  return 1
}

if [[ -n "$CUSTOM_DISK_IMAGE" ]]; then
  DISK_IMAGE=$(absolute_existing_path "$CUSTOM_DISK_IMAGE")
elif [[ -n "${DISK_IMAGE:-}" ]]; then
  DISK_IMAGE=$(absolute_existing_path "$DISK_IMAGE")
fi
if [[ -n "$PARENT_CHECKPOINT" ]]; then
  PARENT_CHECKPOINT=$(absolute_existing_path "$PARENT_CHECKPOINT")
  if [[ ! -d "$PARENT_CHECKPOINT" || ! -f "$PARENT_CHECKPOINT/checkpoint_provenance.json" ]]; then
    echo "[ERROR] Parent checkpoint requires a checkpoint_provenance.json sidecar: $PARENT_CHECKPOINT"
    exit 1
  fi
fi
export DISK_IMAGE

if [[ -z "$PARENT_CHECKPOINT" ]]; then
  echo "[INFO] Injecting the finalized workload tree before cold boot"
  "$SCRIPT_DIR/prepare_disk_image.sh"
else
  echo "[INFO] Reusing the immutable parent disk; no reinjection is permitted"
fi

if ! resolve_bundle_dir; then
  echo "[ERROR] Unable to resolve the gem5 ARM FS bundle after disk preparation"
  exit 1
fi
if [[ -z "${DISK_IMAGE:-}" ]]; then
  DISK_IMAGE="$FS_BUNDLE_DIR/disks/aarch64-ubuntu-trusty-headless.img"
fi
DISK_IMAGE=$(absolute_existing_path "$DISK_IMAGE")
if [[ -z "$KERNEL" ]]; then
  KERNEL="$FS_BUNDLE_DIR/binaries/vmlinux.aarch64.20140821"
fi
if [[ -z "$DTB" ]]; then
  DTB="$FS_BUNDLE_DIR/binaries/vexpress.aarch64.20140821.dtb"
fi
if [[ -z "$BOOTLOADER" ]]; then
  BOOTLOADER="$FS_BUNDLE_DIR/binaries/boot_emm.arm64"
fi
KERNEL=$(absolute_existing_path "$KERNEL")
DTB=$(absolute_existing_path "$DTB")
BOOTLOADER=$(absolute_existing_path "$BOOTLOADER")
export DISK_IMAGE FS_BUNDLE_DIR KERNEL DTB

if [[ -n "$PARENT_CHECKPOINT" ]]; then
  python3 - "$PARENT_CHECKPOINT/checkpoint_provenance.json" "$DISK_IMAGE" <<'PY'
import hashlib
import json
import pathlib
import sys

sidecar = pathlib.Path(sys.argv[1])
disk = pathlib.Path(sys.argv[2])
document = json.loads(sidecar.read_text(encoding="utf-8"))
if document.get("schema_version") != 1:
    raise SystemExit("[ERROR] parent checkpoint provenance must be schema 1")
record = document.get("inputs", {}).get("disk_image", {})
digest = hashlib.sha256()
with disk.open("rb") as stream:
    for block in iter(lambda: stream.read(1024 * 1024), b""):
        digest.update(block)
if record.get("bytes") != disk.stat().st_size or record.get("sha256") != digest.hexdigest():
    raise SystemExit("[ERROR] supplied disk does not match the parent checkpoint provenance")
print("[PASS] parent checkpoint and immutable base disk are hash-bound")
PY
fi

if [[ ! -f "$PROVENANCE_HELPER" ]]; then
  echo "[ERROR] Checkpoint provenance helper is missing: $PROVENANCE_HELPER"
  exit 1
fi

CREATION_KIND=cold_boot
RESTORE_ARGS="--cpu-type=$CPU_TYPE"
RUN_MODE=checkpoint
OUTPUT_RESTORE_INDEX=1
PROVENANCE_PARENT_ARGS=()
CREATOR_INPUT_ARGS=(
  --creator-input "checkpoint_creator=$SCRIPT_DIR/create_native_checkpoint.sh"
  --creator-input "provenance_helper=$PROVENANCE_HELPER"
  --creator-input "baseline_runner=$SCRIPT_DIR/run_baseline_fs.sh"
  --creator-input "common_helpers=$SCRIPT_DIR/_common.sh"
)
if [[ -n "$PARENT_CHECKPOINT" ]]; then
  CREATION_KIND=timing_recheckpoint_from_parent
  RESTORE_ARGS="-r 1 --checkpoint-dir=$OUTDIR --cpu-type=timing --restore-with-cpu=timing"
  RUN_MODE=custom
  OUTPUT_RESTORE_INDEX=2
  PROVENANCE_PARENT_ARGS=(--parent-checkpoint-dir "$PARENT_CHECKPOINT")
  CREATOR_INPUT_ARGS+=(
    --creator-input "guest_checkpoint_script=$SCRIPT_DIR/guest_timing_recheckpoint.rcS"
  )
else
  CREATOR_INPUT_ARGS+=(
    --creator-input "guest_checkpoint_script=$SCRIPT_DIR/guest_boot_checkpoint.rcS"
    --creator-input "disk_preparer=$SCRIPT_DIR/prepare_disk_image.sh"
  )
fi
CHECKPOINT_COMMAND="OUTDIR=$OUTDIR MEM_SIZE=$MEM_SIZE SEPIM_KERNEL_MEM=$KERNEL_MEM_LIMIT CPUS=$CPUS GEM5_EXTRA_ARGS=$RESTORE_ARGS scripts/run_baseline_fs.sh --mode $RUN_MODE"
python3 "$PROVENANCE_HELPER" capture \
  --project-root "$ROOT_DIR" \
  --snapshot "$PROVENANCE_SNAPSHOT" \
  --checkpoint-dir "$OUTDIR" \
  --disk-image "$DISK_IMAGE" \
  --gem5-opt "$GEM5_BIN" \
  --aarch64-guest "$IMPICA_DIR/workloads/kmeans_sepim_fs/kmeans_sepim_fs" \
  --test-driver-ko "$IMPICA_DIR/pim_driver/test-driver.ko" \
  --kmeans-oracle "$IMPICA_DIR/workloads/kmeans_sepim_fs/kmeans_digest_oracle" \
  --kernel "$KERNEL" \
  --dtb "$DTB" \
  --bootloader "$BOOTLOADER" \
  --dataset-generator "$SCRIPT_DIR/corrupt_dataset.py" \
  --dataset-wrapper "$SCRIPT_DIR/generate_native_dataset_matrix.py" \
  --workload-data-root "$IMPICA_DIR/workloads/kmeans_sepim_fs/data" \
  --cpu-type "$CPU_TYPE" \
  --num-cpus "$CPUS" \
  --memory-size "$MEM_SIZE" \
  --kernel-memory-limit "$KERNEL_MEM_LIMIT" \
  --container-image "$IMAGE_NAME" \
  --working-directory "$ROOT_DIR" \
  --command "$CHECKPOINT_COMMAND" \
  --creation-kind "$CREATION_KIND" \
  --environment "OUTDIR=$OUTDIR" \
  --environment "MEM_SIZE=$MEM_SIZE" \
  --environment "SEPIM_KERNEL_MEM=$KERNEL_MEM_LIMIT" \
  --environment "CPUS=$CPUS" \
  --environment "GEM5_EXTRA_ARGS=$RESTORE_ARGS" \
  --environment "DISK_IMAGE=$DISK_IMAGE" \
  --environment "KERNEL=$KERNEL" \
  --environment "DTB=$DTB" \
  --environment "FS_BUNDLE_DIR=$FS_BUNDLE_DIR" \
  "${CREATOR_INPUT_ARGS[@]}" \
  "${PROVENANCE_PARENT_ARGS[@]}"

if [[ -n "$PARENT_CHECKPOINT" ]]; then
  python3 - "$PARENT_CHECKPOINT" "$OUTDIR" <<'PY'
import json
import pathlib
import shutil
import sys

parent = pathlib.Path(sys.argv[1])
output = pathlib.Path(sys.argv[2])
document = json.loads(
    (parent / "checkpoint_provenance.json").read_text(encoding="utf-8")
)
selected = document.get("selected_checkpoint", {}).get("selected_checkpoint")
if not isinstance(selected, str) or not selected.startswith("cpt."):
    raise SystemExit("[ERROR] parent provenance has no selected checkpoint")
source = parent / selected
destination = output / selected
if destination.exists():
    raise SystemExit(f"[ERROR] staged restore checkpoint already exists: {destination}")
shutil.copytree(source, destination, copy_function=shutil.copy2)
print(f"[PASS] staged immutable parent checkpoint copy: {destination}")
PY
fi

echo "[INFO] Creating 2 GiB $CPU_TYPE-CPU checkpoint with the top 64 MiB reserved from Linux"
CHECKPOINT_STARTED_UTC=$(date -u +%Y-%m-%dT%H:%M:%SZ)
if [[ -n "$PARENT_CHECKPOINT" ]]; then
  OUTDIR="$OUTDIR" MEM_SIZE="$MEM_SIZE" SEPIM_KERNEL_MEM="$KERNEL_MEM_LIMIT" CPUS="$CPUS" \
    BOOT_SCRIPT="$SCRIPT_DIR/guest_timing_recheckpoint.rcS" \
    GEM5_EXTRA_ARGS="$RESTORE_ARGS" \
    "$SCRIPT_DIR/run_baseline_fs.sh" --mode custom
else
  OUTDIR="$OUTDIR" MEM_SIZE="$MEM_SIZE" SEPIM_KERNEL_MEM="$KERNEL_MEM_LIMIT" CPUS="$CPUS" \
    GEM5_EXTRA_ARGS="$RESTORE_ARGS" \
    "$SCRIPT_DIR/run_baseline_fs.sh" --mode checkpoint
fi
CHECKPOINT_FINISHED_UTC=$(date -u +%Y-%m-%dT%H:%M:%SZ)

if ! ls "$OUTDIR"/cpt.* >/dev/null 2>&1; then
  echo "[ERROR] gem5 exited without creating cpt.* under $OUTDIR"
  exit 1
fi
python3 - "$OUTDIR" "$CPU_TYPE" "$PARENT_CHECKPOINT" <<'PY'
import configparser
import pathlib
import re
import sys

outdir = pathlib.Path(sys.argv[1])
cpu_type = sys.argv[2]
parent_checkpoint = pathlib.Path(sys.argv[3]) if sys.argv[3] else None
terminal = outdir / "system.terminal"
config_path = outdir / "config.ini"
if not terminal.is_file() or not config_path.is_file():
    raise SystemExit("[ERROR] checkpoint lacks system.terminal or config.ini")

boot_terminal = (
    parent_checkpoint / "system.terminal" if parent_checkpoint else terminal
)
if not boot_terminal.is_file():
    raise SystemExit("[ERROR] checkpoint lineage lacks the cold-boot terminal")
text = boot_terminal.read_bytes().replace(b"\0", b"").decode("utf-8", "ignore").replace("\r", "")
cmdlines = [line for line in text.splitlines() if "Kernel command line:" in line]
if not cmdlines or not any(
    "mem=1984MB" in line.split("Kernel command line:", 1)[1].split()
    for line in cmdlines
):
    raise SystemExit("[ERROR] kernel command line lacks the exact mem=1984MB token")
if not any("Memory limited to 1984MB" in line for line in text.splitlines()):
    raise SystemExit("[ERROR] kernel did not acknowledge 'Memory limited to 1984MB'")

config = configparser.ConfigParser(interpolation=None, strict=False)
config.optionxform = str
with config_path.open() as stream:
    config.read_file(stream)
if "mem=1984MB" not in config.get("system", "boot_osflags").split():
    raise SystemExit("[ERROR] config.ini boot_osflags lacks mem=1984MB")
start, end = config.get("system", "mem_ranges").split(":", 1)
physical_bytes = int(end, 0) - int(start, 0) + 1
if physical_bytes != 2048 * 1024 * 1024:
    raise SystemExit("[ERROR] config.ini does not describe exactly 2 GiB")

expected_class = {"atomic": "AtomicSimpleCPU", "timing": "TimingSimpleCPU"}[cpu_type]
expected_mode = cpu_type
sections = sorted(
    section for section in config.sections()
    if re.match(r"^system\.cpu\d+$", section)
)
classes = {config.get(section, "type") for section in sections}
if not sections or classes != {expected_class}:
    raise SystemExit(
        "[ERROR] checkpoint CPU mismatch: %r, expected %s" % (sorted(classes), expected_class)
    )
if config.get("system", "mem_mode") != expected_mode:
    raise SystemExit(
        "[ERROR] checkpoint mem_mode mismatch: %s, expected %s"
        % (config.get("system", "mem_mode"), expected_mode)
    )
print(
    "[PASS] checkpoint provenance: cpu_type=%s mem_mode=%s physical_bytes=%d kernel_limit=1984MB"
    % (cpu_type, expected_mode, physical_bytes)
)
PY

python3 "$PROVENANCE_HELPER" finalize \
  --snapshot "$PROVENANCE_SNAPSHOT" \
  --output "$PROVENANCE_OUTPUT" \
  --checkpoint-dir "$OUTDIR" \
  --restore-index "$OUTPUT_RESTORE_INDEX" \
  --checkpoint-started-utc "$CHECKPOINT_STARTED_UTC" \
  --checkpoint-finished-utc "$CHECKPOINT_FINISHED_UTC" \
  --remove-snapshot

echo "[PASS] Native reserved-memory checkpoint: $OUTDIR (cpu_type=$CPU_TYPE, mem_mode=$CPU_TYPE)"
