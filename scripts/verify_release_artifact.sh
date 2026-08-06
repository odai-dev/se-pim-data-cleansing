#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
ROOT_DIR=$(cd "$SCRIPT_DIR/.." && pwd)
INCLUDE_NATIVE=1
POSITIONAL=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-native) INCLUDE_NATIVE=0; shift ;;
    --help|-h)
      echo "Usage: scripts/verify_release_artifact.sh [--no-native] [archive] [report]"
      exit 0
      ;;
    *) POSITIONAL+=("$1"); shift ;;
  esac
done
set -- "${POSITIONAL[@]}"

ARCHIVE="${1:-$ROOT_DIR/output/artifact/pim-cleanser-publication-artifact.tar.gz}"
REPORT="${2:-$ROOT_DIR/output/artifact/clean-reproduction.json}"
if [[ "$ARCHIVE" != /* ]]; then ARCHIVE="$PWD/$ARCHIVE"; fi
if [[ "$REPORT" != /* ]]; then REPORT="$PWD/$REPORT"; fi
EXTRACT=$(mktemp -d /tmp/pim-cleanser-verify.XXXXXX)
trap 'rm -rf "$EXTRACT"' EXIT

for tool in python3 sha256sum tar latexmk pdfinfo pdftoppm pdftotext rg soffice; do
  command -v "$tool" >/dev/null || { echo "[ERROR] Missing required tool: $tool"; exit 1; }
done
python3 -c 'import docx, latex2mathml' >/dev/null 2>&1 || {
  echo "[ERROR] Missing Python dependencies; install requirements-reproduction.txt"
  exit 1
}
[[ -f "$ARCHIVE" ]] || { echo "[ERROR] Release archive not found: $ARCHIVE"; exit 1; }
mkdir -p "$(dirname "$REPORT")"
archive_sha=$(sha256sum "$ARCHIVE" | awk '{print $1}')
tar -xzf "$ARCHIVE" -C "$EXTRACT"
REPRO="$EXTRACT/pim-cleanser-artifact"

python3 - "$REPRO" "$INCLUDE_NATIVE" <<'PY'
import hashlib
import json
import pathlib
import sys
import zipfile

root = pathlib.Path(sys.argv[1])
include_native = sys.argv[2] == "1"
release = json.loads((root / "RELEASE-MANIFEST.json").read_text())
if release.get("native_evidence_included") is not include_native:
    raise SystemExit("release native mode does not match verifier mode")
expected = release["files"]
actual = {
    p.relative_to(root).as_posix(): {
        "bytes": p.stat().st_size,
        "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
    }
    for p in root.rglob("*")
    if p.is_file() and p.name != "RELEASE-MANIFEST.json"
}
if actual != expected:
    missing = sorted(set(expected) - set(actual))
    extra = sorted(set(actual) - set(expected))
    changed = sorted(k for k in set(actual) & set(expected) if actual[k] != expected[k])
    raise SystemExit(
        f"release manifest mismatch missing={missing} extra={extra} changed={changed}"
    )

submission = json.loads((root / "paper/SUBMISSION-MANIFEST.json").read_text())
for relative, record in submission["files"].items():
    path = root / relative
    if path.stat().st_size != record["bytes"]:
        raise SystemExit(f"submitted file size mismatch: {relative}")
    if hashlib.sha256(path.read_bytes()).hexdigest() != record["sha256"]:
        raise SystemExit(f"submitted file hash mismatch: {relative}")
with zipfile.ZipFile(root / "output/doc/se_pim_data_cleansing_paper.docx") as archive:
    if "word/document.xml" not in archive.namelist():
        raise SystemExit("submitted DOCX is invalid")

evidence = json.loads((root / "results/EVIDENCE-MANIFEST.json").read_text())
classes = evidence["evidence_classes"]
required = ["quality", "calibrated_performance", "native_cleaning_calibration"]
if include_native:
    required += ["direct_native_paper_input", "promoted_native"]
for name in required:
    record = classes[name]
    if "csv" in record:
        path = root / record["csv"]
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != record["csv_sha256"]:
            raise SystemExit(f"evidence CSV hash mismatch: {name}")
if include_native:
    promoted = classes["promoted_native"]
    path = root / promoted["directory"] / "manifest.json"
    if hashlib.sha256(path.read_bytes()).hexdigest() != promoted["manifest_sha256"]:
        raise SystemExit("promoted native manifest hash mismatch")
print(f"[PASS] release files={len(actual)} submitted=3 evidence_classes={len(required)}")
PY

cd "$REPRO"
scripts/check_impica_bundle.sh
scripts/bootstrap_repo.sh
make -C IMPICA/workloads/kmeans_sepim_fs host-test
python3 -m unittest discover -s scripts/tests -p 'test_*.py'
python3 -m unittest discover -s tests -p 'test_*.py'

if [[ "$INCLUDE_NATIVE" == 1 ]]; then
  promotion_root="$EXTRACT/reproduced-promotion"
  python3 scripts/promote_native_e2e_evidence.py \
    --fused-manifest results/raw/publication_e2e_fused_final_strict/manifest.json \
    --regression-manifest results/raw/regression_strict_20260727T183538Z/regression_manifest.json \
    --assembly-audit results/raw/publication_e2e_fused_final_strict_paper/assembly_audit.json \
    --run-id reproduced-promoted-native \
    --out-root "$promotion_root"
  cmp results/promoted/native_e2e_strict_promoted_20260727T222512Z/individual.csv \
    "$promotion_root/reproduced-promoted-native/individual.csv"
  cmp results/promoted/native_e2e_strict_promoted_20260727T222512Z/summary.csv \
    "$promotion_root/reproduced-promoted-native/summary.csv"
fi

GEN="$EXTRACT/generated"
asset_args=(
  scripts/generate_publication_assets.py
  --quality results/csv/publication_20260728T203351Z_quality.csv
  --performance results/csv/publication_20260728T203351Z_performance.csv
  --evidence-root "$REPRO"
  --out-dir "$GEN"
)
if [[ "$INCLUDE_NATIVE" == 1 ]]; then
  asset_args+=(--native results/csv/publication_20260728T213959Z_native.csv)
fi
python3 "${asset_args[@]}"
asset_names=(
  datasets_table.tex hybrid_block.csv leakage.csv matrix_table.tex
  mode_evidence_table.tex overhead.csv phase_breakdown.csv policy_tradeoff.csv
  quality_cross_table.tex quality_table.tex quality_uci_mean.csv
)
if [[ "$INCLUDE_NATIVE" == 1 ]]; then
  asset_names+=(native_table.tex numbers.tex)
fi
for name in "${asset_names[@]}"; do cmp "paper/generated/$name" "$GEN/$name"; done

mkdir -p "$EXTRACT/pdf" "$EXTRACT/pdf-pages" "$EXTRACT/docx" "$EXTRACT/docx-pages"
latexmk -pdf -interaction=nonstopmode -halt-on-error -outdir="$EXTRACT/pdf" \
  se_pim_data_cleansing_paper.tex >/dev/null
PDF="$EXTRACT/pdf/se_pim_data_cleansing_paper.pdf"
LOG="$EXTRACT/pdf/se_pim_data_cleansing_paper.log"
if rg -n 'Overfull|undefined references|multiply defined' "$LOG"; then
  echo "[ERROR] Reproduced paper log contains unresolved or overfull content"
  exit 1
fi
pages=$(pdfinfo "$PDF" | awk '/^Pages:/ {print $2}')
[[ "$pages" == 7 ]] || { echo "[ERROR] Reproduced PDF has $pages pages, expected 7"; exit 1; }
pdf_text="$EXTRACT/pdf/reproduced.txt"
pdftotext "$PDF" "$pdf_text"
rg -q '0\.048495%' "$pdf_text"
rg -q '0\.117989%' "$pdf_text"
rg -q 'wafaa2026/se-pim-data-cleansing' "$pdf_text"
pdftoppm -png -r 100 "$PDF" "$EXTRACT/pdf-pages/page" >/dev/null 2>&1
[[ $(find "$EXTRACT/pdf-pages" -maxdepth 1 -name 'page-*.png' | wc -l) == 7 ]]

python3 scripts/generate_paper_docx.py --output "$EXTRACT/docx/reproduced.docx"
python3 - output/doc/se_pim_data_cleansing_paper.docx "$EXTRACT/docx/reproduced.docx" <<'PY'
from docx import Document
import sys

def content(path):
    doc = Document(path)
    paragraphs = [p.text for p in doc.paragraphs]
    tables = [
        [[cell.text for cell in row.cells] for row in table.rows]
        for table in doc.tables
    ]
    return paragraphs, tables, len(doc.inline_shapes)

submitted = content(sys.argv[1])
reproduced = content(sys.argv[2])
if submitted != reproduced:
    raise SystemExit("reproduced DOCX structured content differs from submission")
print(f"[PASS] reproduced DOCX paragraphs={len(submitted[0])} tables={len(submitted[1])} figures={submitted[2]}")
PY
profile=$(mktemp -d /tmp/pim-cleanser-lo.XXXXXX)
soffice -env:UserInstallation="file://$profile" --headless --convert-to pdf \
  --outdir "$EXTRACT/docx" "$EXTRACT/docx/reproduced.docx" >/dev/null
docx_pdf="$EXTRACT/docx/reproduced.pdf"
docx_pages=$(pdfinfo "$docx_pdf" | awk '/^Pages:/ {print $2}')
[[ "$docx_pages" == 8 ]] || { echo "[ERROR] Reproduced DOCX renders to $docx_pages pages, expected 8"; exit 1; }
pdftoppm -png -r 100 "$docx_pdf" "$EXTRACT/docx-pages/page" >/dev/null 2>&1
[[ $(find "$EXTRACT/docx-pages" -maxdepth 1 -name 'page-*.png' | wc -l) == 8 ]]
rm -rf "$profile"

python3 - "$REPORT" "$archive_sha" "$PDF" "$INCLUDE_NATIVE" <<'PY'
import datetime
import hashlib
import json
import pathlib
import sys

report = pathlib.Path(sys.argv[1])
pdf = pathlib.Path(sys.argv[3])
include_native = sys.argv[4] == "1"
checks = {
    "release_manifest": "pass",
    "submission_manifest": "pass",
    "evidence_manifest": "pass",
    "impica_bundle_and_source_hashes": "pass",
    "host_tests": "pass",
    "python_tests": "pass",
    "publication_assets_byte_equal": "pass",
    "paper_compile_and_render_7_pages": "pass",
    "docx_structural_rebuild_and_render_8_pages": "pass",
}
checks["native_promotion_revalidation"] = "pass" if include_native else "not included"
payload = {
    "schema_version": 2,
    "status": "pass",
    "native_evidence_included": include_native,
    "finished_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "archive_sha256": sys.argv[2],
    "reproduced_pdf_sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(),
    "checks": checks,
}
report.write_text(json.dumps(payload, indent=2) + "\n")
print(f"[PASS] clean reproduction report: {report}")
PY
