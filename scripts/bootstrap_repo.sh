#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=scripts/_common.sh
source "$SCRIPT_DIR/_common.sh"

LOG_FILE=$(setup_log "$ROOT_DIR/logs/build" "bootstrap_repo")
start_logging "$LOG_FILE"
TARGET_DIR="$ROOT_DIR/IMPICA"
SOURCE_DIR="$ROOT_DIR/IMPICA-master"
REPO_URL="https://github.com/kha-dinh/IMPICA.git"
ARCHIVE_URL="https://codeload.github.com/kha-dinh/IMPICA/tar.gz/refs/heads/master"

if [[ -d "$TARGET_DIR" ]]; then
  echo "[INFO] Found existing $TARGET_DIR"
else
  if [[ -d "$SOURCE_DIR" ]]; then
    echo "[INFO] Found local source tree $SOURCE_DIR; copying to $TARGET_DIR"
    cp -a "$SOURCE_DIR" "$TARGET_DIR"
  else
    echo "[INFO] Cloning IMPICA from $REPO_URL"
    if ! git clone --depth 1 --filter=blob:none "$REPO_URL" "$TARGET_DIR"; then
      echo "[WARN] Shallow filtered clone failed; switching git HTTP version and retrying"
      git config --global http.version HTTP/1.1
      if ! git clone --depth 1 --filter=blob:none "$REPO_URL" "$TARGET_DIR"; then
        echo "[WARN] Git clone failed again; downloading tarball fallback"
        TARBALL="$ROOT_DIR/impica.tgz"
        wget "$ARCHIVE_URL" -O "$TARBALL"
        tar -xzf "$TARBALL" -C "$ROOT_DIR"
        mv "$ROOT_DIR/IMPICA-master" "$TARGET_DIR"
      fi
    fi
  fi
fi

if [[ ! -d "$TARGET_DIR" ]]; then
  fail_gate "GATE 2" "Unable to acquire IMPICA source tree" "$LOG_FILE"
  exit 1
fi

# When mounted into a root-run container, git may reject ownership checks.
if command -v git >/dev/null 2>&1; then
  git config --global --add safe.directory "$TARGET_DIR" || true
fi

if [[ ! -d "$TARGET_DIR/.git" ]]; then
  echo "[INFO] Initializing local git history for reproducibility"
  (
    cd "$TARGET_DIR"
    git init
    git config user.name "autonomous-agent"
    git config user.email "agent@local"
    git add .
    git commit -m "baseline snapshot"
  )
fi

if COMMIT_HASH=$(git -C "$TARGET_DIR" rev-parse HEAD 2>/dev/null); then
  echo "[INFO] IMPICA commit: $COMMIT_HASH"
else
  echo "[WARN] Could not resolve IMPICA commit hash at $TARGET_DIR"
fi

echo "[PASS] bootstrap_repo.sh completed"
