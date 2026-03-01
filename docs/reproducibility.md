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

## Recording requirements (to be filled as gates progress)
- Docker image digest:
- IMPICA commit hash:
- gem5 binary hash:
- FS image URL + checksum:
- Kernel/image deviations from paper:
- Per-figure run command, seed, runtime, output CSV/PNG paths:
