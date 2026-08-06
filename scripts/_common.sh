#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
CONTAINER_RUNTIME=()

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

mark_gate_pass() {
  local gate="$1"
  local details="$2"
  local out="$ROOT_DIR/logs/PASSED_${gate}.txt"
  rm -f "$ROOT_DIR/logs/FAILED_GATE.txt"
  {
    echo "timestamp=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "gate=${gate/GATE_/GATE }"
    echo "details=$details"
  } > "$out"
  echo "[PASS] Wrote $out"
}

as_root() {
  "$@"
}

write_run_metadata() {
  local outdir="$1"
  local gate="$2"
  local backend="$3"
  local mode="$4"
  local checkpoint_dir="$5"
  local fs_config="$6"
  local gem5_commit="$7"
  local impica_commit="$8"

  mkdir -p "$outdir"
  cat > "$outdir/metadata.json" <<EOF
{
  "timestamp_utc": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "gate": "$gate",
  "backend": "$backend",
  "mode": "$mode",
  "checkpoint_dir": "$checkpoint_dir",
  "fs_config": "$fs_config",
  "gem5_commit": "$gem5_commit",
  "impica_commit": "$impica_commit"
}
EOF
}

detect_container_runtime() {
  if command -v docker >/dev/null 2>&1; then
    if docker info >/dev/null 2>&1; then
      CONTAINER_RUNTIME=(docker)
    elif sudo -n docker info >/dev/null 2>&1; then
      CONTAINER_RUNTIME=(sudo -n docker)
    else
      return 1
    fi
  elif command -v podman >/dev/null 2>&1; then
    CONTAINER_RUNTIME=(podman)
  else
    return 1
  fi
}

maybe_reexec_in_container() {
  local mode="$1"
  local script_rel="$2"
  shift 2
  local -a orig_args=("$@")
  local -a explicit_env=()
  local -a git_mounts=()
  local image="${IMAGE_NAME:-sepim-impica:ubuntu18}"
  local needs_container=0
  local quoted_args
  local host_uid host_gid

  if [[ "${SEPIM_IN_CONTAINER:-0}" == "1" ]]; then
    return 0
  fi

  case "$mode" in
    always)
      needs_container=1
      ;;
    auto)
      if ! command -v aarch64-linux-gnu-gcc >/dev/null 2>&1; then
        needs_container=1
      fi
      ;;
    never)
      needs_container=0
      ;;
    *)
      echo "[ERROR] Invalid container mode: $mode (expected always|auto|never)"
      exit 2
      ;;
  esac

  if [[ "${SEPIM_FORCE_DOCKER:-0}" == "1" ]]; then
    needs_container=1
  fi

  if [[ "$needs_container" -ne 1 ]]; then
    return 0
  fi

  if ! detect_container_runtime; then
    echo "[ERROR] Container runtime unavailable (docker/podman), but container mode is '$mode'."
    exit 1
  fi

  if ! "${CONTAINER_RUNTIME[@]}" image inspect "$image" >/dev/null 2>&1; then
    echo "[ERROR] Container image not found: $image"
    echo "[HINT] Build it first: tools/docker/build_image.sh"
    exit 1
  fi

  host_uid=$(id -u)
  host_gid=$(id -g)
  # Propagate only this explicitly supported experiment input.  Pass it as one
  # argv element (never through eval or the inner shell command) so whitespace
  # and shell metacharacters cannot alter the container invocation.  Translate
  # host workspace paths to the sole /workspace bind mount.
  if [[ "${DISK_IMAGE+x}" == "x" ]]; then
    local container_disk_image="$DISK_IMAGE"
    if [[ "$container_disk_image" == "$ROOT_DIR" ]]; then
      container_disk_image=/workspace
    elif [[ "$container_disk_image" == "$ROOT_DIR/"* ]]; then
      container_disk_image="/workspace/${container_disk_image#"$ROOT_DIR/"}"
    fi
    explicit_env=(-e "DISK_IMAGE=$container_disk_image")
  fi
  # A disposable experiment copy may be a Git worktree whose .git file points
  # outside the sole /workspace bind mount.  Provenance collection must see
  # the real top-level and nested-IMPICA object databases, but it never needs
  # to write them, so mount external common directories at their recorded
  # absolute paths read-only.
  local repo common_git seen_git=""
  for repo in "$ROOT_DIR" "$ROOT_DIR/IMPICA"; do
    if [[ -f "$repo/.git" ]]; then
      common_git=$(git -C "$repo" rev-parse --git-common-dir)
      if [[ "$common_git" != /* ]]; then
        common_git=$(realpath "$repo/$common_git")
      else
        common_git=$(realpath "$common_git")
      fi
      case "$common_git" in
        "$ROOT_DIR"|"$ROOT_DIR"/*) ;;
        *)
          if [[ ":$seen_git:" != *":$common_git:"* ]]; then
            git_mounts+=(-v "$common_git:$common_git:ro")
            seen_git="${seen_git:+$seen_git:}$common_git"
          fi
          ;;
      esac
    fi
  done
  quoted_args=$(printf '%q ' "${orig_args[@]}")
  echo "[INFO] Re-running inside container image $image (mode=$mode)"
  exec "${CONTAINER_RUNTIME[@]}" run --rm --privileged \
    -v "$ROOT_DIR:/workspace" \
    -v "$ROOT_DIR:$ROOT_DIR" \
    "${git_mounts[@]}" \
    -w /workspace \
    -e SEPIM_IN_CONTAINER=1 \
    -e IMAGE_NAME="$image" \
    -e HOST_UID="$host_uid" \
    -e HOST_GID="$host_gid" \
    "${explicit_env[@]}" \
    "$image" \
    /bin/bash -lc "set -euo pipefail; trap 'chown -R \"\$HOST_UID:\$HOST_GID\" /workspace/results /workspace/logs /workspace/scripts/guest_*.rcS 2>/dev/null || true' EXIT; $script_rel $quoted_args"
}
