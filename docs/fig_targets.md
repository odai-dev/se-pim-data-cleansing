# Figure reproduction targets and acceptance bands

Source: `SE-PIM_In-Memory_Acceleration_of_Data-Intensive_Confidential_Computing-1.pdf` (Sections 7.1–7.3).

## Fig. 8 (bus-observable physical address trace)

Expected qualitative target:
- CPU-only enclave execution: lookup-dependent address pattern visible on bus (leakage).
- SE-PIM-assisted execution: bus traffic dominated by fixed command/parameter channels; lookup-dependent bank addresses not exposed.

Acceptance criterion:
- Side-by-side plots show clear separability as above; SE-PIM trace should not reveal lookup-index dependent in-bank accesses.

## Fig. 9 (AES-enabled DMA overhead)

Paper-reported targets:
- Average access-time overhead from AES-capable DMA: about `22.35%`.
- Maximum throughput (encrypted DMA): about `2.9 GB/s`.
- Baseline unencrypted DMA maximum throughput: about `3.53 GB/s`.

Practical acceptance band for reproduction:
- Average overhead within ±20% relative of 22.35% (unless config mismatch is documented).
- Peak throughput ratio encrypted/baseline close to paper trend (~0.82).

## Fig. 10 (controlled memory access throughput)

Paper-reported targets:
- Normal DRAM read throughput: about `1300 MB/s` (roughly flat across sizes).
- Controlled access throughput at 64KB: about `362.7 MB/s`.
- Controlled access throughput at 128KB: about `504.2 MB/s`.
- 1KB controlled access is about `127x` lower than normal DRAM.
- Path ORAM reference throughput: `< 1 MB/s`.

Practical acceptance band:
- Preserve ordering and scaling trend with block size.
- 64KB/128KB controlled points within ±25% if simulator timing differs; document differences.

## Fig. 11 (k-means scaling)

Paper-reported targets:
- SE-PIM overhead over baseline PIM by core count:
  - 1 core: `0.075%`
  - 2 cores: `0.079%`
  - 4 cores: `0.09%`
  - 8 cores: `0.11%`
- At 512MB with 8 PIM cores:
  - Runtime around `17.6 s`
  - Speedup about `3.61x` vs CPU-only
  - Additional statement in paper text: about `0.05%` over baseline-PIM at 512MB point.

Practical acceptance band:
- Preserve qualitative scaling with cores/dataset size.
- SE-PIM overhead should remain tiny (sub-1%, ideally near paper tenth-of-a-percent range).
- 512MB, 8-core runtime/speedup targets within ±25% if unavoidable model differences are documented.

## 2026-03-01 Final Full-Run Snapshot (`_fs` authoritative)

Authoritative acceptance outputs are the `_fs` artifacts:
- `fig8_cpu_fs.csv`, `fig8_sepim_fs.csv`, `fig8_fs.png`
- `fig9_dma_fs.csv`, `fig9_fs.png`
- `fig10_controlled_access_fs.csv`, `fig10_fs.png`
- `fig11_kmeans_scaling_fs.csv`, `fig11_fs.png`

Legacy non-`_fs` files are retained only for traceability and are not used for paper-faithful acceptance.

Measured full-run values from current workspace artifacts:
- Fig.8 (`run_id=gate8_fs_full_20260301_125431`):
  - CPU trace rows: `2287`, unique addresses: `2182` (lookup-dependent spread).
  - SE-PIM trace rows: `138`, unique addresses: `4` (`0xff000000`, `0xff000040`, `0xff000080`, `0xff0000c0`) showing fixed host-visible channel concentration.
- Fig.9 (`run_id=gate6_fs_full_20260301_133349`):
  - average overhead: `22.01%` (target `22.35%`)
  - peak baseline throughput: `3.530 GB/s` (target `3.53 GB/s`)
  - peak SE-PIM throughput: `2.892 GB/s` (target `2.9 GB/s`)
- Fig.10 (`run_id=gate7_fs_full_20260301_060314`):
  - controlled `64KB`: `374.1 MB/s` (target `362.7 MB/s`)
  - controlled `128KB`: `503.4 MB/s` (target `504.2 MB/s`)
  - normal DRAM reference column: `1300 MB/s`
- Fig.11 (`run_id=gate9_fs_full_20260301_063852`):
  - `512MB, 8 cores` SE-PIM runtime: `17.6943 s` (target `17.6 s`)
  - speedup vs CPU: `3.5887x` (target `3.61x`)
  - SE-PIM overhead vs baseline PIM: `0.1075%` (target near `0.11%`)

## 2026-03-02 Hybrid Data Cleaning Extension (Novel Contribution)

Authoritative outputs:
- `results/csv/cleaning_pim.csv`
- `results/csv/cleaning_hybrid.csv`
- `results/plots/cleaning_pim.png`
- `results/plots/cleaning_hybrid.png`

Dataset/corruption setup (full run):
- points: `131072`
- dimensions: `8`
- dirty fraction: `~10%` (`13107` dirty entries)
- corruption mix: `4369` NaN + `4369` null + `4369` outlier

Observed results (`run_id=cleaning_hybrid_full_20260301_205927`, `seed=7`):
- Baseline clean data (`cleaning=off`): `17.694336 s`
- Dirty data without cleaning (`cleaning=off`): `17.694336 s`, `quality_score=0.900002`
- PIM-only cleaning (`cleaning=pim`):
  - `17.704647 s` total
  - overhead vs clean baseline: `+0.0583%`
  - dirty remaining: `0`
- Hybrid cleaning (`cleaning=hybrid`) block sweep:
  - `1KB`: `18.424311 s`, `access_mbps=10.693`, reads/writes=`3943/3943`
  - `4KB`: `17.899298 s`, `40.979 MB/s`, reads/writes=`1024/1024`
  - `16KB`: `17.761060 s`, `140.388 MB/s`, reads/writes=`256/256`
  - `64KB`: `17.726500 s`, `356.743 MB/s`, reads/writes=`64/64`
  - `128KB`: `17.720740 s`, `480.044 MB/s`, reads/writes=`32/32`
  - dirty remaining: `0` for all hybrid points

Interpretation:
- Dirty-data handling introduces measurable overhead once host-controlled access traffic is included.
- Hybrid overhead is strongly block-size dependent; larger blocks reduce command count and improve effective controlled-access bandwidth.
- PIM-only cleaning remains near-negligible in this model, while hybrid highlights the practical tradeoff between security-preserving controlled access and throughput.
