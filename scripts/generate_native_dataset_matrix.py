#!/usr/bin/env python3
"""Generate a checksum-pinned native experiment dataset matrix.

The native full-system runner needs datasets inside the guest image before its
checkpoint is created.  This wrapper records the otherwise separate generation
commands and artifacts so a later ``--reuse-datasets`` run retains complete
provenance.
"""

import argparse
import hashlib
import json
import os
import platform
import re
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "scripts" / "corrupt_dataset.py"
DEFAULT_OUTPUT_ROOT = (
    ROOT / "IMPICA" / "workloads" / "kmeans_sepim_fs" / "data"
)
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def artifact(path):
    resolved = path.resolve()
    try:
        shown = str(resolved.relative_to(ROOT))
    except ValueError:
        shown = str(resolved)
    return {
        "path": shown,
        "bytes": resolved.stat().st_size,
        "sha256": sha256_file(resolved),
    }


def git_value(directory, *args):
    result = subprocess.run(
        ["git", *args],
        cwd=directory,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else "unavailable"


def rate_tag(rate):
    percent = rate * 100.0
    rounded = round(percent)
    if abs(percent - rounded) > 1e-9 or rounded < 0 or rounded > 100:
        raise ValueError(
            f"rate {rate} cannot be represented by the runner's integer-percent tag"
        )
    return f"{int(rounded):03d}"


def main():
    parser = argparse.ArgumentParser(
        description="Generate and provenance-pin a native dataset matrix"
    )
    parser.add_argument("--dataset-id", required=True)
    parser.add_argument("--points", required=True, type=int)
    parser.add_argument("--dims", required=True, type=int)
    parser.add_argument("--clusters", required=True, type=int)
    parser.add_argument("--seeds", nargs="+", type=int, default=(7, 19, 42))
    parser.add_argument(
        "--rates", nargs="+", type=float, default=(0.0, 0.01, 0.10, 0.40)
    )
    parser.add_argument("--distribution", default="balanced")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()

    if not ID_RE.fullmatch(args.dataset_id):
        raise SystemExit(f"invalid dataset ID: {args.dataset_id!r}")
    if args.points <= 0 or args.dims <= 0 or args.clusters <= 1:
        raise SystemExit("points/dims must be positive and clusters must exceed one")
    if len(set(args.seeds)) != len(args.seeds) or any(seed < 0 for seed in args.seeds):
        raise SystemExit("seeds must be unique non-negative integers")
    if len(set(args.rates)) != len(args.rates) or any(
        rate < 0.0 or rate > 1.0 for rate in args.rates
    ):
        raise SystemExit("rates must be unique values in [0,1]")
    try:
        tags = [rate_tag(rate) for rate in args.rates]
    except ValueError as error:
        raise SystemExit(str(error)) from error
    if len(set(tags)) != len(tags):
        raise SystemExit("rates produce duplicate runner filename tags")
    if not GENERATOR.is_file():
        raise SystemExit(f"dataset generator is missing: {GENERATOR}")

    output_root = args.output_root.resolve()
    data_dir = output_root / args.dataset_id
    if data_dir.exists():
        raise SystemExit(f"refusing to overwrite dataset directory: {data_dir}")
    data_dir.mkdir(parents=True)
    manifest_path = (
        args.manifest.resolve()
        if args.manifest is not None
        else data_dir / "dataset_generation_manifest.json"
    )
    if manifest_path.exists():
        raise SystemExit(f"refusing to overwrite manifest: {manifest_path}")

    started = datetime.now(timezone.utc)
    commands = []
    generated = []
    try:
        for seed in args.seeds:
            for rate, tag in zip(args.rates, tags):
                stem = f"s{seed:03d}_r{tag}"
                clean = data_dir / f"{stem}_clean.bin"
                dirty = data_dir / f"{stem}_dirty.bin"
                labels = data_dir / f"{stem}_labels.bin"
                metadata = data_dir / f"{stem}.json"
                command = [
                    sys.executable,
                    str(GENERATOR),
                    "--clean-out",
                    str(clean),
                    "--dirty-out",
                    str(dirty),
                    "--labels-out",
                    str(labels),
                    "--meta-out",
                    str(metadata),
                    "--points",
                    str(args.points),
                    "--dims",
                    str(args.dims),
                    "--clusters",
                    str(args.clusters),
                    "--seed",
                    str(seed),
                    "--dirty-frac",
                    str(rate),
                    "--distribution",
                    args.distribution,
                ]
                commands.append(shlex.join(command))
                subprocess.run(command, cwd=ROOT, check=True)
                for path in (clean, dirty, labels, metadata):
                    if not path.is_file():
                        raise RuntimeError(f"generator did not create {path}")
                    generated.append(artifact(path))

        document = {
            "schema_version": 1,
            "dataset_id": args.dataset_id,
            "started_utc": started.isoformat(),
            "finished_utc": datetime.now(timezone.utc).isoformat(),
            "parameters": {
                "points": args.points,
                "dims": args.dims,
                "clusters": args.clusters,
                "seeds": args.seeds,
                "rates": args.rates,
                "distribution": args.distribution,
            },
            "generator": artifact(GENERATOR),
            "wrapper": artifact(Path(__file__)),
            "python": {
                "executable": sys.executable,
                "version": platform.python_version(),
            },
            "top_commit": git_value(ROOT, "rev-parse", "HEAD"),
            "impica_commit": git_value(ROOT / "IMPICA", "rev-parse", "HEAD"),
            "commands": commands,
            "outputs": generated,
        }
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = manifest_path.with_name(
            f".{manifest_path.name}.tmp.{os.getpid()}"
        )
        temporary.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, manifest_path)
    except BaseException:
        # Preserve completed generator outputs for forensic inspection, but
        # never emit a manifest that could be mistaken for a complete matrix.
        raise

    print(
        f"[PASS] generated groups={len(args.seeds) * len(args.rates)} "
        f"files={len(generated)} data_dir={data_dir} manifest={manifest_path}"
    )


if __name__ == "__main__":
    main()
