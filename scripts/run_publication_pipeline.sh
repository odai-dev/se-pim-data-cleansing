#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=scripts/_common.sh
source "$SCRIPT_DIR/_common.sh"

ORIG_ARGS=("$@")
STARTED_UTC=$(date -u +%Y-%m-%dT%H:%M:%SZ)
printf -v COMMAND_LINE '%q ' "$0" "${ORIG_ARGS[@]}"
MODE=full
RUN_ID="publication_$(date -u +%Y%m%dT%H%M%SZ)"
QUALITY_CSV=""
PERFORMANCE_CSV=""
NATIVE_CSV=""
CHECKPOINT_DIR=""
NATIVE_DATASET_ID=""
BUILD_PAPER=0
UCI_ARCHIVE="$ROOT_DIR/datasets/source/uci_har_official_c00b8030.zip"
UCI_SHA256="c00b803081a5c797cd5e4b83700a9810b38d53d9d84e01917e090e1fdbc81031"
IMAGE_NAME=${IMAGE_NAME:-sepim-impica@sha256:b4935cb7b1343fcaef5dcf19bb7644a7cfc3843522b81b0fbf04c741ad11c296}

usage() {
  cat <<'EOF'
Usage: scripts/run_publication_pipeline.sh [options]

Options:
  --quick                    Reduced smoke matrices (default: full matrices)
  --run-id ID                Unique output prefix
  --quality CSV              Reuse a validated quality summary CSV
  --performance CSV          Reuse a validated individual performance CSV
  --native CSV               Include a validated native gem5 CSV
  --checkpoint-dir DIR       Run the native gate and include its CSV
  --native-dataset-id ID     Dataset directory already frozen in that checkpoint
  --uci-archive ZIP          Pinned UCI HAR archive path
  --skip-paper               Generate evidence but do not invoke latexmk

When --quality or --performance is omitted, that matrix is regenerated.  A
native CSV is optional and is never synthesized. For the remaining
evaluation-report revision, omit both --native and --checkpoint-dir so generated
native fields are explicit placeholders and the paper publishes only calibrated
performance evidence.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --quick) MODE=quick; shift ;;
    --run-id) RUN_ID="$2"; shift 2 ;;
    --run-id=*) RUN_ID="${1#*=}"; shift ;;
    --quality) QUALITY_CSV="$2"; shift 2 ;;
    --quality=*) QUALITY_CSV="${1#*=}"; shift ;;
    --performance) PERFORMANCE_CSV="$2"; shift 2 ;;
    --performance=*) PERFORMANCE_CSV="${1#*=}"; shift ;;
    --native) NATIVE_CSV="$2"; shift 2 ;;
    --native=*) NATIVE_CSV="${1#*=}"; shift ;;
    --checkpoint-dir) CHECKPOINT_DIR="$2"; shift 2 ;;
    --checkpoint-dir=*) CHECKPOINT_DIR="${1#*=}"; shift ;;
    --native-dataset-id) NATIVE_DATASET_ID="$2"; shift 2 ;;
    --native-dataset-id=*) NATIVE_DATASET_ID="${1#*=}"; shift ;;
    --uci-archive) UCI_ARCHIVE="$2"; shift 2 ;;
    --uci-archive=*) UCI_ARCHIVE="${1#*=}"; shift ;;
    --skip-paper) BUILD_PAPER=0; shift ;;
    --help|-h) usage; exit 0 ;;
    *) echo "[ERROR] Unknown argument: $1"; usage; exit 2 ;;
  esac
done

RAW_DIR="$ROOT_DIR/results/raw/$RUN_ID"
if [[ -e "$RAW_DIR" ]]; then
  echo "[ERROR] Refusing to overwrite publication run: $RAW_DIR"
  exit 1
fi
mkdir "$RAW_DIR"
LOG_FILE=$(setup_log "$ROOT_DIR/logs/run" "$RUN_ID")
start_logging "$LOG_FILE"

echo "[INFO] Publication pipeline run_id=$RUN_ID mode=$MODE"
make -C "$ROOT_DIR/IMPICA/workloads/kmeans_sepim_fs" host-test

if [[ -z "$QUALITY_CSV" ]]; then
  if [[ ! -f "$UCI_ARCHIVE" ]]; then
    "$SCRIPT_DIR/fetch_uci_har.sh"
  fi
  quality_id="${RUN_ID}_quality"
  quality_args=(
    "$SCRIPT_DIR/run_quality_matrix.py"
    --run-id "$quality_id"
    --uci-archive "$UCI_ARCHIVE"
    --uci-sha256 "$UCI_SHA256"
  )
  if [[ "$MODE" == quick ]]; then quality_args+=(--quick); fi
  python3 "${quality_args[@]}"
  QUALITY_CSV="$ROOT_DIR/results/csv/${quality_id}_summary.csv"
fi

if [[ -z "$PERFORMANCE_CSV" ]]; then
  performance_id="${RUN_ID}_performance"
  performance_args=("$SCRIPT_DIR/run_performance_matrix.py" --run-id "$performance_id")
  if [[ "$MODE" == quick ]]; then performance_args+=(--quick); fi
  python3 "${performance_args[@]}"
  PERFORMANCE_CSV="$ROOT_DIR/results/csv/${performance_id}.csv"
fi

if [[ -n "$CHECKPOINT_DIR" ]]; then
  if [[ -n "$NATIVE_CSV" ]]; then
    echo "[ERROR] Use either --native or --checkpoint-dir, not both"
    exit 2
  fi
  if [[ -z "$NATIVE_DATASET_ID" ]]; then
    echo "[ERROR] --checkpoint-dir requires --native-dataset-id"
    exit 2
  fi
  native_id="${RUN_ID}_native"
  native_args=(
    --checkpoint-dir "$CHECKPOINT_DIR"
    --run-id "$native_id"
    --dataset-id "$NATIVE_DATASET_ID"
    --dataset-generation-manifest "$ROOT_DIR/IMPICA/workloads/kmeans_sepim_fs/data/$NATIVE_DATASET_ID/dataset_generation_manifest.json"
    --reuse-datasets
    --skip-disk-prepare
    --checkpoint-index 2
    --workload kmeans
    --run-id publication_20260728T211551Z_native
    --workers 3
  )
  if [[ "$MODE" == quick ]]; then native_args+=(--quick); fi
  "$SCRIPT_DIR/run_native_e2e_gate.sh" "${native_args[@]}"
  NATIVE_CSV="$ROOT_DIR/results/csv/${native_id}.csv"
fi

for required in "$QUALITY_CSV" "$PERFORMANCE_CSV"; do
  if [[ ! -f "$required" ]]; then
    echo "[ERROR] Required evidence CSV does not exist: $required"
    exit 1
  fi
done
if [[ -n "$NATIVE_CSV" && ! -f "$NATIVE_CSV" ]]; then
  echo "[ERROR] Native CSV does not exist: $NATIVE_CSV"
  exit 1
fi

ASSEMBLY="$RAW_DIR/pim_cleaner.s"
AUDIT="$RAW_DIR/assembly_audit.json"
docker run --rm \
  -v "$ROOT_DIR:/workspace" -w /workspace "$IMAGE_NAME" \
  aarch64-linux-gnu-gcc -O2 -Wall -Wextra -std=gnu99 -fverbose-asm \
  -IIMPICA/pim_driver -S -o "/workspace/${ASSEMBLY#$ROOT_DIR/}" \
  IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c
python3 "$SCRIPT_DIR/audit_aarch64_cleaner.py" "$ASSEMBLY" --report "$AUDIT"

asset_args=(
  "$SCRIPT_DIR/generate_publication_assets.py"
  --quality "$QUALITY_CSV"
  --performance "$PERFORMANCE_CSV"
  --out-dir "$ROOT_DIR/paper/generated"
)
if [[ -n "$NATIVE_CSV" ]]; then asset_args+=(--native "$NATIVE_CSV"); fi
python3 "${asset_args[@]}"

# Paper manuscripts are maintained directly as static DOCX and PDF artifacts.

python3 - "$RAW_DIR/manifest.json" "$RUN_ID" "$MODE" "$QUALITY_CSV" \
  "$PERFORMANCE_CSV" "$NATIVE_CSV" "$AUDIT" "$BUILD_PAPER" \
  "$STARTED_UTC" "$COMMAND_LINE" "$IMAGE_NAME" "$CHECKPOINT_DIR" <<'PY'
import datetime, hashlib, json, pathlib, subprocess, sys
(manifest, run_id, mode, quality, performance, native, audit, build_paper,
 started, command, image, checkpoint) = sys.argv[1:]
paths = [pathlib.Path(quality), pathlib.Path(performance), pathlib.Path(audit)]
if native:
    paths.append(pathlib.Path(native))

def git_value(repo, *args):
    result = subprocess.run(
        ["git", *args], cwd=repo, text=True, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL
    )
    return result.stdout.strip() if result.returncode == 0 else "unavailable"

digest = hashlib.sha256()
root = pathlib.Path.cwd()
for repo in (root, root / "IMPICA"):
    for args in (("diff", "--binary"), ("status", "--short")):
        result = subprocess.run(
            ["git", *args], cwd=repo, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL
        )
        digest.update(str(repo).encode())
        digest.update(result.stdout)

def display_path(path):
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path)

source_paths = set()
for directory in (root / "scripts",):
    source_paths.update(path for path in directory.rglob("*") if path.is_file())
for directory in (
    root / "IMPICA" / "gem5" / "src" / "dev" / "arm",
    root / "IMPICA" / "pim_driver",
    root / "IMPICA" / "workloads" / "kmeans_sepim_fs",
):
    source_paths.update(
        path for path in directory.rglob("*")
        if path.is_file() and path.suffix in {".c", ".cc", ".h", ".hh", ".py", ".sh", ".S"}
    )
for path in (
    root / ".gitignore", root / "README.md", root / "README_CLEANING.md",
    root / "paper" / "se_pim_data_cleansing_paper.pdf",
    root / "paper" / "se_pim_data_cleansing_paper.docx",
    root / "IMPICA" / "gem5" / "src" / "mem" / "abstract_mem.cc",
    root / "IMPICA" / "gem5" / "configs" / "common" / "FSConfig.py",
    root / "IMPICA" / "workloads" / "kmeans_sepim_fs" / "Makefile",
):
    if path.is_file():
        source_paths.add(path)
source_tree = hashlib.sha256()
for path in sorted(source_paths):
    source_tree.update(display_path(path).encode())
    source_tree.update(b"\0")
    source_tree.update(path.read_bytes())
payload = {
    "schema_version": 1,
    "run_id": run_id,
    "started_utc": started,
    "finished_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "command": command.strip(),
    "mode": mode,
    "paper_built": build_paper == "1",
    "top_commit": git_value(pathlib.Path.cwd(), "rev-parse", "HEAD"),
    "impica_commit": git_value(pathlib.Path.cwd() / "IMPICA", "rev-parse", "HEAD"),
    "source_diff_digest": digest.hexdigest(),
    "source_tree_sha256": source_tree.hexdigest(),
    "source_file_count": len(source_paths),
    "docker_image": image,
    "checkpoint": checkpoint or None,
    "inputs": {display_path(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths},
}
paper = pathlib.Path("output/pdf/se_pim_data_cleansing_paper.pdf")
if payload["paper_built"]:
    payload["paper"] = {
        "path": str(paper),
        "bytes": paper.stat().st_size,
        "sha256": hashlib.sha256(paper.read_bytes()).hexdigest(),
    }
pathlib.Path(manifest).write_text(json.dumps(payload, indent=2) + "\n")
PY

echo "[PASS] Publication pipeline completed: $RUN_ID"
