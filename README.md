# PIM-Cleanser

**Secure, fixed-schedule data cleansing for confidential
Processing-in-Memory workloads.**

[![IEEE artifact](https://img.shields.io/badge/artifact-IEEE%20submission-blue)](https://github.com/wafaa2026/se-pim-data-cleansing/releases/tag/ieee-submission-2026-07-29)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

PIM-Cleanser extends the SE-PIM architecture with an in-memory sanitization
stage for data containing NaNs, missing-value sentinels, and outliers. Cleaning
happens inside the protected memory path before the main PIM workload runs,
avoiding a host-side pass over confidential records.

The key idea is simple: cleaning decisions may depend on secret data, but the
externally visible schedule does not. Fixed-schedule modes scan every public
record and feature and issue unconditional writes, so equal-public-shape inputs
produce the same modeled host-PIM trace.

## What this repository provides

- A PIM cleaning kernel with zero and per-feature mean imputation.
- Fixed-schedule PIM and hybrid cleaning modes, plus explicit leaky controls.
- Host tests for cleaning correctness, security traces, k-means integration,
  and fused zero-imputation semantics.
- Reproducible quality, calibrated-performance, and native gem5 evidence.
- The submitted IEEE paper, generated tables and figures, and a verified release
  archive.

## How it works

```text
Confidential dataset
        |
        v
Host locks the protected memory range
        |
        v
PIM-Cleanser scans, validates, and repairs records
using a schedule determined only by public parameters
        |
        v
The sanitized data feeds the PIM workload
        |
        v
The host receives the result and unlocks memory
```

PIM-Cleanser supports six evaluated modes:

| Mode | Behavior | Security role |
|---|---|---|
| `off` | No repair | Workload baseline |
| `host-conditional` | Writes only dirty records | Leakage control |
| `host-branchless` | Reads and writes all records | Fixed candidate |
| `pim-oblivious` | Fixed PIM scan and write schedule | Fixed candidate |
| `hybrid-sparse` | Transfers dirty-dependent blocks | Leakage control |
| `hybrid-oblivious` | Transfers all padded public blocks | Fixed candidate |

## Results at a glance

The evaluation covers balanced and heavy-tailed synthetic mixtures, UCI Human
Activity Recognition data, k-means, and feature-wise aggregation.

- Across 1,008 equal-public-shape groups, fixed candidates produced identical
  modeled observable traces; the leakage controls showed the expected
  corruption-dependent behavior.
- At 10% UCI HAR corruption, mean imputation reduced aggregation error from
  `0.0671` with zero repair to `0.0017`.
- For the selected 4 MiB, 32-feature, fixed-20-iteration k-means configuration,
  the calibrated model estimates `0.048495%` incremental overhead for zero
  imputation and `0.117989%` for mean imputation.

The overhead values are calibrated estimates anchored by isolated native gem5
cleaning measurements. Direct native runs and the separately promoted strict
native bundle are included as supporting evidence; the paper does not claim a
direct native end-to-end overhead measurement. The complete evidence mapping is
in [`results/EVIDENCE-MANIFEST.json`](results/EVIDENCE-MANIFEST.json).

## Quick start

The easiest way to reproduce the published artifact is to download the
[`ieee-submission-2026-07-29` release](https://github.com/wafaa2026/se-pim-data-cleansing/releases/tag/ieee-submission-2026-07-29).

From a clone or extracted release:

```bash
scripts/check_impica_bundle.sh
scripts/bootstrap_repo.sh
make -C IMPICA/workloads/kmeans_sepim_fs host-test
python3 -m unittest discover -s scripts/tests -p 'test_*.py'
python3 -m unittest discover -s tests -p 'test_*.py'
```

To build and verify the complete publication archive from a clean extraction:

```bash
scripts/build_release_artifact.sh
scripts/verify_release_artifact.sh
```

The verifier checks file hashes and provenance, reconstructs the source-only
IMPICA tree, runs the tests, reproduces the promoted native bundle and generated
publication assets, and writes `output/artifact/clean-reproduction.json`.

## Paper

**PIM-Cleanser: In-Memory Acceleration of Data-Intensive Confidential Data
Sanitization**

Wafaa M. AL-Madhaji, Odai M. Gubran, and Ibrahim Ahmed Al-Baltah.

- [Submitted IEEE PDF](paper/se_pim_data_cleansing_paper.pdf)
- [Submitted Word Manuscript](paper/se_pim_data_cleansing_paper.docx)
- [Submission manifest](paper/SUBMISSION-MANIFEST.json)
- [Citation metadata](CITATION.cff)

The camera-ready manuscript is maintained directly as verified DOCX and PDF
artifacts in `paper/`. Their SHA-256 values are recorded in the submission manifest.

## Repository layout

```text
impica-parts/       source-only IMPICA bundle and integrity manifest
paper/              submission metadata and generated paper inputs
results/csv/        canonical evaluation rows
results/raw/        run manifests, validations, provenance, and assembly audit
results/promoted/   independently promoted strict native evidence
scripts/            experiment, generation, and verification tools
tests/              promotion and provenance tests
```

## Security scope

The evaluated property concerns a passive observer of the host-PIM interface
and external memory traffic under the stated SE-PIM assumptions. PIM-core power
or electromagnetic leakage, internal microarchitectural behavior, physical
attacks, and compromised measured code are outside the evaluated scope.

## License

Repository code and artifact tooling are available under the [MIT License](LICENSE).
Bundled or referenced upstream components retain their own licenses.
