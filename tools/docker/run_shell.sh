#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
IMAGE_NAME=${IMAGE_NAME:-sepim-impica:ubuntu18}

if command -v docker >/dev/null 2>&1; then
  if docker info >/dev/null 2>&1; then
    RUNTIME=(docker)
  elif sudo -n docker info >/dev/null 2>&1; then
    RUNTIME=(sudo -n docker)
  else
    echo "Docker is installed but not accessible (try running with sudo/root)."
    exit 1
  fi
elif command -v podman >/dev/null 2>&1; then
  RUNTIME=(podman)
else
  echo "No container runtime found (docker/podman)."
  exit 1
fi

exec "${RUNTIME[@]}" run --rm -it \
  --privileged \
  -v "$ROOT_DIR:/workspace" \
  -w /workspace \
  "$IMAGE_NAME" \
  /bin/bash
