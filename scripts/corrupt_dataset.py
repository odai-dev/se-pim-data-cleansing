#!/usr/bin/env python3

import argparse
import json
import math
import os
import random
import struct
from collections import Counter

MAGIC = 0x4B4D4453  # KMDS
VERSION = 1
NULL_SENTINEL = -999999.0


def write_dataset(path, points, dims, seed):
    hdr = struct.pack(
        "<8I",
        MAGIC,
        VERSION,
        points,
        dims,
        seed,
        0,
        0,
        0,
    )
    with open(path, "wb") as f:
        f.write(hdr)
        for row in data_rows(points, dims):
            f.write(struct.pack("<" + "f" * dims, *row))


def data_rows(points, dims):
    for i in range(points):
        yield _DATA[i * dims : (i + 1) * dims]


def set_row(i, dims, vals):
    base = i * dims
    _DATA[base : base + dims] = vals


def get_row(i, dims):
    base = i * dims
    return _DATA[base : base + dims]


def generate_clean(points, dims, seed):
    rnd = random.Random(seed)
    arr = [0.0] * (points * dims)
    for i in range(points):
        base = i * dims
        for d in range(dims):
            arr[base + d] = rnd.gauss(0.0, 1.0)
    return arr


def apply_corruption(points, dims, dirty_frac, seed):
    rnd = random.Random(seed ^ 0xA5A55A5A)
    dirty_count = int(points * dirty_frac)
    dirty_indices = sorted(rnd.sample(range(points), dirty_count)) if dirty_count > 0 else []

    n_nan = dirty_count // 3
    n_null = dirty_count // 3
    n_out = dirty_count - n_nan - n_null

    types = {}
    for idx in dirty_indices[:n_nan]:
        row = get_row(idx, dims)
        col = rnd.randrange(dims)
        row[col] = float("nan")
        set_row(idx, dims, row)
        types[idx] = "nan"

    for idx in dirty_indices[n_nan : n_nan + n_null]:
        row = [0.0] * dims
        row[0] = NULL_SENTINEL
        set_row(idx, dims, row)
        types[idx] = "null"

    for idx in dirty_indices[n_nan + n_null :]:
        row = get_row(idx, dims)
        mag = rnd.uniform(5000.0, 20000.0)
        sign = -1.0 if rnd.random() < 0.5 else 1.0
        for d in range(dims):
            row[d] = sign * mag * (1.0 + d * 0.03)
        set_row(idx, dims, row)
        types[idx] = "outlier"

    return dirty_indices, types


def main():
    ap = argparse.ArgumentParser(description="Generate clean + corrupted k-means dataset binary")
    ap.add_argument("--clean-out", required=True)
    ap.add_argument("--dirty-out", required=True)
    ap.add_argument("--meta-out", required=True)
    ap.add_argument("--points", type=int, default=131072)
    ap.add_argument("--dims", type=int, default=8)
    ap.add_argument("--dirty-frac", type=float, default=0.10)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    if args.points <= 0 or args.dims <= 0:
        raise SystemExit("points and dims must be positive")
    if not (0.0 <= args.dirty_frac <= 1.0):
        raise SystemExit("dirty-frac must be in [0,1]")

    global _DATA
    _DATA = generate_clean(args.points, args.dims, args.seed)

    os.makedirs(os.path.dirname(args.clean_out), exist_ok=True)
    os.makedirs(os.path.dirname(args.dirty_out), exist_ok=True)
    os.makedirs(os.path.dirname(args.meta_out), exist_ok=True)

    write_dataset(args.clean_out, args.points, args.dims, args.seed)

    dirty_indices, type_map = apply_corruption(args.points, args.dims, args.dirty_frac, args.seed)
    write_dataset(args.dirty_out, args.points, args.dims, args.seed)

    by_type = Counter(type_map.values())
    meta = {
        "format": {
            "magic_hex": hex(MAGIC),
            "version": VERSION,
            "float": "float32",
            "null_sentinel": NULL_SENTINEL,
        },
        "seed": args.seed,
        "points": args.points,
        "dims": args.dims,
        "dirty_frac_requested": args.dirty_frac,
        "dirty_count": len(dirty_indices),
        "dirty_frac_actual": (len(dirty_indices) / float(args.points)) if args.points else 0.0,
        "distribution": {
            "nan": int(by_type.get("nan", 0)),
            "null": int(by_type.get("null", 0)),
            "outlier": int(by_type.get("outlier", 0)),
        },
        "dirty_indices": {
            "nan": [i for i in dirty_indices if type_map.get(i) == "nan"],
            "null": [i for i in dirty_indices if type_map.get(i) == "null"],
            "outlier": [i for i in dirty_indices if type_map.get(i) == "outlier"],
        },
    }

    with open(args.meta_out, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)

    print("[INFO] clean dataset:", args.clean_out)
    print("[INFO] dirty dataset:", args.dirty_out)
    print("[INFO] metadata:", args.meta_out)
    print(
        "[INFO] dirty summary: count=%d frac=%.6f nan=%d null=%d outlier=%d"
        % (
            meta["dirty_count"],
            meta["dirty_frac_actual"],
            meta["distribution"]["nan"],
            meta["distribution"]["null"],
            meta["distribution"]["outlier"],
        )
    )


if __name__ == "__main__":
    main()
