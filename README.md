# PIM-Cleanser IEEE reproduction artifact

This repository is the public artifact for **PIM-Cleanser: In-Memory
Acceleration of Data-Intensive Confidential Data Sanitization**.

## Submitted paper

The IEEE conference submission was finalized on **29 July 2026**. The immutable
submission pair is:

- `se_pim_data_cleansing_paper.pdf` - seven-page IEEE PDF, SHA-256
  `f4b09368636d1a68992754b011dd9101133292a7512dc089b3fd56c3741e254f`.
- `output/doc/se_pim_data_cleansing_paper.docx` - Word manuscript, SHA-256
  `22f5dc370c647595b23e72b20ae3ad958feb7b6e6a362d5ecdc7ae55fc244a59`.

`paper/SUBMISSION-MANIFEST.json` records the complete file metadata. The
15 July surgical revision is an earlier draft and is not part of this release.

## Evidence boundary

The paper deliberately separates three evidence classes:

| Evidence | What it supports | Status |
|---|---|---|
| Host-native quality matrix | Repair quality on synthetic data and UCI HAR | 270 canonical rows |
| Functional calibrated matrix | The reported `0.048495%` zero and `0.117989%` mean estimated overheads | 18,144 analytical rows, not native gem5 ticks |
| Native gem5 runs | Cleaning calibration and fixed public transcript checks | Exact candidate input plus a separately promoted strict bundle |

The paper makes **no direct native end-to-end overhead claim**. The exact
36-row native CSV used while generating paper assets retains its original
`candidate` label. The independently promoted native bundle is published
separately with its regression and assembly evidence. See
`results/EVIDENCE-MANIFEST.json` for the complete mapping and checksums.

## Verify the release

Required for the packaged verification path: Bash, Python 3, a C compiler,
`latexmk`, an IEEEtran-capable TeX installation, Poppler, and standard archive
tools.

```bash
python3 -m pip install -r requirements-reproduction.txt
scripts/check_impica_bundle.sh
python3 -m unittest discover -s scripts/tests -p 'test_*.py'
python3 -m unittest discover -s tests -p 'test_*.py'
scripts/build_release_artifact.sh
scripts/verify_release_artifact.sh
```

The verifier works from a fresh extraction, reconstructs the exact source-only
IMPICA bundle, runs host tests, verifies all evidence hashes, regenerates paper
assets byte-for-byte, compiles and renders the paper, and writes
`output/artifact/clean-reproduction.json`.

Use `scripts/build_release_artifact.sh --no-native` only for a smaller
calibrated-only derivative. It is not the full IEEE release.

## Source provenance

The source-only IMPICA bundle is exported from nested repository commit
`f8a18cd2677256b4b0e4ecd5cf547d033b268953`. Its manifest binds the key cleaner,
workload, and gem5 device files used by the July 29 evidence. Build products,
checkpoints, disk images, raw generated datasets, and repository history are not
redistributed.

The full native rerun additionally needs the pinned ARM full-system image,
kernel, rebuilt gem5 binary, and provenance-bound checkpoints described in the
recorded manifests. The release verifies those immutable records but does not
pretend that omitted multi-gigabyte dependencies are present.

## Repository layout

```text
impica-parts/                 exact source-only IMPICA bundle and manifest
paper/generated/              generated tables, macros, and plot data
paper/docx_assets/            submitted Word manuscript figure assets
results/csv/                  canonical paper and promoted-evidence rows
results/raw/                  compact run manifests and validations
results/promoted/             strict promoted native bundle
scripts/                      experiment, generation, promotion, and verification tools
tests/                        promotion and provenance tests
```

## Security scope

The evaluated property concerns a passive observer of the host-PIM interface
and external memory traffic under the stated SE-PIM assumptions. It does not
cover PIM-core power, electromagnetic leakage, internal caches/branches,
physical attacks, compromised measured code, or production hardware.

## Citation and license

Citation metadata is provided in `CITATION.cff`. Code and artifact glue are
released under the repository's MIT license; upstream components retain their
own licenses.
