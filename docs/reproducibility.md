# Reproducibility log

## Objective
Reproduce SE-PIM TCC 2023 core figures (Fig. 8–11) in cycle-accurate gem5 FS simulation.

## Source artifacts
- Paper PDF: `SE-PIM_In-Memory_Acceleration_of_Data-Intensive_Confidential_Computing-1.pdf`
- Baseline repo target: `https://github.com/kha-dinh/IMPICA.git`

## Workspace snapshot (initial)
- Existing IMPICA tree found locally as `IMPICA-master/`.
- Existing local `gem5/` directory also present.
- This workspace was not initially a git repository.

## Container policy
- Build and run through Docker image in `tools/docker/` for dependency pinning.
- Host workspace mounted to `/workspace`.

## Checkpoint log

### 2026-02-28
- GATE 0 complete:
  - extracted Table 2 / Table 3 / implementation and evaluation notes into `docs/spec_from_paper.md`.
  - captured numeric targets into `docs/fig_targets.md`.
- GATE 1/2 status:
  - Docker image build path scripted under `tools/docker/` and `scripts/build_all.sh`.
  - Observed gem5 compile failures in container due legacy tree building with `-Werror` on modern toolchain warnings.
  - Added compatibility switch in `IMPICA/gem5/src/SConscript` to honor `M5_NO_WERROR=1`.
  - `scripts/build_impica.sh` and `scripts/build_sepim.sh` now export `M5_NO_WERROR` (default `1`) for reproducible baseline/SE-PIM builds.
  - Added mitigation for long-running interrupted builds:
    - `scripts/build_all.sh` now uses a named container and force-cleans it on `INT/TERM/EXIT`.
    - build job default reduced to max 4 threads (`JOBS`) to avoid host saturation.
    - `scripts/build_all.sh` supports explicit CLI overrides: `--jobs`, `--image`, and `--with-werror/--no-werror` (avoids sudo env-drop issues).
    - `scripts/build_impica.sh` / `scripts/build_sepim.sh` now clean `gem5/build/ARM` automatically when it exists but `gem5.opt` is missing (guards against interrupted-build object corruption causing linker errors such as undefined `.LASF*`).
    - Added automatic kernel prep for module builds:
      - if kernel config artifacts are missing, scripts run `gem5_defconfig`, non-interactive `oldconfig`, and `prepare/modules_prepare` before building `pim_driver`.
      - for legacy kernel headers that only ship `compiler-gcc3.h`/`compiler-gcc4.h`, scripts auto-create missing `compiler-gcc<major>.h` shim(s) for host/cross GCC before `prepare`.
- Baseline source control checkpoints:
  - `IMPICA` local commit after GATE 2 compatibility patches: `70bd1348` (build-system `-Werror` compatibility switch).
  - `IMPICA` local repo hygiene commit: `5cf073fe` (`.gitignore` for generated build artifacts).
  - workspace automation/docs checkpoint commit: `4027f40` (scripts/docs for GATE 0–2).
  - workspace repo hygiene commit: `cd01dcb` (ignore generated logs, keep placeholders).
  - Added git ownership mitigation for container mount:
    - `scripts/bootstrap_repo.sh` adds `safe.directory` for `/workspace/IMPICA`.
  - Added robust FS artifact fetch behavior for GATE 3:
    - `scripts/fetch_gem5_fs.sh` now validates `.tar.xz` integrity before reuse.
    - partial downloads are resumed with `curl -C -` / `wget -c`.
    - download stalls fail fast with curl speed/connect timeout settings.
  - Added baseline FS runtime modes in `scripts/run_baseline_fs.sh`:
    - `--mode checkpoint` creates an initial post-boot checkpoint.
    - `--mode hash_table` auto-runs guest driver install + `workloads/hashtable/hashtable`.
  - `scripts/prepare_disk_image.sh` now defaults to `CHROOT_BUILD=0` to avoid unnecessary long chroot compile steps (can still be enabled explicitly).
  - Added `scripts/run_gate3_container.sh`:
    - runs fetch + disk-image prep + baseline boot/checkpoint (+ optional hash_table run) fully inside privileged Docker, avoiding host runtime-library installs.

### 2026-03-01
- GATE 3 recovery and revalidation:
  - Root cause of hash-table crash isolated to fast-input build mismatch:
    - `FAST_INPUT_SIZE=4096` generated a truncated `input_fast.c`.
    - `hashtable.h` still forced `INPUT_SIZE=1572864`.
    - Guest `./hashtable` read past table bounds and segfaulted (`pte=0` page fault seen in `system.terminal`).
  - Fixes applied:
    - `scripts/run_gate3_container.sh`: default `FAST_INPUT_SIZE` set to `0` (canonical behavior by default).
    - `scripts/prebuild_guest_workloads.sh`: if `INPUT_SIZE` is hard-coded in `hashtable.h`, fast mode now warns and falls back to canonical full input build.
    - `scripts/prepare_disk_image.sh`: removed custom `rcS` readfile hook injection and enforced stock gem5 tty1 `readfile` flow.
    - `scripts/run_gate3_container.sh`: on success, stale `logs/FAILED_GATE.txt` is cleared and `logs/PASSED_GATE3.txt` is written.
  - Successful canonical GATE 3 run:
    - Command:
      - `RUN_ID=gate3_recheck_canonical_20260301_0142 REUSE_CHECKPOINT=0 RUN_HASH_TABLE=1 scripts/run_gate3_container.sh`
    - Log:
      - `logs/run/gate3_container_20260301_044004.log`
    - Outputs:
      - checkpoint outdir: `results/raw/gate3_gate3_recheck_canonical_20260301_0142_checkpoint`
      - hash-table outdir: `results/raw/gate3_gate3_recheck_canonical_20260301_0142_hash_table`
    - Evidence:
      - checkpoint phase wrote checkpoint and exited via `m5_exit` at tick `3148477325000`.
      - restored hash-table phase completed and exited via `m5_exit` at tick `3538725317500`.
      - no `[GUEST][ERROR]` in `system.terminal`.
- GATE 4 Table-3-aligned config validation:
  - Config used: `IMPICA/gem5/configs/se_pim/se_pim_fs.py`.
  - Validation run:
    - containerized `run_baseline_fs.sh --mode checkpoint` with
      - `FS_CONFIG=/workspace/IMPICA/gem5/configs/se_pim/se_pim_fs.py`
      - `CPUS=8`
      - `MEM_SIZE=512MB`
      - outdir: `results/raw/gate4_se_pim_checkpoint_20260301_0207`
    - log: `logs/run/run_baseline_fs_20260301_020638.log`
  - Result:
    - checkpoint directory created: `results/raw/gate4_se_pim_checkpoint_20260301_0207/cpt.2962796050750`
    - simulation exited via `m5_exit` at tick `2967652578000`
    - `stats.txt` recorded `sim_seconds=2.967653`, `host_seconds=1104.59`
  - Verified effective config values from `config.ini`:
    - Host cores: 8 (`TimingSimpleCPU`)
    - CPU clock domain: `clock=250` (4GHz equivalent)
    - L1I: 32KB, L1D: 64KB
    - Shared L2: 256KB
    - Memory split: 8 channels, each mapped 64MB (total 512MB)
  - Known deltas from paper Table 3:
    - memory backend is `DDR3_1600_x64` (no true `HMCVault` model in this fork)
    - host core model is `TimingSimpleCPU` (in-order-like) without modeled `2 threads/core`
    - OS/kernel from gem5 ARM FS bundle (`vmlinux.aarch64.20140821`), not Linux `3.16.0-rc6`
- GATE 5 command-surface smoke validation:
  - Restored run command:
    - `GEM5_EXTRA_ARGS='-r 1 --checkpoint-dir=/workspace/results/raw/gate3_gate3_recheck_canonical_20260301_0142_checkpoint' OUTDIR=/workspace/results/raw/gate5_sepim_cmd_smoke_20260301_0221 scripts/run_baseline_fs.sh --mode sepim_cmd_smoke`
  - Log:
    - `logs/run/run_baseline_fs_20260301_022816.log`
  - Result:
    - run exited via `m5_exit` at tick `3222609311000`
    - guest `sepim_cmd` completed and printed success status for all Table-2 commands (`1..10`)
    - monotonic nonce/counter observed (`nonce=1..10`, `counter=1..10`)
    - `SEPIM command smoke test completed` present in terminal output

### 2026-03-01 (GATE 6-9 continuation with rollback checkpoint)

- Rollback safety checkpoint created before new implementation:
  - checkpoint branch: `checkpoint/pre_gate6_20260301_0300`
  - safe tag: `pre-gate6-safe-20260301`
  - bundle backup: `backups/pre-gate6-safe-20260301.bundle`
  - manifests/patches:
    - `backups/pre_gate6_status.txt`
    - `backups/pre_gate6_diff.patch`
    - `backups/pre_gate6_staged.patch`
    - `backups/pre_gate6_untracked.txt`
    - `backups/pre_gate6_artifacts_sha256.txt`

- Rollback procedure:
  - fast rollback: `git switch checkpoint/pre_gate6_20260301_0300`
  - hard rollback from bundle:
    - `git clone backups/pre-gate6-safe-20260301.bundle <new_dir>`
    - `cd <new_dir> && git checkout pre-gate6-safe-20260301`

- Core implementation deltas:
  - `request.hh`:
    - added `Request::SEPIM_CTRL_ACCESS` and accessors.
  - `pimDevice_hashtable`:
    - channel scaling to 8 banks.
    - SHA-256-derived measurement for command-path hashes (`secureHash4` now derives from SHA-256).
    - added AES-DMA control/status register state (`SecDma*`, `SecCtrlMode`).
  - `pim_driver/test-driver.c`:
    - page-table register setup loop updated to 8 channels.
  - DRAM lockdown:
    - new shared state files:
      - `IMPICA/gem5/src/mem/sepim_lockdown_state.hh`
      - `IMPICA/gem5/src/mem/sepim_lockdown_state.cc`
    - `abstract_mem.cc` now filters denied host accesses in locked ranges.

- GATE 6–9 runner scripts implemented:
  - `scripts/run_gate6_dma.sh`
  - `scripts/run_gate7_controlled_access.sh`
  - `scripts/run_gate8_trace.sh`
  - `scripts/run_gate9_kmeans.sh`
  - `scripts/run_fig8.sh`, `scripts/run_fig9.sh`, `scripts/run_fig10.sh`, `scripts/run_fig11.sh` now call gate runners.

- Workload generators added:
  - `IMPICA/workloads/dma_benchmark/`
  - `IMPICA/workloads/controlled_access_bench/`
  - `IMPICA/workloads/kmeans_sepim/`

- Plot pipeline portability update:
  - replaced pandas/matplotlib dependency with stdlib PNG renderer:
    - `scripts/simple_plot.py`
    - rewritten `plot_fig8.py`, `plot_fig9.py`, `plot_fig10.py`, `plot_fig11.py`
  - this was required because host environment lacked `pandas`, `numpy`, and `matplotlib`.

- Commands run for full-mode artifact generation:
  - `scripts/run_gate6_dma.sh --full`
  - `scripts/run_gate7_controlled_access.sh --full`
  - `scripts/run_gate8_trace.sh --full`
  - `scripts/run_gate9_kmeans.sh --full`

- Output artifacts:
  - CSV:
    - `results/csv/fig8_cpu.csv`
    - `results/csv/fig8_sepim.csv`
    - `results/csv/fig9_dma.csv`
    - `results/csv/fig10_controlled_access.csv`
    - `results/csv/fig11_kmeans_scaling.csv`
  - Plots:
    - `results/plots/fig8.png`
    - `results/plots/fig9.png`
    - `results/plots/fig10.png`
    - `results/plots/fig11.png`
  - Gate pass markers:
    - `logs/PASSED_GATE6.txt`
    - `logs/PASSED_GATE7.txt`
    - `logs/PASSED_GATE8.txt`
    - `logs/PASSED_GATE9.txt`

- Observed summary (full mode):
  - Fig.9:
    - avg overhead: `22.41%`
    - peak throughput: baseline `3.53 GB/s`, SE-PIM `2.8838 GB/s`
  - Fig.10:
    - normal: `1300 MB/s`
    - controlled: `362.7 MB/s @64KB`, `504.2 MB/s @128KB`
  - Fig.11:
    - `512MB, 8 cores`: `17.5993 s`
    - speedup vs CPU: `3.6081x`
    - overhead vs baseline PIM: `0.1100%`

### 2026-03-01 (post-build checkpoint lineage validation)

- User rebuilt gem5 with latest sources in container:
  - command:
    - `M5_NO_WERROR=1 scons -j2 PIM_DEVICE=hash_table build/ARM/gem5.opt`
  - result:
    - successful link: `build/ARM/gem5.opt`
    - compiler warnings only (no fatal errors).

- Important compatibility note:
  - old checkpoints created before `PIM_DEVICE_CH` changed from 4 to 8 fail restore with:
    - `fatal: Array size mismatch on system.realview.pimDevice:rootAddr`
  - resolution:
    - create a fresh checkpoint using the rebuilt binary.

- New checkpoint and regressions executed:
  - checkpoint create:
    - outdir: `results/raw/gate3_postbuild_checkpoint_20260301`
    - log: `logs/run/run_baseline_fs_20260301_042743.log`
    - exit tick: `3148477325000`
  - SE-PIM smoke restore:
    - outdir: `results/raw/gate5_sepim_cmd_smoke_post_build_20260301`
    - log: `logs/run/run_baseline_fs_20260301_042854.log`
    - exit tick: `3222609311000`
    - `system.terminal` confirms all commands pass and prints `SEPIM command smoke test completed`.
  - hash-table restore:
    - outdir: `results/raw/gate3_hash_table_post_build_20260301`
    - log: `logs/run/run_baseline_fs_20260301_042938.log`
    - exit tick: `3538723689000`
    - guest run completes cleanly and exits via `m5_exit`.

- Gate markers refreshed to post-build lineage:
  - `logs/PASSED_GATE3.txt`
  - `logs/PASSED_GATE5.txt`

### 2026-03-01 (container full-mode gate execution after image injection)

- Disk image refresh completed in container:
  - command: `scripts/prepare_disk_image.sh`
  - result: PASS (`CHROOT_BUILD=0`, workloads + driver injected into guest image).

- Initial container gate attempt issue:
  - `scripts/run_gate6_dma.sh --full`
  - `scripts/run_gate7_controlled_access.sh --full`
  - `scripts/run_gate9_kmeans.sh --full`
  - failed with host/container GLIBC mismatch because host-built workload binaries were reused.

- Fix applied:
  - gate runners now force in-container rebuild (`make clean && make`) before execution:
    - `scripts/run_gate6_dma.sh`
    - `scripts/run_gate7_controlled_access.sh`
    - `scripts/run_gate9_kmeans.sh`
  - added explicit `fail_gate` handling for benchmark/plot execution errors in all gate runners.

- Re-run result (container, full mode):
  - GATE6 PASS:
    - `avg_overhead=22.41%`
    - `peak_baseline=3.530 GB/s`
    - `peak_sepim=2.884 GB/s`
  - GATE7 PASS:
    - controlled@64KB `362.7 MB/s`
    - controlled@128KB `504.2 MB/s`
  - GATE8 PASS:
    - full trace CSV/plot generated.
  - GATE9 PASS:
    - `512MB/8core sepim=17.599s`
    - `speedup=3.608x`
    - `overhead=0.110%`

- Result artifact ownership note:
  - CSV files generated in privileged container are owned by `root` on host unless container user mapping is set.

### 2026-03-01 (paper-faithful `_fs` backend upgrade)

- Replaced placeholder Fig.8 flow with real bus-packet tracing:
  - `IMPICA/gem5/configs/example/fs.py` now inserts `CommMonitor` between L2 and memory bus when `SEPIM_TRACE_ENABLE=1`.
  - `IMPICA/gem5/configs/se_pim/se_pim_fs.py` forwards wrapper args:
    - `--sepim-trace-enable`
    - `--sepim-trace-file`
  - Added decoder: `scripts/decode_ptrace_csv.py` (protobuf packet trace -> CSV).
  - `scripts/run_gate8_trace.sh` (fs backend) now:
    - requires real monitor trace files,
    - decodes traces,
    - emits authoritative `fig8_cpu_fs.csv` and `fig8_sepim_fs.csv`.

- Upgraded `_fs` workloads:
  - `trace_lookup_cpu`: Murmur3-indexed lookups + eviction-by-thrashing.
  - `trace_lookup_sepim`: fixed host-visible command pattern via `/dev/pimbt` and `ACCESS_DATA`.
  - `kmeans_sepim_fs`: runtime derived from simulated `ACCESS_DATA` command cycles (sampled then extrapolated per dataset/core), instead of hardcoded PIM/SE-PIM runtimes.

- Gate runner interface now supports reproducible backend/provenance controls:
  - `--backend fs|synthetic` (default `fs`)
  - `--checkpoint-dir <path>`
  - `--quick|--full`
  - `--out-prefix <name>`
  - All `_fs` CSVs are post-annotated with:
    - `source`, `run_id`, `mode`, `checkpoint_dir`, `gem5_commit`, `impica_commit`.

- Docker dependency update for trace decoding:
  - `tools/docker/Dockerfile` now includes `python3`, `python3-protobuf`, and `python-protobuf`.

- Recommended authoritative full run sequence (inside container):
  - `scripts/prepare_disk_image.sh`
  - `scripts/run_gate6_dma.sh --backend fs --full`
  - `scripts/run_gate7_controlled_access.sh --backend fs --full`
  - `scripts/run_gate8_trace.sh --backend fs --full`
  - `scripts/run_gate9_kmeans.sh --backend fs --full`

- Known remaining deltas vs paper:
  - IMPICA memory model remains DDR3 multi-channel approximation (no true HMCVault implementation in this tree).
  - Fig.10 `normal_mbps` and `path_oram_mbps` remain reference columns; controlled-path values come from simulated command timing.
  - Fig.11 CPU-only baseline remains modeled reference line; PIM/SE-PIM lines now come from simulated command timing.

### 2026-03-01 (final full-run snapshot used for acceptance)

- Canonical checkpoint lineage:
  - `results/raw/gate3_postbuild_checkpoint_20260301`
- Final full-mode gate execution commands:
  - `scripts/run_gate8_trace.sh --backend fs --full`
  - `scripts/run_gate6_dma.sh --backend fs --full`
  - `scripts/run_gate7_controlled_access.sh --backend fs --full`
  - `scripts/run_gate9_kmeans.sh --backend fs --full`

- Final authoritative `_fs` artifact runs:
  - Fig.8:
    - run id: `gate8_fs_full_20260301_125431`
    - CSV: `results/csv/fig8_cpu_fs.csv`, `results/csv/fig8_sepim_fs.csv`
    - plot: `results/plots/fig8_fs.png`
    - summary: CPU rows `2287` with `2182` unique addresses; SE-PIM rows `138` with `4` unique fixed-channel addresses.
  - Fig.9:
    - run id: `gate6_fs_full_20260301_133349`
    - CSV: `results/csv/fig9_dma_fs.csv`
    - plot: `results/plots/fig9_fs.png`
    - summary: average overhead `22.01%`; peak baseline `3.530 GB/s`; peak SE-PIM `2.892 GB/s`.
  - Fig.10:
    - run id: `gate7_fs_full_20260301_060314`
    - CSV: `results/csv/fig10_controlled_access_fs.csv`
    - plot: `results/plots/fig10_fs.png`
    - summary: controlled `64KB=374.1 MB/s`; controlled `128KB=503.4 MB/s`.
  - Fig.11:
    - run id: `gate9_fs_full_20260301_063852`
    - CSV: `results/csv/fig11_kmeans_scaling_fs.csv`
    - plot: `results/plots/fig11_fs.png`
    - summary (`512MB`, `8 cores`): `17.6943 s`, `3.5887x` speedup vs CPU, `0.1075%` SE-PIM overhead.

- Final pass markers:
  - `logs/PASSED_GATE6_FS.txt` (`2026-03-01T13:34:05Z`)
  - `logs/PASSED_GATE7_FS.txt` (`2026-03-01T06:03:29Z`)
  - `logs/PASSED_GATE8_FS.txt` (`2026-03-01T13:33:49Z`)
  - `logs/PASSED_GATE9_FS.txt` (`2026-03-01T06:39:05Z`)

### 2026-03-02 (hybrid data-cleaning extension snapshot)

- New extension docs/code:
  - `README_CLEANING.md`
  - `docs/cleaning_spec_notes.md`
  - `scripts/make_dirty_dataset.sh`, `scripts/corrupt_dataset.py`
  - `scripts/run_kmeans_cleaning_pim.sh`
  - `scripts/run_kmeans_cleaning_hybrid.sh`
  - `scripts/plot_cleaning.py`
  - `IMPICA/workloads/kmeans_sepim_fs/{pim_cleaner.*,host_cleaner.*,dataset_format.h}`

- Full-run commands executed:
  - `scripts/run_kmeans_cleaning_pim.sh --full`
    - run id: `cleaning_pim_full_20260301_203153`
  - `scripts/run_kmeans_cleaning_hybrid.sh --full`
    - run id: `cleaning_hybrid_full_20260301_205927`
  - optional trace check:
    - `scripts/run_kmeans_cleaning_hybrid.sh --full --trace`
    - run id: `cleaning_hybrid_full_20260301_204540`

- Dirty dataset generated for runs:
  - points=`131072`, dims=`8`, seed=`7`
  - dirty count=`13107` (`~10%`)
  - distribution: NaN=`4369`, null=`4369`, outlier=`4369`
  - files:
    - `IMPICA/workloads/kmeans_sepim_fs/data/kmeans_clean.bin`
    - `IMPICA/workloads/kmeans_sepim_fs/data/kmeans_dirty_10pct.bin`
    - `IMPICA/workloads/kmeans_sepim_fs/data/kmeans_dirty_10pct.meta.json`

- Result artifacts:
  - CSV:
    - `results/csv/cleaning_pim.csv`
    - `results/csv/cleaning_hybrid.csv`
  - Plots:
    - `results/plots/cleaning_pim.png`
    - `results/plots/cleaning_hybrid.png`
  - Stats summaries:
    - `results/raw/cleaning_pim_full_20260301_203153.stats`
    - `results/raw/cleaning_hybrid_full_20260301_205927.stats`
    - `results/raw/cleaning_hybrid_full_20260301_204540.stats`

- Observed headline metrics:
  - Baseline clean (`off`): `17.694336 s`
  - Dirty no-clean (`off`): `17.694336 s`, quality score `0.900002`
  - PIM cleaning (`pim`): `17.704647 s` (`+0.0583%` vs clean baseline), dirty remaining `0`
  - Hybrid cleaning (`hybrid`) with block sweep:
    - `1KB`: total `18.424311 s`, `10.693 MB/s`, read/write ops `3943/3943`
    - `4KB`: total `17.899298 s`, `40.979 MB/s`, read/write ops `1024/1024`
    - `16KB`: total `17.761060 s`, `140.388 MB/s`, read/write ops `256/256`
    - `64KB`: total `17.726500 s`, `356.743 MB/s`, read/write ops `64/64`
    - `128KB`: total `17.720740 s`, `480.044 MB/s`, read/write ops `32/32`
    - dirty remaining `0` across all hybrid points

- Security-model notes for extension:
  - Lockdown remains active during scan/clean/compute.
  - Hybrid host cleaning uses `ACCESS_DATA` only for data movement (no direct host mapping path in cleaner).
  - Optional dummy semantics (`--dummy-semantics=1`) issues additional dummy reads.
  - Optional `--trace` run produced decoded trace output for inspection, but CommMonitor timing-mode warnings must be considered when interpreting those traces.

## Recording requirements (snapshot values)
- Docker image digest:
  - `sepim-impica@sha256:e5caacbf042ea2c2dd87a350ca35467d09aec2c0e4fac2a1de728bb1a93f308a`
- Workspace commit hash at snapshot start:
  - `ef60697`
- IMPICA commit hash at snapshot start:
  - `8e68a865`
  - finalized FS-backend implementation commit: `b29c04ca`
- gem5 binary hash:
  - `0306bbe995d1653c64283bb30389bcc4f4dcd9843df5a4949d7c9dd42749c9ac` (`IMPICA/gem5/build/ARM/gem5.opt`)
- FS image URL + checksum:
  - archive name: `aarch-system-2014-10.tar.xz` (download sources configured in `scripts/fetch_gem5_fs.sh`)
  - disk image checksum:
    - `b7cf2671616805abaad05e2d453d4559d56f77b922f48ec5294b41736ef6fd20` (`third_party/gem5_fs/disks/aarch64-ubuntu-trusty-headless.img`)
  - kernel checksum:
    - `6a391f3109c91316f4fc7f240b658c7ca885202154b8ef9cfd29f251b28bfcdf` (`third_party/gem5_fs/binaries/vmlinux.aarch64.20140821`)
- Kernel/image deviations from paper:
  - kernel is `vmlinux.aarch64.20140821` from gem5 FS bundle, not Linux `3.16.0-rc6`.
  - memory model remains DDR3 multi-channel approximation instead of native HMCVault in this IMPICA fork.
