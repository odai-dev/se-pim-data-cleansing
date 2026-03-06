# SE-PIM Data Cleansing — Artifact Repository

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

This repository contains the artifact for the paper:

> **"PIM-Cleanser: In-Memory Acceleration of Data-Intensive Confidential Data Sanitization"**  
> Wafaa M. AL-Madhaji and Ibrahim Ahmed Al-Baltah

It provides:
1. **Reproducible replication** of Figs. 8–11 from the SE-PIM paper using cycle-accurate gem5 full-system simulation.
2. **Hybrid in-PIM data cleansing extension** — a novel PIM/host-hybrid k-means cleaning pipeline with security (lockdown) semantics.

---

## Table of Contents

- [Repository Layout](#repository-layout)
- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [Setup](#setup)
- [Running Experiments](#running-experiments)
- [Data Cleaning Extension](#data-cleaning-extension)
- [Expected Results](#expected-results)
- [Artifact Checksums](#artifact-checksums)
- [Known Deviations from Paper](#known-deviations-from-paper)
- [Citation](#citation)
- [License](#license)

---

## Repository Layout

```
.
├── IMPICA/               # Patched SE-PIM / IMPICA source tree
│   ├── gem5/             # Modified gem5 simulator (ARM FS)
│   └── workloads/        # Guest workloads (DMA bench, k-means, etc.)
├── scripts/              # All build, run, and plot scripts
├── docs/                 # Reproducibility log, spec notes, figure targets
├── results/
│   ├── raw/              # Generated simulation output dirs (gitignored)
│   ├── csv/              # Parsed CSV results (gitignored)
│   └── plots/            # Generated figures (gitignored)
├── logs/                 # Build and run logs (gitignored)
├── tools/docker/         # Dockerfile for the reproducible build environment
├── third_party/          # Downloaded FS images and runtime libs (gitignored)
├── README.md             # This file
├── README_CLEANING.md    # Detailed notes on the data-cleaning extension
├── docs/reproducibility.md  # Full gate-by-gate experiment log
└── se_pim_data_cleansing_paper.tex  # LaTeX source of the accompanying paper
```

---

## Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Docker | ≥ 20.10 | Required for all build and run steps |
| Disk space | ≥ 20 GB free | gem5 FS image (~7 GB) + build artifacts |
| RAM | ≥ 8 GB | sim runs are memory-intensive |
| `curl` or `wget` | any | For downloading FS artifacts |
| `python3` | ≥ 3.8 | For plot scripts |
| `aarch64-linux-gnu-gcc` | optional | If available on host, skips Docker for some steps |

### Host Configuration (Ubuntu / Debian)

You can install all required host dependencies with the following commands:

```bash
# Update packages
sudo apt-get update

# Install basic required tools
sudo apt-get install -y git curl python3

# (Optional) Install cross-compiler to speed up workload builds
sudo apt-get install -y gcc-aarch64-linux-gnu
```

### Docker Installation

You **must** have Docker installed because the gem5 execution environment relies on a specific legacy toolchain (`ubuntu18`).

```bash
# 1. Install Docker dependencies
sudo apt-get update
sudo apt-get install -y ca-certificates curl

# 2. Add Docker's official GPG key
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

# 3. Add the Docker repository
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# 4. Install Docker
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io

# 5. Add your user to the docker group (avoids needing 'sudo docker')
sudo usermod -aG docker $USER
# You may need to log out and log back in, or run 'newgrp docker' for this to take effect.
```

> **Note:** All build and simulation steps run inside the Docker container `sepim-impica:ubuntu18`. You do **not** need to install gem5's legacy dependencies on your host.

---

## Quick Start

```bash
# 1. Clone this repository
git clone https://github.com/odai-dev/se-pim-data-cleansing.git
cd se-pim-data-cleansing

# 2. Build the Docker image
scripts/build_all.sh --jobs 4

# 3. Fetch gem5 FS artifacts (ARM kernel + disk image, ~7 GB)
scripts/fetch_gem5_fs.sh

# 4. Run the full experiment suite (inside Docker automatically)
scripts/run_gate3_container.sh          # Boot checkpoint (Gate 3)
scripts/run_gate6_dma.sh --backend fs --full
scripts/run_gate7_controlled_access.sh --backend fs --full
scripts/run_gate8_trace.sh --backend fs --full
scripts/run_gate9_kmeans.sh --backend fs --full
```

Plots are written to `results/plots/`. See [Running Experiments](#running-experiments) for details.

---

## Setup

### Step 1 — Clone

```bash
git clone https://github.com/odai-dev/se-pim-data-cleansing.git
cd se-pim-data-cleansing
```

### Step 2 — Build Docker Image

```bash
# Default: 4 parallel jobs, no -Werror
scripts/build_all.sh

# Options
scripts/build_all.sh --jobs 8 --image sepim-impica:ubuntu18
```

This builds:
- The gem5 ARM simulator (`IMPICA/gem5/build/ARM/gem5.opt`)
- The SE-PIM/IMPICA guest workloads (cross-compiled for AArch64)
- The PIM kernel module (`pim_driver`)

> The build takes **60–120 minutes** on a typical 8-core host.

### Step 3 — Fetch FS Artifacts

```bash
scripts/fetch_gem5_fs.sh
```

Downloads the gem5 ARM FS bundle (`aarch64-ubuntu-trusty-headless.img` + `vmlinux.aarch64.20140821`) into `third_party/gem5_fs/`. Resumes interrupted downloads automatically.

**Checksums** (see [Artifact Checksums](#artifact-checksums)):
- Disk image: `b7cf2671...`
- Kernel: `6a391f31...`

### Step 4 — Prepare Disk Image

Injects compiled workloads and the PIM driver into the guest image:

```bash
scripts/prepare_disk_image.sh
```

> Requires Docker with `--privileged` (for loop mount). Takes ~5 minutes.

### Step 5 — Create Boot Checkpoint

```bash
scripts/run_gate3_container.sh
```

Creates a post-boot gem5 checkpoint in `results/raw/`. This checkpoint is reused by all subsequent experiment runs. Takes ~30 minutes.

---

## Running Experiments

All gate runners accept `--backend fs` (simulation) and `--full` (full input size) or `--quick` (reduced config for smoke testing).

### Figure 8 — Memory Access Traffic Trace

```bash
scripts/run_gate8_trace.sh --backend fs --full
# Output: results/csv/fig8_cpu_fs.csv, fig8_sepim_fs.csv
#         results/plots/fig8_fs.png
```

### Figure 9 — DMA Overhead

```bash
scripts/run_gate6_dma.sh --backend fs --full
# Output: results/csv/fig9_dma_fs.csv
#         results/plots/fig9_fs.png
```

### Figure 10 — Controlled-Access Bandwidth

```bash
scripts/run_gate7_controlled_access.sh --backend fs --full
# Output: results/csv/fig10_controlled_access_fs.csv
#         results/plots/fig10_fs.png
```

### Figure 11 — k-means Scaling

```bash
scripts/run_gate9_kmeans.sh --backend fs --full
# Output: results/csv/fig11_kmeans_scaling_fs.csv
#         results/plots/fig11_fs.png
```

### Regenerate All Plots from Existing CSVs

```bash
scripts/run_fig8.sh
scripts/run_fig9.sh
scripts/run_fig10.sh
scripts/run_fig11.sh
```

---

## Data Cleaning Extension

See [`README_CLEANING.md`](README_CLEANING.md) for full details on the PIM/hybrid data-cleaning pipeline.

### Generate Dirty Dataset

```bash
scripts/make_dirty_dataset.sh --dirty-frac 0.10 --seed 7 --points 131072 --dims 8
```

Produces `kmeans_clean.bin`, `kmeans_dirty_10pct.bin`, and `kmeans_dirty_10pct.meta.json` under `IMPICA/workloads/kmeans_sepim_fs/data/`.

### Run PIM-Only Cleaning

```bash
scripts/run_kmeans_cleaning_pim.sh --full
# Output: results/csv/cleaning_pim.csv, results/plots/cleaning_pim.png
```

### Run Hybrid Cleaning (block-size sweep)

```bash
scripts/run_kmeans_cleaning_hybrid.sh --full
# Output: results/csv/cleaning_hybrid.csv, results/plots/cleaning_hybrid.png
```

---

## Expected Results

### Figures 8–11 (from final authoritative run, 2026-03-01)

| Figure | Metric | Value |
|---|---|---|
| **Fig. 8** | CPU trace rows / unique addresses | 2,287 / 2,182 |
| **Fig. 8** | SE-PIM trace rows / unique addresses | 138 / 4 |
| **Fig. 9** | Avg. DMA overhead | 22.01% |
| **Fig. 9** | Peak baseline throughput | 3.530 GB/s |
| **Fig. 9** | Peak SE-PIM throughput | 2.892 GB/s |
| **Fig. 10** | Controlled-access @ 64 KB | 374.1 MB/s |
| **Fig. 10** | Controlled-access @ 128 KB | 503.4 MB/s |
| **Fig. 11** | k-means (512 MB, 8 cores) | 17.694 s |
| **Fig. 11** | Speedup vs. CPU | 3.589× |
| **Fig. 11** | SE-PIM overhead vs. PIM | 0.108% |

### Data Cleaning Results (2026-03-02)

| Mode | Total Time | Quality Score |
|---|---|---|
| Baseline clean | 17.694 s | 1.0 |
| Dirty, no cleaning | 17.694 s | 0.900 |
| PIM cleaning | 17.705 s (+0.06%) | 1.0 |
| Hybrid @ 4 KB | 17.899 s | 1.0 |
| Hybrid @ 64 KB | 17.727 s | 1.0 |
| Hybrid @ 128 KB | 17.721 s | 1.0 |

---

## Artifact Checksums

| Artifact | SHA-256 |
|---|---|
| Docker image (`sepim-impica`) | `sha256:e5caacbf042ea2c2dd87a350ca35467d09aec2c0e4fac2a1de728bb1a93f308a` |
| `gem5.opt` binary | `0306bbe995d1653c64283bb30389bcc4f4dcd9843df5a4949d7c9dd42749c9ac` |
| `aarch64-ubuntu-trusty-headless.img` | `b7cf2671616805abaad05e2d453d4559d56f77b922f48ec5294b41736ef6fd20` |
| `vmlinux.aarch64.20140821` | `6a391f3109c91316f4fc7f240b658c7ca885202154b8ef9cfd29f251b28bfcdf` |
| IMPICA commit (final) | `b29c04ca` |
| Workspace commit (snapshot) | `ef60697` |

---

## Known Deviations from Paper

| Paper Spec | This Implementation |
|---|---|
| HMCVault memory model | DDR3 multi-channel approximation (no native HMCVault in this IMPICA fork) |
| Linux 3.16.0-rc6 kernel | `vmlinux.aarch64.20140821` from gem5 ARM FS bundle |
| 2 threads/core (SMT) | `TimingSimpleCPU` (in-order-like, no SMT) |
| Fig. 11 CPU baseline | Reference modeled line; PIM/SE-PIM values from simulated `ACCESS_DATA` command timing |

---

## Citation

If you use this artifact, please cite:

```bibtex
@article{almadhaji2026pimcleanser,
  title     = {PIM-Cleanser: In-Memory Acceleration of Data-Intensive Confidential Data Sanitization},
  author    = {AL-Madhaji, Wafaa M. and Al-Baltah, Ibrahim Ahmed},
  year      = {2026}
}
```

See also [`CITATION.cff`](CITATION.cff) for machine-readable citation metadata.

---

## License

This project is licensed under the **MIT License** — see [LICENSE](LICENSE) for details.

The gem5 simulator and IMPICA baseline are subject to their own licenses (BSD and MIT respectively).
