#!/usr/bin/env python3

import argparse
import pandas as pd
import matplotlib.pyplot as plt


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    df = pd.read_csv(args.input)

    fig, axes = plt.subplots(1, 2, figsize=(12, 4))

    for mode, g in df.groupby("mode"):
        axes[0].plot(g["block_size"], g["baseline_latency_ns"], marker="o", label=f"baseline-{mode}")
        axes[0].plot(g["block_size"], g["sepim_latency_ns"], marker="x", label=f"sepim-{mode}")

    axes[0].set_title("DMA latency")
    axes[0].set_xlabel("Block size (bytes)")
    axes[0].set_ylabel("Latency (ns)")
    axes[0].grid(True, alpha=0.3)
    axes[0].legend(fontsize=8)

    max_row = df.groupby("block_size")[["baseline_gbps", "sepim_gbps"]].max().reset_index()
    axes[1].plot(max_row["block_size"], max_row["baseline_gbps"], marker="o", label="Baseline")
    axes[1].plot(max_row["block_size"], max_row["sepim_gbps"], marker="x", label="SE-PIM")
    axes[1].set_title("DMA throughput")
    axes[1].set_xlabel("Block size (bytes)")
    axes[1].set_ylabel("Throughput (GB/s)")
    axes[1].grid(True, alpha=0.3)
    axes[1].legend()

    plt.tight_layout()
    plt.savefig(args.out, dpi=200)


if __name__ == "__main__":
    main()
