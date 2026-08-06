# PIM-Cleanser implementation guide

PIM-Cleanser validates and repairs floating-point records before the protected
SE-PIM workload consumes them. Supported invalid values include NaNs,
infinities, the configured missing-value sentinel, and public-threshold
outliers.

## Policies and schedules

- `zero`: replace invalid values with `0.0f`; intended for normalized features.
- `mean`: replace invalid values with the public feature mean; preserves feature
  aggregates better but can change correlations and clusters.
- `host-conditional` and `hybrid-sparse`: intentionally leaky controls whose
  write schedule depends on dirty density.
- `host-branchless`, `pim-oblivious`, and `hybrid-oblivious`: fixed-schedule
  candidates whose public transcript is checked across equal-shape inputs.

The fixed PIM path scans public feature positions and issues unconditional
writes. Data validity affects the selected value, not whether the public write
occurs.

## Host tests

After reconstructing the bundled source:

```bash
scripts/bootstrap_repo.sh
make -C IMPICA/workloads/kmeans_sepim_fs host-test
```

The tests compare cleaner output with independent references and check fixed
trace behavior. Native publication runs additionally require strict checkpoint,
dataset, executable, and source provenance; missing provenance fails closed.

## Recreate paper assets

```bash
python3 scripts/generate_publication_assets.py \
  --quality results/csv/publication_20260728T203351Z_quality.csv \
  --performance results/csv/publication_20260728T203351Z_performance.csv \
  --native results/csv/publication_20260728T213959Z_native.csv \
  --out-dir /tmp/pim-cleanser-generated
```

The clean release verifier compares every generated table, macro, and CSV with
`paper/generated/`. The calibrated performance runner also validates the
24-row native cleaning calibration CSV before producing modeled rows.

## Native reruns

`scripts/run_native_cleaning_gate.sh` measures isolated cleaning. The stricter
`scripts/run_native_e2e_gate.sh` binds direct TimingSimpleCPU execution to the
checkpoint, disk, guest workload, driver, datasets, source state, and independent
output oracle. It has no missing-provenance bypass in this release.

Only `scripts/promote_native_e2e_evidence.py` may create promoted native output,
and only after its provenance, transcript, timing, reference, assembly, and
regression gates pass.
