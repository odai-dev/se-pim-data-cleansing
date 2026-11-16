#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=scripts/_common.sh
source "$SCRIPT_DIR/_common.sh"

INCLUDE_NATIVE=1
while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-native) INCLUDE_NATIVE=0; shift ;;
    --help|-h)
      echo "Usage: scripts/build_release_artifact.sh [--no-native]"
      echo "The default builds the complete July 29 IEEE artifact."
      exit 0
      ;;
    *) echo "[ERROR] Unknown argument: $1"; exit 2 ;;
  esac
done

QUALITY_CSV="results/csv/publication_20260728T203351Z_quality.csv"
PERFORMANCE_CSV="results/csv/publication_20260728T203351Z_performance.csv"
CALIBRATION_CSV="results/csv/native_clean_pipeline2c_full_20260714.csv"
NATIVE_CSV="results/csv/publication_20260728T213959Z_native.csv"
OUTPUT_DIR="$ROOT_DIR/output/artifact"
ARCHIVE="$OUTPUT_DIR/pim-cleanser-publication-artifact.tar.gz"
CHECKSUM="$ARCHIVE.sha256"
STAGE=$(mktemp -d /tmp/pim-cleanser-release.XXXXXX)
PAYLOAD="$STAGE/pim-cleanser-artifact"
trap 'rm -rf "$STAGE"' EXIT

core_paths=(
  README.md README_CLEANING.md LICENSE CITATION.cff CONTRIBUTING.md
  scripts tests tools datasets/source/.gitkeep
  paper impica-parts results/EVIDENCE-MANIFEST.json
  "$QUALITY_CSV" "$PERFORMANCE_CSV" "$CALIBRATION_CSV"
  results/raw/publication_20260728T203351Z_quality
  results/raw/publication_20260728T203351Z_performance
  results/raw/native_clean_pipeline2c_full_20260714
)
native_paths=(
  "$NATIVE_CSV"
  results/csv/publication_20260728T213959Z_native_paired.csv
  results/csv/publication_e2e_fused_final_strict_native.csv
  results/csv/publication_e2e_fused_final_strict_paired.csv
  results/raw/publication_20260728T211551Z_native
  results/raw/publication_e2e_fused_final_strict
  results/raw/publication_e2e_fused_final_strict_paper
  results/raw/regression_strict_20260727T183538Z
  results/promoted/native_e2e_strict_promoted_20260727T222512Z
)

required=("${core_paths[@]}")
if [[ "$INCLUDE_NATIVE" == 1 ]]; then required+=("${native_paths[@]}"); fi
for relative in "${required[@]}"; do
  if [[ ! -e "$ROOT_DIR/$relative" ]]; then
    echo "[ERROR] Release input missing: $relative"
    exit 1
  fi
done

mkdir -p "$PAYLOAD" "$OUTPUT_DIR"
paths=("${core_paths[@]}")
if [[ "$INCLUDE_NATIVE" == 1 ]]; then paths+=("${native_paths[@]}"); fi
(
  cd "$ROOT_DIR"
  tar --exclude='__pycache__' --exclude='*.pyc' --exclude='*.pyo' \
      --exclude='*.aux' --exclude='*.log' --exclude='*.fls' \
      --exclude='*.fdb_latexmk' --exclude='output/artifact' \
      -cf - "${paths[@]}"
) | tar -xf - -C "$PAYLOAD"

python3 - "$PAYLOAD" "$INCLUDE_NATIVE" "$QUALITY_CSV" "$PERFORMANCE_CSV" \
  "$CALIBRATION_CSV" "$NATIVE_CSV" <<'PY'
import hashlib
import json
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
include_native = sys.argv[2] == "1"
files = {}
for path in sorted(p for p in root.rglob("*") if p.is_file()):
    relative = path.relative_to(root).as_posix()
    files[relative] = {
        "bytes": path.stat().st_size,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }
manifest = {
    "schema_version": 2,
    "artifact": "PIM-Cleanser July 29 IEEE reproduction artifact",
    "submission_date": "2026-07-29",
    "entry_point": "scripts/verify_release_artifact.sh",
    "native_evidence_included": include_native,
    "quality_csv": sys.argv[3],
    "performance_csv": sys.argv[4],
    "native_calibration_csv": sys.argv[5],
    "direct_native_csv": sys.argv[6] if include_native else None,
    "network_required_for_packaged_verification": False,
    "large_native_runtime_dependencies_redistributed": False,
    "source_commit": "f8a18cd2677256b4b0e4ecd5cf547d033b268953",
    "files": files,
}
(root / "RELEASE-MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n")
PY

tmp_archive="$OUTPUT_DIR/.pim-cleanser-publication-artifact.tar.gz.new"
tar --sort=name --mtime='UTC 2026-07-29' --owner=0 --group=0 --numeric-owner \
  -czf "$tmp_archive" -C "$STAGE" pim-cleanser-artifact
mv "$tmp_archive" "$ARCHIVE"
(
  cd "$OUTPUT_DIR"
  sha256sum "$(basename "$ARCHIVE")" > "$(basename "$CHECKSUM")"
)
echo "[PASS] Release archive: $ARCHIVE"
echo "[PASS] Release checksum: $CHECKSUM"
