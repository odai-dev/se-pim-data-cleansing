#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=scripts/_common.sh
source "$SCRIPT_DIR/_common.sh"

LOG_FILE=$(setup_log "$ROOT_DIR/logs/build" "check_impica_bundle")
start_logging "$LOG_FILE"

echo "[INFO] Verifying bootstrap defaults and bundled source integrity"

if ! rg -n '^SOURCE_MODE=\$\{SOURCE_MODE:-bundled\}$' "$ROOT_DIR/scripts/bootstrap_repo.sh" >/dev/null 2>&1; then
  fail_gate "STATIC_BUNDLE_CHECK" "bootstrap_repo.sh default SOURCE_MODE is not bundled" "$LOG_FILE"
  exit 1
fi

if ! rg -n 'case "\$SOURCE_MODE" in' "$ROOT_DIR/scripts/bootstrap_repo.sh" >/dev/null 2>&1; then
  fail_gate "STATIC_BUNDLE_CHECK" "bootstrap_repo.sh missing SOURCE_MODE switch" "$LOG_FILE"
  exit 1
fi

if ! rg -n 'verify_bundle_manifest' "$ROOT_DIR/scripts/bootstrap_repo.sh" >/dev/null 2>&1; then
  fail_gate "STATIC_BUNDLE_CHECK" "bootstrap_repo.sh missing bundle validation path" "$LOG_FILE"
  exit 1
fi

"$ROOT_DIR/scripts/bootstrap_repo.sh" --verify-bundle

echo "[PASS] check_impica_bundle.sh completed"
