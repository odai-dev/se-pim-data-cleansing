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

    plt.figure(figsize=(7, 4))
    plt.plot(df["block_kb"], df["normal_mbps"], marker="o", label="Normal DRAM")
    plt.plot(df["block_kb"], df["controlled_mbps"], marker="x", label="Controlled access")
    if "path_oram_mbps" in df.columns:
        plt.plot(df["block_kb"], df["path_oram_mbps"], marker="s", label="Path ORAM")

    plt.xscale("log", base=2)
    plt.yscale("log")
    plt.xlabel("Block size (KB)")
    plt.ylabel("Throughput (MB/s)")
    plt.title("Controlled access throughput")
    plt.grid(True, which="both", alpha=0.3)
    plt.legend()
    plt.tight_layout()
    plt.savefig(args.out, dpi=200)


if __name__ == "__main__":
    main()
