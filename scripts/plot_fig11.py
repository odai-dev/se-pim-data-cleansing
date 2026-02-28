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

    for cores in sorted(df["pim_cores"].unique()):
        g = df[df["pim_cores"] == cores]
        axes[0].plot(g["dataset_mb"], g["pim_baseline_sec"], marker="o", label=f"PIM-{cores} baseline")
        axes[0].plot(g["dataset_mb"], g["sepim_sec"], marker="x", linestyle="--", label=f"PIM-{cores} se-pim")

    cpu = df.groupby("dataset_mb")["cpu_sec"].mean().reset_index()
    axes[0].plot(cpu["dataset_mb"], cpu["cpu_sec"], marker="^", label="CPU-only")
    axes[0].set_xlabel("Dataset size (MB)")
    axes[0].set_ylabel("Runtime (s)")
    axes[0].set_title("k-means runtime scaling")
    axes[0].grid(True, alpha=0.3)
    axes[0].legend(fontsize=7)

    over = df.groupby("pim_cores")["overhead_pct"].mean().reset_index()
    axes[1].bar(over["pim_cores"].astype(str), over["overhead_pct"])
    axes[1].set_xlabel("PIM cores")
    axes[1].set_ylabel("SE-PIM overhead (%)")
    axes[1].set_title("SE-PIM overhead vs baseline PIM")
    axes[1].grid(True, axis="y", alpha=0.3)

    plt.tight_layout()
    plt.savefig(args.out, dpi=200)


if __name__ == "__main__":
    main()
