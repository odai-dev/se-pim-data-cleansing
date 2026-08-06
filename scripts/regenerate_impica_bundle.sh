#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=scripts/_common.sh
source "$SCRIPT_DIR/_common.sh"

IMPICA_GIT_DIR=${IMPICA_GIT_DIR:-"$ROOT_DIR/IMPICA"}
IMPICA_SOURCE_REF=${IMPICA_SOURCE_REF:-f8a18cd2677256b4b0e4ecd5cf547d033b268953}
ARCHIVE="$ROOT_DIR/impica-source.tar.gz"
PARTS_DIR="$ROOT_DIR/impica-parts"
MANIFEST="$PARTS_DIR/manifest.json"
PART_PREFIX="$PARTS_DIR/impica-source.tar.gz.part-"
STAGE=$(mktemp -d /tmp/pim-cleanser-impica.XXXXXX)
trap 'rm -rf "$STAGE"' EXIT

if [[ ! -d "$IMPICA_GIT_DIR" ]]; then
  echo "[ERROR] IMPICA_GIT_DIR is not a directory: $IMPICA_GIT_DIR"
  exit 1
fi
resolved_commit=$(git -C "$IMPICA_GIT_DIR" rev-parse "${IMPICA_SOURCE_REF}^{commit}")
if [[ "$resolved_commit" != "f8a18cd2677256b4b0e4ecd5cf547d033b268953" ]]; then
  echo "[ERROR] Ref resolves to $resolved_commit, expected the July 29 evidence commit"
  exit 1
fi

echo "[INFO] Exporting exact IMPICA evidence commit $resolved_commit"
git -C "$IMPICA_GIT_DIR" archive --format=tar --prefix=IMPICA/ "$resolved_commit" \
  | tar -xf - -C "$STAGE"

# Keep source and build recipes, but remove checked-in products and generated inputs.
rm -rf \
  "$STAGE/IMPICA/gem5/build" \
  "$STAGE/IMPICA/gem5/.hg" \
  "$STAGE/IMPICA/linux-aarch64-gem5-20140821" \
  "$STAGE/IMPICA/workloads/btree/input_file.c" \
  "$STAGE/IMPICA/workloads/btree/obj" \
  "$STAGE/IMPICA/workloads/hashtable/input.c" \
  "$STAGE/IMPICA/workloads/hashtable/input_part.h" \
  "$STAGE/IMPICA/workloads/hashtable/input_fast.c" \
  "$STAGE/IMPICA/workloads/kmeans_sepim_fs/data" \
  "$STAGE/IMPICA/workloads/hashtable/hashtable" \
  "$STAGE/IMPICA/workloads/sepim_cmd/sepim_cmd" \
  "$STAGE/IMPICA/workloads/kmeans_sepim_fs/kmeans_sepim_fs" \
  "$STAGE/IMPICA/workloads/kmeans_sepim_fs/quality_eval" \
  "$STAGE/IMPICA/workloads/kmeans_sepim_fs/tests/test_cleaner" \
  "$STAGE/IMPICA/workloads/kmeans_sepim_fs/tests/test_security_trace" \
  "$STAGE/IMPICA/workloads/controlled_access_bench_fs/controlled_access_bench_fs" \
  "$STAGE/IMPICA/workloads/dma_benchmark_fs/dma_benchmark_fs" \
  "$STAGE/IMPICA/workloads/trace_lookup_cpu/trace_lookup_cpu" \
  "$STAGE/IMPICA/workloads/trace_lookup_sepim/trace_lookup_sepim"
find "$STAGE/IMPICA" -type f \
  \( -name '*.pyc' -o -name '*.pyo' -o -name '*.o' -o -name '*.ko' \
     -o -name '*.mod.c' -o -name '*.cmd' -o -name 'Module.symvers' \
     -o -name 'modules.order' \) -delete
find "$STAGE/IMPICA" -type d \
  \( -name '__pycache__' -o -name '.tmp_versions' \) -empty -delete

tmp_archive="$STAGE/impica-source.tar.gz"
tar --sort=name --mtime='UTC 2026-07-29' --owner=0 --group=0 --numeric-owner \
  -czf "$tmp_archive" -C "$STAGE" IMPICA
cp "$tmp_archive" "$ARCHIVE"

mkdir -p "$PARTS_DIR"
find "$PARTS_DIR" -maxdepth 1 -type f -name 'impica-source.tar.gz.part-*' -delete
split -b 512K "$ARCHIVE" "$PART_PREFIX"

python3 - "$ARCHIVE" "$PARTS_DIR" "$MANIFEST" "$resolved_commit" <<'PY'
import hashlib
import json
import pathlib
import sys

archive, parts_dir, manifest = map(pathlib.Path, sys.argv[1:4])
source_commit = sys.argv[4]

def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()

parts = sorted(parts_dir.glob("impica-source.tar.gz.part-*"))
payload = {
    "schema_version": 3,
    "archive_name": archive.name,
    "archive_bytes": archive.stat().st_size,
    "archive_sha256": sha256(archive),
    "expected_part_count": len(parts),
    "part_bytes": 512 * 1024,
    "assembled_extract_dir": "IMPICA",
    "source_repository_commit": source_commit,
    "source_repository_tracked_diff_sha256": hashlib.sha256(b"").hexdigest(),
    "source_only_exclusions": [
        "repository history", "gem5/build", "unchanged Linux source",
        "generated datasets", "compiler outputs", "checked-in executables",
        "Python bytecode",
    ],
    "evidence_source_hashes": {
        "gem5/src/dev/arm/pimDevice_hashtable.cc": "45ca7f79de995b14acb8a228ff55efa19d4420a62242c48acb877dc1af0ee6e9",
        "workloads/kmeans_sepim_fs/kmeans_sepim_fs.c": "56dd8fbdef8a2ac6f8941bbcec13337605941c6edd829aa13cca58ab7935ca75",
        "workloads/kmeans_sepim_fs/pim_cleaner.c": "c4c53e05ffd277d173839530b25f309f4d75dcb42bf81a87591281bf18866285",
        "workloads/kmeans_sepim_fs/pim_cleaner.h": "793fa1161d1689ef78cf24f0410a03003eed7ad8e70274a421d770f0f4ac9083",
    },
    "parts": [
        {"file": path.name, "bytes": path.stat().st_size, "sha256": sha256(path)}
        for path in parts
    ],
}
manifest.write_text(json.dumps(payload, indent=2) + "\n")
print("[INFO] archive_sha256=%s parts=%d" % (payload["archive_sha256"], len(parts)))
PY

"$SCRIPT_DIR/check_impica_bundle.sh"
echo "[PASS] Exact IMPICA evidence bundle regenerated and verified"
