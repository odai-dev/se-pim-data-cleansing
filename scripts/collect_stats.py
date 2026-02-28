#!/usr/bin/env python3
"""Extract selected metrics from gem5 stats.txt files into CSV.

Usage:
  python3 scripts/collect_stats.py --stats results/raw/run/stats.txt --keys sim_seconds system.cpu.numCycles --out results/csv/metrics.csv
"""

import argparse
import csv
from pathlib import Path


def parse_stats(path: Path):
    data = {}
    for line in path.read_text(errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("-") or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        key = parts[0]
        val = parts[1]
        data[key] = val
    return data


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stats", required=True, help="Path to gem5 stats.txt")
    ap.add_argument("--keys", nargs="+", required=True, help="Metric keys to extract")
    ap.add_argument("--out", required=True, help="Output CSV path")
    args = ap.parse_args()

    stats_path = Path(args.stats)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    parsed = parse_stats(stats_path)

    with out_path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["metric", "value"])
        for key in args.keys:
            writer.writerow([key, parsed.get(key, "NA")])


if __name__ == "__main__":
    main()
