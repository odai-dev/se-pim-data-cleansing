#!/usr/bin/env python3
"""Validate the event-driven gem5 PIM cleaner against fixed-transcript gates."""

import argparse
import csv
import hashlib
import io
import json
import os
import re
import shlex
import subprocess
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKLOAD = ROOT / "IMPICA" / "workloads" / "kmeans_sepim_fs"
PINNED_IMAGE = "sepim-impica@sha256:e5caacbf042ea2c2dd87a350ca35467d09aec2c0e4fac2a1de728bb1a93f308a"
DEVICE_HEADER = ROOT / "IMPICA" / "gem5" / "src" / "dev" / "arm" / "pimDevice_hashtable.hh"


def device_constant(name):
    text = DEVICE_HEADER.read_text()
    match = re.search(rf"static const int {re.escape(name)}\s*=\s*([^;]+);", text)
    if not match:
        raise RuntimeError(f"missing native device constant {name}")
    expression = match.group(1).strip()
    if not re.fullmatch(r"[0-9+*() /\t-]+", expression):
        raise RuntimeError(f"unsafe native device constant expression: {name}={expression}")
    value = eval(expression, {"__builtins__": {}}, {})
    if not isinstance(value, int) or value <= 0:
        raise RuntimeError(f"invalid native device constant: {name}={value}")
    return value


def run(command, *, env=None, capture=False):
    printable = " ".join(shlex.quote(str(value)) for value in command)
    print(f"[RUN] {printable}", flush=True)
    return subprocess.run(
        [str(value) for value in command],
        cwd=ROOT,
        env=env,
        check=True,
        universal_newlines=True,
        stdout=subprocess.PIPE if capture else None,
    )


def git_value(repo, *args):
    result = subprocess.run(
        ["git", *args], cwd=repo, universal_newlines=True,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
    )
    return result.stdout.strip() if result.returncode == 0 else "unavailable"


def source_diff_digest():
    digest = hashlib.sha256()
    for repo in (ROOT, ROOT / "IMPICA"):
        for args in (("diff", "--binary"), ("status", "--short")):
            result = subprocess.run(
                ["git", *args], cwd=repo, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
            )
            digest.update(str(repo).encode())
            digest.update(result.stdout)
    return digest.hexdigest()


def extract_rows(terminal):
    text = terminal.read_bytes().replace(b"\0", b"").decode("utf-8", "ignore").replace("\r", "")
    rows = []
    block = []
    collecting = False
    for line in text.splitlines():
        if line.strip() == "FSCSV_BEGIN":
            collecting = True
            block = []
        elif line.strip() == "FSCSV_END":
            if block:
                rows.extend(csv.DictReader(io.StringIO("\n".join(block) + "\n")))
            collecting = False
            block = []
        elif collecting:
            block.append(line)
    return rows


def validate(rows, expected_rows):
    if len(rows) != expected_rows:
        raise RuntimeError(f"expected {expected_rows} native rows, found {len(rows)}")
    for row in rows:
        if row["model_kind"] != "gem5_native_candidate_cleaning":
            raise RuntimeError(f"unexpected model kind: {row['model_kind']}")
        if int(row["simulator_ticks"]) <= 0 or int(row["status_polls"]) <= 0:
            raise RuntimeError("native row lacks positive simulator ticks or status polls")
        if int(row["simulator_dma_bytes"]) != int(row["visible_bytes"]):
            raise RuntimeError("device DMA byte count differs from public transcript")
        if int(row["dma_action_count"]) != (
            int(row["dma_action_reads"]) + int(row["dma_action_writes"])
        ):
            raise RuntimeError("native DMA action count is inconsistent")

    groups = defaultdict(list)
    for row in rows:
        key = (row["imputation"], row["points"], row["dims"])
        groups[key].append(row)
    fixed_fields = (
        "visible_reads",
        "visible_writes",
        "visible_bytes",
        "simulator_dma_bytes",
        "simulator_ticks",
        "status_polls",
        "trace_digest",
        "native_dma_burst_bytes",
        "native_compute_lanes",
        "native_pipeline_buffers",
        "dma_action_reads",
        "dma_action_writes",
        "dma_action_count",
    )
    for key, group in groups.items():
        for field in fixed_fields:
            values = {row[field] for row in group}
            if len(values) != 1:
                raise RuntimeError(f"native transcript mismatch group={key} field={field}: {values}")
    return {
        "status": "pass",
        "property": "equal public shape implies equal DMA trace, ticks, and status polls",
        "groups": len(groups),
        "rows": len(rows),
        "fixed_fields": fixed_fields,
    }


def main():
    started = datetime.now(timezone.utc)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint-dir", type=Path, required=True)
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--points", type=int)
    parser.add_argument("--dims", type=int, default=8)
    parser.add_argument("--run-id")
    parser.add_argument(
        "--dataset-id",
        help="guest data directory name (defaults to run ID)",
    )
    parser.add_argument(
        "--reuse-datasets",
        action="store_true",
        help="reuse pre-generated files from --dataset-id instead of overwriting them",
    )
    parser.add_argument(
        "--skip-disk-prepare",
        action="store_true",
        help="do not mutate the disk image after restoring a dataset-pinned checkpoint",
    )
    args = parser.parse_args()

    native_dma_burst_bytes = device_constant("NativeDmaSize")
    native_compute_lanes = device_constant("NativeComputeLanes")
    native_pipeline_buffers = device_constant("NativePipelineBuffers")

    checkpoint = args.checkpoint_dir.resolve()
    if not checkpoint.is_dir() or not list(checkpoint.glob("cpt.*")):
        raise SystemExit(f"checkpoint missing cpt.* directories: {checkpoint}")
    points = args.points or (512 if args.quick else 8192)
    rates = (0.0, 0.10, 0.40) if args.quick else (0.0, 0.01, 0.10, 0.40)
    seeds = (7, 19) if args.quick else (7, 19, 42)
    policies = ("zero", "mean")
    run_id = args.run_id or "native_clean_%s_%s" % (
        "quick" if args.quick else "full", time.strftime("%Y%m%d_%H%M%S")
    )
    dataset_id = args.dataset_id or run_id
    raw_dir = ROOT / "results" / "raw" / run_id
    csv_path = ROOT / "results" / "csv" / f"{run_id}.csv"
    data_dir = WORKLOAD / "data" / dataset_id
    terminal = raw_dir / "system.terminal"
    cases_dir = raw_dir / "cases"
    raw_dir.mkdir(parents=True, exist_ok=False)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    if args.reuse_datasets:
        if not data_dir.is_dir():
            raise SystemExit(f"reused dataset directory does not exist: {data_dir}")
    else:
        data_dir.mkdir(parents=True, exist_ok=False)

    commands = []
    datasets = []
    for seed in seeds:
        for rate in rates:
            rate_tag = int(round(rate * 100))
            stem = f"s{seed}_r{rate_tag:02d}"
            clean = data_dir / f"{stem}_clean.bin"
            dirty = data_dir / f"{stem}_dirty.bin"
            labels = data_dir / f"{stem}_labels.bin"
            metadata = data_dir / f"{stem}.json"
            if args.reuse_datasets:
                for required in (clean, dirty, labels, metadata):
                    if not required.is_file():
                        raise SystemExit(f"missing reused dataset file: {required}")
                existing = json.loads(metadata.read_text())
                if (
                    int(existing["points"]) != points
                    or int(existing["dims"]) != args.dims
                    or int(existing["seed"]) != seed
                    or abs(float(existing["dirty_frac_requested"]) - rate) > 1e-12
                ):
                    raise SystemExit(f"reused dataset metadata mismatch: {metadata}")
                commands.append(f"reuse checksum-pinned dataset {dirty.relative_to(ROOT)}")
            else:
                command = [
                    sys.executable,
                    ROOT / "scripts" / "corrupt_dataset.py",
                    "--clean-out", clean,
                    "--dirty-out", dirty,
                    "--labels-out", labels,
                    "--meta-out", metadata,
                    "--points", points,
                    "--dims", args.dims,
                    "--clusters", 6,
                    "--seed", seed,
                    "--dirty-frac", rate,
                    "--distribution", "balanced",
                ]
                commands.append(" ".join(shlex.quote(str(value)) for value in command))
                run(command)
            datasets.append((dirty, rate, seed, metadata))

    run(["make", "-C", WORKLOAD, "clean", "all"])
    binary_kind = run(["file", WORKLOAD / "kmeans_sepim_fs"], capture=True).stdout
    if "ARM aarch64" not in binary_kind:
        raise RuntimeError(f"workload is not AArch64: {binary_kind.strip()}")
    if not args.skip_disk_prepare:
        run([ROOT / "scripts" / "prepare_disk_image.sh"])

    # Restore the same checkpoint for every case.  Running all cases in one
    # guest makes status-poll counts depend on public OS timer/preemption state
    # left by earlier cases, so those executions do not begin from equal public
    # machine states and cannot be used for the transcript-equality gate.
    guest_prefix = [
        "#!/bin/sh",
        "set -ex",
        "cd /home/pim_driver",
        "mknod /dev/pimbt c 70 0 || true",
        "insmod ./test-driver.ko || { echo '[GUEST][ERROR] insmod failed'; m5 exit; exit 1; }",
        "chmod 600 /dev/pimbt",
        "cd /home/workloads/kmeans_sepim_fs",
    ]
    rows = []
    case_terminals = []
    cases_dir.mkdir()
    for dirty, rate, seed, _metadata in datasets:
        guest_path = Path("./data") / dataset_id / dirty.name
        for policy in policies:
            rate_tag = int(round(rate * 100))
            case_id = f"s{seed}_r{rate_tag:02d}_{policy}"
            case_dir = cases_dir / case_id
            case_terminal = case_dir / "system.terminal"
            guest_script = raw_dir / f"guest_{case_id}.rcS"
            command = (
                f"./kmeans_sepim_fs --quick --cleaning=pim-oblivious --native-pim=1 "
                f"--dataset={guest_path} --corruption={rate} --seed={seed} "
                f"--imputation={policy} --outlier-threshold=8 --iterations=20 --clusters=6"
            )
            guest_lines = guest_prefix + [
                f"{command} || {{ echo '[GUEST][ERROR] native cleaner failed'; m5 exit; exit 1; }}",
                "m5 exit",
            ]
            guest_script.write_text("\n".join(guest_lines) + "\n")
            guest_script.chmod(0o755)
            commands.append(command)

            env = os.environ.copy()
            env.update(
                {
                    "OUTDIR": str(case_dir),
                    "BOOT_SCRIPT": str(guest_script),
                    "GEM5_EXTRA_ARGS": f"-r 1 --checkpoint-dir={checkpoint}",
                    "MEM_SIZE": "2048MB",
                    "SEPIM_KERNEL_MEM": "1984MB",
                }
            )
            run([ROOT / "scripts" / "run_baseline_fs.sh", "--mode", "custom"], env=env)
            if not case_terminal.is_file():
                raise RuntimeError(f"missing terminal output: {case_terminal}")
            case_rows = extract_rows(case_terminal)
            if len(case_rows) != 1:
                raise RuntimeError(
                    f"expected one native row for {case_id}, found {len(case_rows)}"
                )
            for row in case_rows:
                data_bytes = int(row["points"]) * int(row["dims"]) * 4
                chunks = (data_bytes + native_dma_burst_bytes - 1) // native_dma_burst_bytes
                read_passes = 2 if row["imputation"] == "mean" else 1
                row.update(
                    {
                        "native_dma_burst_bytes": native_dma_burst_bytes,
                        "native_compute_lanes": native_compute_lanes,
                        "native_pipeline_buffers": native_pipeline_buffers,
                        "dma_action_reads": chunks * read_passes,
                        "dma_action_writes": chunks,
                        "dma_action_count": chunks * (read_passes + 1),
                    }
                )
            rows.extend(case_rows)
            case_terminals.append(case_terminal)

    # Keep a human-readable aggregate alongside the per-case primary logs.
    with terminal.open("wb") as aggregate:
        for case_terminal in case_terminals:
            aggregate.write(
                (f"\n===== {case_terminal.parent.name} =====\n").encode("utf-8")
            )
            aggregate.write(case_terminal.read_bytes())
    validation = validate(rows, len(datasets) * len(policies))
    with csv_path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    dataset_metadata = [json.loads(metadata.read_text()) for *_rest, metadata in datasets]
    manifest = {
        "schema_version": 1,
        "run_id": run_id,
        "started_utc": started.isoformat(),
        "finished_utc": datetime.now(timezone.utc).isoformat(),
        "model_kind": "gem5_native_candidate_cleaning",
        "scope": "native cleaning ticks plus separately calibrated downstream workload",
        "case_isolation": "each row restored from the identical checkpoint and public machine state",
        "checkpoint": str(checkpoint.relative_to(ROOT)),
        "docker_image": os.environ.get("IMAGE_NAME", PINNED_IMAGE),
        "top_commit": git_value(ROOT, "rev-parse", "HEAD"),
        "impica_commit": git_value(ROOT / "IMPICA", "rev-parse", "HEAD"),
        "source_diff_digest": source_diff_digest(),
        "parameters": {
            "points": points,
            "dims": args.dims,
            "rates": rates,
            "seeds": seeds,
            "native_dma_burst_bytes": native_dma_burst_bytes,
            "native_compute_lanes": native_compute_lanes,
            "native_pipeline_buffers": native_pipeline_buffers,
            "cache_line_bytes": 64,
        },
        "dataset_id": dataset_id,
        "reused_checkpoint_pinned_datasets": args.reuse_datasets,
        "disk_prepare_skipped": args.skip_disk_prepare,
        "dataset_files": [metadata["files"] for metadata in dataset_metadata],
        "commands": commands,
        "result_csv": str(csv_path.relative_to(ROOT)),
        "terminal": str(terminal.relative_to(ROOT)),
        "case_terminals": [str(path.relative_to(ROOT)) for path in case_terminals],
        "validation": validation,
    }
    (raw_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"[PASS] native gate rows={len(rows)} csv={csv_path}")


if __name__ == "__main__":
    main()
