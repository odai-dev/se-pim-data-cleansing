#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=scripts/_common.sh
source "$SCRIPT_DIR/_common.sh"

ORIG_ARGS=("$@")
IMAGE_NAME=${IMAGE_NAME:-sepim-impica@sha256:b4935cb7b1343fcaef5dcf19bb7644a7cfc3843522b81b0fbf04c741ad11c296}
maybe_reexec_in_container always "scripts/$(basename "$0")" "${ORIG_ARGS[@]}"

trap 'chown -R "${HOST_UID:-0}:${HOST_GID:-0}" \
  "$ROOT_DIR/IMPICA/workloads/kmeans_sepim_fs" "$ROOT_DIR/results" "$ROOT_DIR/logs" 2>/dev/null || true' EXIT
python3 "$SCRIPT_DIR/run_native_e2e_gate.py" "$@"
