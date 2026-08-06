#!/usr/bin/env python3
"""Apply reproducible anomaly locations to an existing KMDS dataset."""

import argparse
import array
import hashlib
import json
import math
import random
import struct
from collections import Counter
from pathlib import Path


MAGIC = 0x4B4D4453
VERSION = 1
NULL_SENTINEL = -999999.0
HEADER = struct.Struct("<8I")


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_dataset(path):
    with path.open("rb") as stream:
        raw_header = stream.read(HEADER.size)
        if len(raw_header) != HEADER.size:
            raise ValueError("truncated KMDS header")
        fields = list(HEADER.unpack(raw_header))
        magic, version, points, dims = fields[:4]
        if magic != MAGIC or version != VERSION or points == 0 or dims == 0:
            raise ValueError("invalid KMDS header")
        values = array.array("f")
        values.fromfile(stream, points * dims)
        if len(values) != points * dims or stream.read(1):
            raise ValueError("invalid KMDS body size")
    if __import__("sys").byteorder != "little":
        values.byteswap()
    if not all(math.isfinite(value) for value in values):
        raise ValueError("source dataset is not clean and finite")
    return fields, values


def main():
    parser = argparse.ArgumentParser(description="Corrupt an existing clean KMDS dataset")
    parser.add_argument("--clean", required=True, type=Path)
    parser.add_argument("--dirty-out", required=True, type=Path)
    parser.add_argument("--meta-out", required=True, type=Path)
    parser.add_argument("--base-meta", type=Path)
    parser.add_argument("--dirty-frac", required=True, type=float)
    parser.add_argument("--seed", required=True, type=int)
    args = parser.parse_args()
    if not 0.0 <= args.dirty_frac <= 1.0:
        raise SystemExit("dirty-frac must be in [0,1]")

    header, values = load_dataset(args.clean)
    points, dims = header[2], header[3]
    header[4] = args.seed
    randomizer = random.Random(args.seed ^ 0xA5A55A5A)
    dirty_count = int(points * args.dirty_frac)
    indices = sorted(randomizer.sample(range(points), dirty_count)) if dirty_count else []
    first = dirty_count // 3
    second = first + dirty_count // 3
    types = {}
    for index in indices[:first]:
        values[index * dims + randomizer.randrange(dims)] = float("nan")
        types[index] = "nan"
    for index in indices[first:second]:
        base = index * dims
        values[base : base + dims] = array.array("f", [0.0] * dims)
        values[base] = NULL_SENTINEL
        types[index] = "null"
    for index in indices[second:]:
        base = index * dims
        magnitude = randomizer.uniform(5000.0, 20000.0)
        sign = -1.0 if randomizer.random() < 0.5 else 1.0
        for dimension in range(dims):
            values[base + dimension] = sign * magnitude * (1.0 + dimension * 0.0003)
        types[index] = "outlier"

    args.dirty_out.parent.mkdir(parents=True, exist_ok=True)
    with args.dirty_out.open("wb") as stream:
        stream.write(HEADER.pack(*header))
        output = array.array("f", values)
        if __import__("sys").byteorder != "little":
            output.byteswap()
        output.tofile(stream)

    counts = Counter(types.values())
    base_meta = json.loads(args.base_meta.read_text()) if args.base_meta else {}
    metadata = {
        "schema_version": 1,
        "source": base_meta.get("source", "existing KMDS dataset"),
        "base_metadata": str(args.base_meta) if args.base_meta else None,
        "points": points,
        "dims": dims,
        "seed": args.seed,
        "dirty_frac_requested": args.dirty_frac,
        "dirty_count": dirty_count,
        "dirty_frac_actual": dirty_count / points,
        "distribution": {kind: counts.get(kind, 0) for kind in ("nan", "null", "outlier")},
        "dirty_indices": {
            kind: [index for index in indices if types[index] == kind]
            for kind in ("nan", "null", "outlier")
        },
        "files": {
            "clean": {
                "path": args.clean.name,
                "bytes": args.clean.stat().st_size,
                "sha256": sha256_file(args.clean),
            },
            "dirty": {
                "path": args.dirty_out.name,
                "bytes": args.dirty_out.stat().st_size,
                "sha256": sha256_file(args.dirty_out),
            },
        },
    }
    args.meta_out.parent.mkdir(parents=True, exist_ok=True)
    args.meta_out.write_text(json.dumps(metadata, indent=2) + "\n")
    print(f"[PASS] dirty={dirty_count}/{points} output={args.dirty_out}")


if __name__ == "__main__":
    main()
