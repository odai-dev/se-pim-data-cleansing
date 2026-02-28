#!/usr/bin/env python3

import argparse
import pandas as pd
import matplotlib.pyplot as plt


def _to_num_addr(s):
    if isinstance(s, str):
        s = s.strip()
        if s.startswith("0x"):
            return int(s, 16)
    return int(s)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cpu", required=True)
    ap.add_argument("--sepim", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    cpu = pd.read_csv(args.cpu)
    sepim = pd.read_csv(args.sepim)

    for df in (cpu, sepim):
        df["addr_num"] = df["addr"].apply(_to_num_addr)

    fig, axes = plt.subplots(2, 1, figsize=(10, 6), sharex=True)

    for ax, df, title in [
        (axes[0], cpu, "CPU-only trace"),
        (axes[1], sepim, "SE-PIM trace"),
    ]:
        rd = df[df["rw"].str.upper().isin(["R", "READ"])]
        wr = df[df["rw"].str.upper().isin(["W", "WRITE"])]
        ax.scatter(rd["time"], rd["addr_num"], s=4, label="read", alpha=0.7)
        ax.scatter(wr["time"], wr["addr_num"], s=4, label="write", alpha=0.7)
        ax.set_title(title)
        ax.set_ylabel("Physical address")
        ax.grid(True, alpha=0.3)

    axes[1].set_xlabel("Time")
    axes[0].legend(loc="upper right")
    plt.tight_layout()
    plt.savefig(args.out, dpi=200)


if __name__ == "__main__":
    main()
