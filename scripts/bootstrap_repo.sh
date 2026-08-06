#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=scripts/_common.sh
source "$SCRIPT_DIR/_common.sh"

LOG_FILE=$(setup_log "$ROOT_DIR/logs/build" "bootstrap_repo")
start_logging "$LOG_FILE"

TARGET_DIR="$ROOT_DIR/IMPICA"
REPO_URL="https://github.com/kha-dinh/IMPICA.git"
ARCHIVE_URL="https://codeload.github.com/kha-dinh/IMPICA/tar.gz/refs/heads/master"
BUNDLE_MANIFEST="$ROOT_DIR/impica-parts/manifest.json"
PARTS_DIR="$ROOT_DIR/impica-parts"
ASSEMBLED_ARCHIVE="$ROOT_DIR/impica-source.tar.gz"
SOURCE_MODE=${SOURCE_MODE:-bundled}
VERIFY_BUNDLE_ONLY=0

usage() {
  cat <<'EOF'
Usage: scripts/bootstrap_repo.sh [--source-mode bundled|upstream] [--verify-bundle]

Defaults:
  --source-mode bundled

Modes:
  bundled  Use tracked impica-parts + manifest (strict integrity checks).
  upstream Clone/download IMPICA directly from upstream.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --source-mode)
      if [[ $# -lt 2 ]]; then
        echo "[ERROR] --source-mode requires bundled|upstream"
        exit 2
      fi
      SOURCE_MODE="$2"
      shift 2
      ;;
    --source-mode=*)
      SOURCE_MODE="${1#*=}"
      shift
      ;;
    --verify-bundle)
      VERIFY_BUNDLE_ONLY=1
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "[ERROR] Unknown argument: $1"
      usage
      exit 2
      ;;
  esac
done

verify_bundle_manifest() {
  python3 - "$BUNDLE_MANIFEST" "$PARTS_DIR" <<'PY'
import hashlib
import json
import os
import sys

manifest_path, parts_dir = sys.argv[1], sys.argv[2]
if not os.path.isfile(manifest_path):
    raise SystemExit("[ERROR] Missing bundle manifest: %s" % manifest_path)

with open(manifest_path, "r", encoding="utf-8") as f:
    manifest = json.load(f)

parts = manifest.get("parts")
expected_count = manifest.get("expected_part_count")
archive_sha = manifest.get("archive_sha256")
archive_name = manifest.get("archive_name")
if not isinstance(parts, list) or not parts:
    raise SystemExit("[ERROR] Manifest has no parts list")
if expected_count != len(parts):
    raise SystemExit("[ERROR] Manifest expected_part_count=%s but parts list has %d entries" %
                     (expected_count, len(parts)))
if not archive_sha or not archive_name:
    raise SystemExit("[ERROR] Manifest missing archive_name/archive_sha256")

for idx, item in enumerate(parts):
    rel = item.get("file")
    part_sha = item.get("sha256")
    part_bytes = item.get("bytes")
    if not rel or not part_sha:
        raise SystemExit("[ERROR] Manifest part entry %d missing file/sha256" % idx)
    path = os.path.join(parts_dir, rel)
    if not os.path.isfile(path):
        raise SystemExit("[ERROR] Missing part file listed in manifest: %s" % path)
    size = os.path.getsize(path)
    if part_bytes is not None and size != int(part_bytes):
        raise SystemExit("[ERROR] Part size mismatch for %s (expected=%s actual=%s)" %
                         (rel, part_bytes, size))
    h = hashlib.sha256()
    with open(path, "rb") as pf:
        for chunk in iter(lambda: pf.read(1024 * 1024), b""):
            h.update(chunk)
    if h.hexdigest() != part_sha:
        raise SystemExit("[ERROR] Part SHA mismatch for %s" % rel)

print("[INFO] Bundle manifest validated: %d parts, archive=%s" % (len(parts), archive_name))
PY
}

verify_assembled_archive() {
  local archive_path="$1"
  python3 - "$BUNDLE_MANIFEST" "$archive_path" <<'PY'
import hashlib
import json
import os
import sys

manifest_path, archive_path = sys.argv[1], sys.argv[2]
with open(manifest_path, "r", encoding="utf-8") as f:
    manifest = json.load(f)
expected_sha = manifest["archive_sha256"]
if not os.path.isfile(archive_path):
    raise SystemExit(1)
h = hashlib.sha256()
with open(archive_path, "rb") as af:
    for chunk in iter(lambda: af.read(1024 * 1024), b""):
        h.update(chunk)
if h.hexdigest() != expected_sha:
    raise SystemExit(2)
PY
}

assemble_bundle_archive() {
  local tmp_archive="$ROOT_DIR/.tmp_impica_source.tar.gz"
  echo "[INFO] Assembling bundled IMPICA archive from tracked parts"
  python3 - "$BUNDLE_MANIFEST" "$PARTS_DIR" "$tmp_archive" <<'PY'
import json
import os
import sys

manifest_path, parts_dir, out_path = sys.argv[1], sys.argv[2], sys.argv[3]
with open(manifest_path, "r", encoding="utf-8") as f:
    manifest = json.load(f)
parts = manifest["parts"]
with open(out_path, "wb") as out:
    for item in parts:
        part_path = os.path.join(parts_dir, item["file"])
        with open(part_path, "rb") as inp:
            for chunk in iter(lambda: inp.read(1024 * 1024), b""):
                out.write(chunk)
print(out_path)
PY
  mv "$tmp_archive" "$ASSEMBLED_ARCHIVE"
}

extract_bundled_source() {
  local topdir
  if ! verify_assembled_archive "$ASSEMBLED_ARCHIVE"; then
    echo "[WARN] Existing assembled archive missing or invalid: $ASSEMBLED_ARCHIVE"
    assemble_bundle_archive
  fi

  if ! verify_assembled_archive "$ASSEMBLED_ARCHIVE"; then
    fail_gate "GATE 2" "Assembled archive failed SHA-256 validation: $ASSEMBLED_ARCHIVE" "$LOG_FILE"
    exit 1
  fi

  topdir=$(python3 - "$ASSEMBLED_ARCHIVE" <<'PY'
import sys
import tarfile
with tarfile.open(sys.argv[1], "r:gz") as archive:
    first = next(iter(archive), None)
if first is None:
    raise SystemExit(1)
print(first.name.split("/", 1)[0])
PY
  )
  if [[ -z "$topdir" ]]; then
    fail_gate "GATE 2" "Unable to inspect assembled archive root directory" "$LOG_FILE"
    exit 1
  fi

  echo "[INFO] Extracting bundled IMPICA source from $ASSEMBLED_ARCHIVE"
  tar -xzf "$ASSEMBLED_ARCHIVE" -C "$ROOT_DIR"
  if [[ "$topdir" != "IMPICA" ]]; then
    if [[ -d "$ROOT_DIR/$topdir" ]]; then
      mv "$ROOT_DIR/$topdir" "$TARGET_DIR"
    fi
  fi
}

clone_upstream_source() {
  echo "[INFO] Cloning IMPICA from $REPO_URL"
  if ! git clone --depth 1 --filter=blob:none "$REPO_URL" "$TARGET_DIR"; then
    echo "[WARN] Shallow filtered clone failed; switching git HTTP version and retrying"
    git config --global http.version HTTP/1.1
    if ! git clone --depth 1 --filter=blob:none "$REPO_URL" "$TARGET_DIR"; then
      echo "[WARN] Git clone failed again; downloading tarball fallback"
      local tarball="$ROOT_DIR/impica.tgz"
      wget "$ARCHIVE_URL" -O "$tarball"
      tar -xzf "$tarball" -C "$ROOT_DIR"
      if [[ -d "$ROOT_DIR/IMPICA-master" ]]; then
        mv "$ROOT_DIR/IMPICA-master" "$TARGET_DIR"
      fi
    fi
  fi
}

if [[ "$SOURCE_MODE" != "bundled" && "$SOURCE_MODE" != "upstream" ]]; then
  echo "[ERROR] Invalid --source-mode: $SOURCE_MODE (expected bundled|upstream)"
  exit 2
fi

if [[ "$VERIFY_BUNDLE_ONLY" == "1" ]]; then
  verify_bundle_manifest
  if ! verify_assembled_archive "$ASSEMBLED_ARCHIVE"; then
    echo "[WARN] Assembled archive invalid or missing; rebuilding from parts"
    assemble_bundle_archive
  fi
  verify_assembled_archive "$ASSEMBLED_ARCHIVE"
  echo "[PASS] bootstrap_repo bundle verification completed"
  exit 0
fi

if [[ -d "$TARGET_DIR" ]]; then
  echo "[INFO] Found existing $TARGET_DIR"
else
  case "$SOURCE_MODE" in
    bundled)
      if ! verify_bundle_manifest; then
        fail_gate "GATE 2" "Bundled IMPICA source validation failed; fix impica-parts or run with --source-mode upstream" "$LOG_FILE"
        exit 1
      fi
      extract_bundled_source
      ;;
    upstream)
      clone_upstream_source
      ;;
  esac
fi

if [[ ! -d "$TARGET_DIR" ]]; then
  fail_gate "GATE 2" "Unable to acquire IMPICA source tree (mode=$SOURCE_MODE)" "$LOG_FILE"
  exit 1
fi

python3 - "$BUNDLE_MANIFEST" "$TARGET_DIR" <<'PY'
import hashlib
import json
import pathlib
import sys

manifest_path, source_root = map(pathlib.Path, sys.argv[1:])
manifest = json.loads(manifest_path.read_text())
expected = manifest.get("evidence_source_hashes", {})
for relative, digest in expected.items():
    path = source_root / relative
    if not path.is_file():
        raise SystemExit(f"[ERROR] Evidence source missing: {relative}")
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != digest:
        raise SystemExit(
            f"[ERROR] Evidence source hash mismatch: {relative} "
            f"expected={digest} actual={actual}"
        )
print(f"[PASS] evidence source hashes verified: {len(expected)}")
PY

# When mounted into a root-run container, git may reject ownership checks.
if command -v git >/dev/null 2>&1; then
  git config --global --add safe.directory "$TARGET_DIR" || true
fi

if [[ ! -e "$TARGET_DIR/.git" ]]; then
  echo "[INFO] Initializing local git history for reproducibility"
  SNAPSHOT_GIT_NAME=${SNAPSHOT_GIT_NAME:-$(git config --global --get user.name 2>/dev/null || echo "local-user")}
  SNAPSHOT_GIT_EMAIL=${SNAPSHOT_GIT_EMAIL:-$(git config --global --get user.email 2>/dev/null || echo "local@example.com")}
  (
    cd "$TARGET_DIR"
    git init -q
    git config user.name "$SNAPSHOT_GIT_NAME"
    git config user.email "$SNAPSHOT_GIT_EMAIL"
    git add .
    git commit -q -m "baseline snapshot"
  )
fi

if COMMIT_HASH=$(git -C "$TARGET_DIR" rev-parse HEAD 2>/dev/null); then
  echo "[INFO] IMPICA commit: $COMMIT_HASH"
else
  echo "[WARN] Could not resolve IMPICA commit hash at $TARGET_DIR"
fi

echo "[PASS] bootstrap_repo.sh completed"
