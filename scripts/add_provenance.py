#!/usr/bin/env python3

import argparse
import csv
import os
import tempfile


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--source", default="gem5_fs")
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--mode", required=True)
    ap.add_argument("--checkpoint-dir", required=True)
    ap.add_argument("--gem5-commit", required=True)
    ap.add_argument("--impica-commit", required=True)
    args = ap.parse_args()

    with open(args.input, "r", newline="") as f:
        rows = list(csv.DictReader(f))
        fields = list(rows[0].keys()) if rows else []

    extra_fields = [
        "source",
        "run_id",
        "mode",
        "checkpoint_dir",
        "gem5_commit",
        "impica_commit",
    ]
    out_fields = fields + [f for f in extra_fields if f not in fields]

    fd, tmp_path = tempfile.mkstemp(prefix="prov_", suffix=".csv", dir=os.path.dirname(args.input) or ".")
    os.close(fd)
    try:
        with open(tmp_path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=out_fields)
            w.writeheader()
            for row in rows:
                row["source"] = args.source
                row["run_id"] = args.run_id
                row["mode"] = args.mode
                row["checkpoint_dir"] = args.checkpoint_dir
                row["gem5_commit"] = args.gem5_commit
                row["impica_commit"] = args.impica_commit
                w.writerow(row)
        os.chmod(tmp_path, 0o644)
        os.replace(tmp_path, args.input)
        os.chmod(args.input, 0o644)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


if __name__ == "__main__":
    main()
