# Hybrid Data Cleaning under SE-PIM

This extension adds dirty-data cleaning experiments to the replicated SE-PIM k-means flow.

## What It Adds
- Reproducible dataset corruption (10% dirty by default): NaN, null sentinel, outliers.
- Modular cleaner code:
  - `IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.h`
  - `IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c`
  - `IMPICA/workloads/kmeans_sepim_fs/host_cleaner.h`
  - `IMPICA/workloads/kmeans_sepim_fs/host_cleaner.c`
- Extended k-means workload flags:
  - `--cleaning=off|pim|hybrid`
  - `--corruption=<frac> --seed=<N>`
  - `--block-size=<bytes>`
  - `--dummy-semantics=0|1`

## Dataset Format
Binary file (`.bin`):
- Header: 8 x `uint32_t` (magic/version/points/dims/seed/reserved)
- Body: contiguous `float32` points (`points * dims`)

Dirty-data sidecar (`.meta.json`) stores exact dirty indices by type.

## Generate Dirty Dataset
```bash
scripts/make_dirty_dataset.sh --dirty-frac 0.10 --seed 7 --points 131072 --dims 8
```
Outputs under `IMPICA/workloads/kmeans_sepim_fs/data/`:
- `kmeans_clean.bin`
- `kmeans_dirty_10pct.bin`
- `kmeans_dirty_10pct.meta.json`

## Run Experiments
PIM-only cleaning run:
```bash
scripts/run_kmeans_cleaning_pim.sh --full
```

Hybrid cleaning run with block sweep:
```bash
scripts/run_kmeans_cleaning_hybrid.sh --full
```

Optional traffic trace during hybrid run:
```bash
scripts/run_kmeans_cleaning_hybrid.sh --full --trace
```

Runner behavior note:
- If `aarch64-linux-gnu-gcc` is missing on host, both run scripts automatically re-exec inside `sepim-impica:ubuntu18`.

## Outputs
- Raw stats:
  - `results/raw/cleaning_*.stats`
- CSV:
  - `results/csv/cleaning_pim.csv`
  - `results/csv/cleaning_hybrid.csv`
- Plots:
  - `results/plots/cleaning_pim.png`
  - `results/plots/cleaning_hybrid.png`

## Security / Lockdown Behavior
- `LOCK_MEM` is issued before scan/clean/compute phases.
- In hybrid mode, host-side cleaning fetches and writes dirty points only through `ACCESS_DATA`.
- No direct host mapping of locked bank memory is used by the cleaning path.
- `UNLOCK_MEM` is issued only after pipeline completion.
- `--dummy-semantics=1` adds dummy reads (including post-write dummy reads) to emulate ORAM-like traffic shaping.

## Key Counters and Metrics
From cleaning CSV columns:
- Runtime breakdown:
  - `scan_sec`, `clean_sec`, `kmeans_sec`, `total_sec`
  - `scan_pct`, `clean_pct`, `kmeans_pct`
- Hybrid controlled-access stats:
  - `access_reads`, `access_writes`, `access_dummy_reads`
  - `access_bytes`, `avg_block_bytes`, `access_mbps`
- Data quality impact:
  - `dirty_found`, `dirty_cleaned`, `dirty_remaining`, `quality_score`

From gem5 stats (optional cross-check in run outdir `stats.txt`):
- `sim_ticks`, `sim_seconds`, `host_seconds`
- Memory transaction counters (if enabled by config/debug flags)

## Notes
- This extension keeps existing Fig.11 replication behavior when no `--cleaning` flag is used.
- Cleaning rules:
  - NaN -> impute `0`
  - Null sentinel row -> zero vector
  - Outlier -> clamp to `[-threshold, +threshold]`

## Latest Full-Run Snapshot (2026-03-02)
- Run ids:
  - `cleaning_pim_full_20260301_203153`
  - `cleaning_hybrid_full_20260301_205927`
- Baseline clean total: `17.694336 s`
- Dirty no-clean total: `17.694336 s`, quality score `0.900002`
- PIM cleaning total: `17.704647 s` (`+0.0583%` vs clean baseline), dirty remaining `0`
- Hybrid totals by block size:
  - `1KB`: `18.424311 s`, `10.693 MB/s`
  - `4KB`: `17.899298 s`, `40.979 MB/s`
  - `16KB`: `17.761060 s`, `140.388 MB/s`
  - `64KB`: `17.726500 s`, `356.743 MB/s`
  - `128KB`: `17.720740 s`, `480.044 MB/s`
