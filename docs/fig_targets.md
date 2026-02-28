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
