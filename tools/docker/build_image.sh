#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
LOG_DIR="$ROOT_DIR/logs/build"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/docker_build_$(date +%Y%m%d_%H%M%S).log"
DIGEST_FILE="$LOG_DIR/docker_image.txt"

IMAGE_NAME=${IMAGE_NAME:-sepim-impica:ubuntu18}

if command -v docker >/dev/null 2>&1; then
  if docker info >/dev/null 2>&1; then
    RUNTIME=(docker)
  elif sudo -n docker info >/dev/null 2>&1; then
    RUNTIME=(sudo -n docker)
  else
    echo "Docker is installed but not accessible (try running with sudo/root)." | tee "$LOG_FILE"
    exit 1
  fi
elif command -v podman >/dev/null 2>&1; then
  RUNTIME=(podman)
else
  echo "No container runtime found (docker/podman)." | tee "$LOG_FILE"
  exit 1
fi

{
  echo "[INFO] Runtime: ${RUNTIME[*]}"
  echo "[INFO] Image: $IMAGE_NAME"
  echo "[INFO] Building from $ROOT_DIR/tools/docker/Dockerfile"
  "${RUNTIME[@]}" build --network host -t "$IMAGE_NAME" -f "$ROOT_DIR/tools/docker/Dockerfile" "$ROOT_DIR"

  IMAGE_ID=$("${RUNTIME[@]}" image inspect "$IMAGE_NAME" --format '{{.Id}}')
  REPO_DIGEST=$("${RUNTIME[@]}" image inspect "$IMAGE_NAME" --format '{{index .RepoDigests 0}}' || true)

  {
    echo "timestamp=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "runtime=${RUNTIME[*]}"
    echo "image=$IMAGE_NAME"
    echo "image_id=$IMAGE_ID"
    echo "repo_digest=${REPO_DIGEST:-unavailable-local-build}"
  } | tee "$DIGEST_FILE"
} | tee "$LOG_FILE"

printf '\n[INFO] Image metadata saved to %s\n' "$DIGEST_FILE"
