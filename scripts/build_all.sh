#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=scripts/_common.sh
source "$SCRIPT_DIR/_common.sh"

LOG_FILE=$(setup_log "$ROOT_DIR/logs/build" "build_all")
start_logging "$LOG_FILE"
IMAGE_NAME=${IMAGE_NAME:-sepim-impica:ubuntu18}
JOBS=${JOBS:-4}
M5_NO_WERROR=${M5_NO_WERROR:-1}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --jobs)
      if [[ $# -lt 2 ]]; then
        echo "[ERROR] --jobs requires a value"
        exit 2
      fi
      JOBS="$2"
      shift 2
      ;;
    --jobs=*)
      JOBS="${1#*=}"
      shift
      ;;
    --image)
      if [[ $# -lt 2 ]]; then
        echo "[ERROR] --image requires a value"
        exit 2
      fi
      IMAGE_NAME="$2"
      shift 2
      ;;
    --image=*)
      IMAGE_NAME="${1#*=}"
      shift
      ;;
    --with-werror)
      M5_NO_WERROR=0
      shift
      ;;
    --no-werror)
      M5_NO_WERROR=1
      shift
      ;;
    *)
      echo "[ERROR] Unknown argument: $1"
      echo "[INFO] Usage: scripts/build_all.sh [--jobs N] [--image NAME] [--with-werror|--no-werror]"
      exit 2
      ;;
  esac
done

if ! [[ "$JOBS" =~ ^[0-9]+$ ]] || [[ "$JOBS" -lt 1 ]]; then
  echo "[ERROR] Invalid --jobs value: $JOBS"
  exit 2
fi

echo "[INFO] Building container image"
"$ROOT_DIR/tools/docker/build_image.sh"

# Avoid spawning duplicate long-running compile jobs.
if pgrep -af '/usr/bin/scons .*build/ARM/gem5\.opt' >/dev/null 2>&1; then
  fail_gate "GATE 2" "Detected existing gem5 scons build process; stop it before rerunning build_all.sh" "$LOG_FILE"
  exit 1
fi

if command -v docker >/dev/null 2>&1; then
  if docker info >/dev/null 2>&1; then
    RUNTIME=(docker)
  elif sudo -n docker info >/dev/null 2>&1; then
    RUNTIME=(sudo -n docker)
  else
    fail_gate "GATE 1" "Docker installed but not accessible without interactive sudo" "$LOG_FILE"
    exit 1
  fi
elif command -v podman >/dev/null 2>&1; then
  RUNTIME=(podman)
else
  fail_gate "GATE 1" "No docker/podman runtime found" "$LOG_FILE"
  exit 1
fi

CONTAINER_NAME="sepim-build-$$"
cleanup_container() {
  "${RUNTIME[@]}" rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true
}
trap cleanup_container INT TERM EXIT

echo "[INFO] Running baseline bootstrap + build inside container"
set +e
"${RUNTIME[@]}" run --rm --privileged \
  --name "$CONTAINER_NAME" \
  -e JOBS="$JOBS" \
  -e M5_NO_WERROR="$M5_NO_WERROR" \
  -v "$ROOT_DIR:/workspace" \
  -w /workspace \
  "$IMAGE_NAME" \
  /bin/bash -lc "scripts/bootstrap_repo.sh && scripts/build_impica.sh"
RC=$?
set -e
if [[ $RC -ne 0 ]]; then
  if [[ $RC -eq 130 ]]; then
    fail_gate "GATE 2" "Build interrupted by user (Ctrl+C)" "$LOG_FILE"
  else
    fail_gate "GATE 2" "Containerized baseline build failed" "$LOG_FILE"
  fi
  exit "$RC"
fi

trap - INT TERM EXIT
cleanup_container

echo "[PASS] build_all.sh completed (GATE 1-2)"
