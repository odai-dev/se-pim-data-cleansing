# Reproducing the July 29 paper artifact

## 1. Verify immutable inputs

```bash
(cd output/artifact && sha256sum -c pim-cleanser-publication-artifact.tar.gz.sha256)
scripts/verify_release_artifact.sh
```

The verifier checks `paper/SUBMISSION-MANIFEST.json`,
`results/EVIDENCE-MANIFEST.json`, the per-run manifests, and the source-bundle
manifest before running any derived checks.

## 2. Reconstruct source and run host checks

```bash
scripts/bootstrap_repo.sh
make -C IMPICA/workloads/kmeans_sepim_fs host-test
python3 -m unittest discover -s scripts/tests -p 'test_*.py'
python3 -m unittest discover -s tests -p 'test_*.py'
```

The reconstructed source is bound to IMPICA commit `f8a18cd2677256b4b0e4ecd5cf547d033b268953`.

## 3. Regenerate paper inputs

```bash
python3 scripts/generate_publication_assets.py \
  --quality results/csv/publication_20260728T203351Z_quality.csv \
  --performance results/csv/publication_20260728T203351Z_performance.csv \
  --native results/csv/publication_20260728T213959Z_native.csv \
  --out-dir /tmp/pim-cleanser-generated
```

Compare the generated directory with `paper/generated`, excluding only the
manifest generation timestamp.

## 4. Build the manuscripts

```bash
python3 -m pip install -r requirements-reproduction.txt
latexmk -pdf -interaction=nonstopmode -halt-on-error \
  se_pim_data_cleansing_paper.tex
python3 scripts/generate_paper_docx.py --output /tmp/pim-cleanser.docx
```

The submitted PDF and DOCX remain immutable reference artifacts. Rebuilt PDFs
can differ bytewise because PDF metadata contains build time; verification uses
source/input hashes, compilation diagnostics, page count, extracted claims, and
rendered pages.

## 5. Native boundary

The packaged release does not redistribute the ARM disk image, kernel, gem5
binary, or checkpoints. Their hashes and provenance are retained in the native
manifests. A direct native rerun requires reconstructing those dependencies and
must pass the exact 1000-tick clock probe and strict checkpoint provenance gate.

Do not use post-hoc CSV edits, provenance hash patching, fallback clock values,
or missing-provenance overrides as publication evidence.
