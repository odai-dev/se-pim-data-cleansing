#!/usr/bin/env python3
"""Convert and reproducibly corrupt the official UCI HAR archive.

The output uses the same KMDS/KMLB binary formats as the synthetic datasets.
The archive is read directly so extraction paths cannot affect provenance.
"""

import argparse
import hashlib
import io
import json
import math
import random
import struct
import zipfile
from collections import Counter
from pathlib import Path


DATA_MAGIC = 0x4B4D4453  # KMDS
DATA_VERSION = 1
LABEL_MAGIC = 0x4B4D4C42  # KMLB
LABEL_VERSION = 1
NULL_SENTINEL = -999999.0
EXPECTED_POINTS = 10299
EXPECTED_DIMS = 561
EXPECTED_CLUSTERS = 6
ARCHIVE_MEMBERS = (
    ("UCI HAR Dataset/train/X_train.txt", "UCI HAR Dataset/train/y_train.txt"),
    ("UCI HAR Dataset/test/X_test.txt", "UCI HAR Dataset/test/y_test.txt"),
)


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_archive(path):
    rows = []
    labels = []
    nested_sha256 = None
    with zipfile.ZipFile(path) as outer_archive:
        bad_member = outer_archive.testzip()
        if bad_member is not None:
            raise ValueError(f"outer archive CRC failure: {bad_member}")
        if all(data_name in outer_archive.namelist() for data_name, _ in ARCHIVE_MEMBERS):
            archive = outer_archive
        else:
            nested_bytes = outer_archive.read("UCI HAR Dataset.zip")
            nested_sha256 = hashlib.sha256(nested_bytes).hexdigest()
            archive = zipfile.ZipFile(io.BytesIO(nested_bytes))
            bad_member = archive.testzip()
            if bad_member is not None:
                raise ValueError(f"nested archive CRC failure: {bad_member}")
        for data_name, label_name in ARCHIVE_MEMBERS:
            with archive.open(data_name) as data_stream, archive.open(label_name) as label_stream:
                data_lines = data_stream.read().decode("ascii").splitlines()
                label_lines = label_stream.read().decode("ascii").splitlines()
            if len(data_lines) != len(label_lines):
                raise ValueError(f"row/label mismatch in {data_name}")
            for line, label_line in zip(data_lines, label_lines):
                row = [float(value) for value in line.split()]
                if len(row) != EXPECTED_DIMS:
                    raise ValueError(f"expected {EXPECTED_DIMS} dimensions, found {len(row)}")
                if not all(math.isfinite(value) and -1.001 <= value <= 1.001 for value in row):
                    raise ValueError("UCI HAR input is not finite normalized data")
                label = int(label_line.strip())
                if not 1 <= label <= EXPECTED_CLUSTERS:
                    raise ValueError(f"invalid activity label: {label}")
                rows.append(row)
                labels.append(label - 1)
        if archive is not outer_archive:
            archive.close()
    if len(rows) != EXPECTED_POINTS:
        raise ValueError(f"expected {EXPECTED_POINTS} rows, found {len(rows)}")
    return rows, labels, nested_sha256


def choose_corruption(points, fraction, seed):
    randomizer = random.Random(seed ^ 0xA5A55A5A)
    count = int(points * fraction)
    indices = sorted(randomizer.sample(range(points), count)) if count else []
    split1 = count // 3
    split2 = split1 + count // 3
    types = {}
    for index in indices[:split1]:
        types[index] = "nan"
    for index in indices[split1:split2]:
        types[index] = "null"
    for index in indices[split2:]:
        types[index] = "outlier"
    return indices, types, randomizer


def corrupt_row(row, kind, randomizer):
    result = list(row)
    if kind == "nan":
        result[randomizer.randrange(len(result))] = float("nan")
    elif kind == "null":
        result = [0.0] * len(result)
        result[0] = NULL_SENTINEL
    elif kind == "outlier":
        magnitude = randomizer.uniform(5000.0, 20000.0)
        sign = -1.0 if randomizer.random() < 0.5 else 1.0
        result = [sign * magnitude * (1.0 + dimension * 0.0003) for dimension in range(len(result))]
    return result


def write_dataset(path, rows, seed, corruption_types=None, randomizer=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    header = struct.pack(
        "<8I", DATA_MAGIC, DATA_VERSION, len(rows), EXPECTED_DIMS, seed, 0, 0, 0
    )
    pack_row = struct.Struct("<" + "f" * EXPECTED_DIMS).pack
    with path.open("wb") as stream:
        stream.write(header)
        for index, row in enumerate(rows):
            if corruption_types and index in corruption_types:
                row = corrupt_row(row, corruption_types[index], randomizer)
            stream.write(pack_row(*row))


def write_labels(path, labels):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as stream:
        stream.write(
            struct.pack(
                "<4I", LABEL_MAGIC, LABEL_VERSION, len(labels), EXPECTED_CLUSTERS
            )
        )
        stream.write(struct.pack("<" + "I" * len(labels), *labels))


def file_record(path):
    return {
        "path": path.name,
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def main():
    parser = argparse.ArgumentParser(description="Prepare UCI HAR for PIM-Cleanser")
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--clean-out", required=True, type=Path)
    parser.add_argument("--dirty-out", type=Path)
    parser.add_argument("--labels-out", required=True, type=Path)
    parser.add_argument("--meta-out", required=True, type=Path)
    parser.add_argument("--dirty-frac", type=float, default=0.10)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()

    if not 0.0 <= args.dirty_frac <= 1.0:
        raise SystemExit("dirty-frac must be in [0,1]")
    actual_archive_sha = sha256_file(args.archive)
    if actual_archive_sha.lower() != args.expected_sha256.lower():
        raise SystemExit(
            f"archive checksum mismatch: expected {args.expected_sha256}, got {actual_archive_sha}"
        )

    rows, labels, nested_sha256 = read_archive(args.archive)
    if args.dirty_out is None and args.dirty_frac != 0.0:
        raise SystemExit("--dirty-frac must be zero when --dirty-out is omitted")
    dirty_indices, corruption_types, randomizer = choose_corruption(
        len(rows), args.dirty_frac, args.seed
    )
    write_dataset(args.clean_out, rows, args.seed)
    if args.dirty_out is not None:
        write_dataset(args.dirty_out, rows, args.seed, corruption_types, randomizer)
    write_labels(args.labels_out, labels)

    counts = Counter(corruption_types.values())
    metadata = {
        "schema_version": 1,
        "source": "UCI Human Activity Recognition Using Smartphones",
        "source_url": "https://archive.ics.uci.edu/dataset/240/human%2Bactivity%2Brecognition%2Busing%2Bsmartphones",
        "source_doi": "10.24432/C54S4K",
        "license": "CC BY 4.0",
        "archive": {
            "path": args.archive.name,
            "bytes": args.archive.stat().st_size,
            "sha256": actual_archive_sha,
            "nested_archive_sha256": nested_sha256,
        },
        "points": len(rows),
        "dims": EXPECTED_DIMS,
        "clusters": EXPECTED_CLUSTERS,
        "labels": "activity identifiers 1-6 converted to zero-based 0-5",
        "normalized_range_validated": [-1.001, 1.001],
        "seed": args.seed,
        "dirty_frac_requested": args.dirty_frac,
        "dirty_count": len(dirty_indices),
        "dirty_frac_actual": len(dirty_indices) / len(rows),
        "distribution": {
            "nan": counts.get("nan", 0),
            "null": counts.get("null", 0),
            "outlier": counts.get("outlier", 0),
        },
        "dirty_indices": {
            kind: [index for index in dirty_indices if corruption_types[index] == kind]
            for kind in ("nan", "null", "outlier")
        },
        "files": {
            "clean": file_record(args.clean_out),
            "labels": file_record(args.labels_out),
        },
    }
    if args.dirty_out is not None:
        metadata["files"]["dirty"] = file_record(args.dirty_out)
    args.meta_out.parent.mkdir(parents=True, exist_ok=True)
    args.meta_out.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(
        f"[PASS] UCI HAR rows={len(rows)} dims={EXPECTED_DIMS} dirty={len(dirty_indices)} "
        f"archive_sha256={actual_archive_sha}"
    )


if __name__ == "__main__":
    main()
