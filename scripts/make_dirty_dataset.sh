#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=scripts/_common.sh
source "$SCRIPT_DIR/_common.sh"

POINTS=${POINTS:-131072}
DIMS=${DIMS:-8}
DIRTY_FRAC=${DIRTY_FRAC:-0.10}
SEED=${SEED:-7}
OUT_DIR=${OUT_DIR:-$ROOT_DIR/IMPICA/workloads/kmeans_sepim_fs/data}
CLEAN_BIN=${CLEAN_BIN:-$OUT_DIR/kmeans_clean.bin}
DIRTY_BIN=${DIRTY_BIN:-$OUT_DIR/kmeans_dirty_10pct.bin}
META_JSON=${META_JSON:-$OUT_DIR/kmeans_dirty_10pct.meta.json}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --points) POINTS="$2"; shift 2 ;;
    --points=*) POINTS="${1#*=}"; shift ;;
    --dims) DIMS="$2"; shift 2 ;;
    --dims=*) DIMS="${1#*=}"; shift ;;
    --dirty-frac|--corruption) DIRTY_FRAC="$2"; shift 2 ;;
    --dirty-frac=*|--corruption=*) DIRTY_FRAC="${1#*=}"; shift ;;
    --seed) SEED="$2"; shift 2 ;;
    --seed=*) SEED="${1#*=}"; shift ;;
    --out-dir) OUT_DIR="$2"; shift 2 ;;
    --out-dir=*) OUT_DIR="${1#*=}"; shift ;;
    --clean-bin) CLEAN_BIN="$2"; shift 2 ;;
    --clean-bin=*) CLEAN_BIN="${1#*=}"; shift ;;
    --dirty-bin) DIRTY_BIN="$2"; shift 2 ;;
    --dirty-bin=*) DIRTY_BIN="${1#*=}"; shift ;;
    --meta-json) META_JSON="$2"; shift 2 ;;
    --meta-json=*) META_JSON="${1#*=}"; shift ;;
    *) echo "[ERROR] Unknown arg: $1"; exit 2 ;;
  esac
done

mkdir -p "$OUT_DIR"

python3 "$ROOT_DIR/scripts/corrupt_dataset.py" \
  --clean-out "$CLEAN_BIN" \
  --dirty-out "$DIRTY_BIN" \
  --meta-out "$META_JSON" \
  --points "$POINTS" \
  --dims "$DIMS" \
  --dirty-frac "$DIRTY_FRAC" \
  --seed "$SEED"

python3 - "$META_JSON" <<'PY'
import json, sys
m = json.load(open(sys.argv[1], 'r', encoding='utf-8'))
print('[PASS] dirty dataset generated')
print('points=%d dims=%d dirty_count=%d dirty_frac_actual=%.6f' % (
    m['points'], m['dims'], m['dirty_count'], m['dirty_frac_actual']))
print('distribution nan=%d null=%d outlier=%d' % (
    m['distribution']['nan'], m['distribution']['null'], m['distribution']['outlier']))
PY
