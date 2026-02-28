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
  - Added git ownership mitigation for container mount:
    - `scripts/bootstrap_repo.sh` adds `safe.directory` for `/workspace/IMPICA`.

## Recording requirements (to be filled as gates progress)
- Docker image digest:
- IMPICA commit hash:
- gem5 binary hash:
- FS image URL + checksum:
- Kernel/image deviations from paper:
- Per-figure run command, seed, runtime, output CSV/PNG paths:
