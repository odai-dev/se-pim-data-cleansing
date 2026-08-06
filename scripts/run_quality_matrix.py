#!/usr/bin/env python3

import argparse
import csv
import hashlib
import json
import math
import statistics
import subprocess
import sys
import time
from pathlib import Path
from datetime import datetime, timezone


ROOT = Path(__file__).resolve().parents[1]
WORKLOAD = ROOT / "IMPICA" / "workloads" / "kmeans_sepim_fs"


def run(command, capture=False):
    print("[RUN]", " ".join(map(str, command)), flush=True)
    return subprocess.run(
        list(map(str, command)),
        cwd=ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE if capture else None,
    )


def source_digest():
    h = hashlib.sha256()
    paths = [
        WORKLOAD / "pim_cleaner.c",
        WORKLOAD / "pim_cleaner.h",
        WORKLOAD / "quality_eval.c",
        ROOT / "scripts" / "corrupt_dataset.py",
        ROOT / "scripts" / "prepare_uci_har.py",
        ROOT / "scripts" / "corrupt_existing_dataset.py",
        Path(__file__),
    ]
    for path in paths:
        h.update(str(path.relative_to(ROOT)).encode())
        h.update(path.read_bytes())
    return h.hexdigest()


def git_value(cwd, *args):
    result = subprocess.run(
        ["git", *args], cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
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


def quality_summary(rows):
    groups = {}
    for row in rows:
        key = (
            row["dataset"], row["distribution"], row["corruption_requested"], row["policy"],
            row["points"], row["dims"], row["clusters"], row["iterations"], row["threshold"],
        )
        groups.setdefault(key, []).append(row)
    output = []
    metrics = (
        "dirty_remaining", "wcss", "wcss_ratio", "centroid_drift", "nmi", "aggregation_error"
    )
    keys = (
        "dataset", "distribution", "corruption_requested", "policy", "points", "dims",
        "clusters", "iterations", "threshold",
    )
    for key, group in sorted(groups.items(), key=lambda item: tuple(map(str, item[0]))):
        result = dict(zip(keys, key))
        result["seed_count"] = len(group)
        result["valid_count"] = sum(int(row["quality_valid"]) for row in group)
        for metric in metrics:
            values = [float(row[metric]) for row in group if math.isfinite(float(row[metric]))]
            result[f"{metric}_mean"] = statistics.fmean(values) if values else float("nan")
            result[f"{metric}_std"] = statistics.stdev(values) if len(values) > 1 else 0.0
        output.append(result)
    return output


def write_csv(path, rows):
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def validate_quality(rows):
    failures = []
    for row in rows:
        rate = float(row["corruption_requested"])
        policy = row["policy"]
        if policy in ("zero", "mean"):
            if int(row["dirty_remaining"]) != 0 or int(row["quality_valid"]) != 1:
                failures.append({"kind": "repair", "row": row})
        if rate == 0.0:
            identity = (
                float(row["wcss_ratio"]) == 1.0
                and float(row["centroid_drift"]) == 0.0
                and float(row["aggregation_error"]) == 0.0
            )
            if not identity:
                failures.append({"kind": "clean_identity", "row": row})
        elif policy == "none":
            if int(row["dirty_remaining"]) == 0 or int(row["quality_valid"]) != 0:
                failures.append({"kind": "uncleaned_control", "row": row})
    if failures:
        raise RuntimeError(f"quality validation failed: {failures[:3]}")
    return {
        "status": "pass",
        "rows": len(rows),
        "clean_input_identity": True,
        "supported_anomalies_repaired": True,
        "uncleaned_corrupted_controls_invalid": True,
    }


def evaluate(clean, dirty, labels, policy, clusters, iterations, threshold):
    result = run(
        [
            WORKLOAD / "quality_eval",
            f"--clean={clean}",
            f"--candidate={dirty}",
            f"--labels={labels}",
            f"--policy={policy}",
            f"--clusters={clusters}",
            f"--iterations={iterations}",
            f"--threshold={threshold}",
        ],
        capture=True,
    )
    rows = list(csv.DictReader(result.stdout.splitlines()))
    if len(rows) != 1:
        raise RuntimeError("quality evaluator did not return exactly one row")
    return rows[0]


def main():
    started = datetime.now(timezone.utc)
    parser = argparse.ArgumentParser(description="Run reproducible PIM-Cleanser quality matrix")
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--points", type=int)
    parser.add_argument("--dims", type=int, default=8)
    parser.add_argument("--clusters", type=int, default=6)
    parser.add_argument("--iterations", type=int, default=20)
    parser.add_argument("--threshold", type=float, default=8.0)
    parser.add_argument("--uci-threshold", type=float, default=1.001)
    parser.add_argument("--uci-archive", type=Path)
    parser.add_argument("--uci-sha256")
    parser.add_argument("--run-id", help="unique output identifier (auto-generated by default)")
    args = parser.parse_args()

    if args.quick:
        rates = (0.0, 0.10, 0.40)
        seeds = (7, 19)
        points = args.points or 4096
    else:
        rates = (0.0, 0.01, 0.05, 0.10, 0.20, 0.40)
        seeds = (7, 19, 42, 73, 101)
        points = args.points or 131072

    run_id = args.run_id or "quality_%s_%s" % (
        "quick" if args.quick else "full", time.strftime("%Y%m%d_%H%M%S")
    )
    raw_dir = ROOT / "results" / "raw" / run_id
    data_dir = raw_dir / "data"
    csv_path = ROOT / "results" / "csv" / f"{run_id}.csv"
    summary_path = ROOT / "results" / "csv" / f"{run_id}_summary.csv"
    manifest_path = raw_dir / "manifest.json"
    validation_path = raw_dir / "quality_validation.json"
    data_dir.mkdir(parents=True, exist_ok=True)
    csv_path.parent.mkdir(parents=True, exist_ok=True)

    run(["make", "-C", WORKLOAD, "host-quality"])
    rows = []
    commands = []
    for distribution in ("balanced", "skewed"):
        for seed in seeds:
            for rate in rates:
                stem = f"{distribution}_s{seed}_r{int(round(rate * 100)):02d}"
                clean = data_dir / f"{stem}_clean.bin"
                dirty = data_dir / f"{stem}_dirty.bin"
                labels = data_dir / f"{stem}_labels.bin"
                meta = data_dir / f"{stem}.json"
                command = [
                    sys.executable,
                    ROOT / "scripts" / "corrupt_dataset.py",
                    "--clean-out", clean,
                    "--dirty-out", dirty,
                    "--meta-out", meta,
                    "--labels-out", labels,
                    "--points", points,
                    "--dims", args.dims,
                    "--dirty-frac", rate,
                    "--seed", seed,
                    "--clusters", args.clusters,
                    "--distribution", distribution,
                ]
                commands.append(" ".join(map(str, command)))
                run(command)
                metadata = json.loads(meta.read_text())
                for policy in ("none", "zero", "mean"):
                    row = evaluate(
                        clean, dirty, labels, policy, args.clusters, args.iterations, args.threshold
                    )
                    row.update(
                        {
                            "dataset": "synthetic",
                            "distribution": distribution,
                            "corruption_requested": rate,
                            "corruption_actual": metadata["dirty_frac_actual"],
                            "seed": seed,
                            "threshold": args.threshold,
                            "clean_sha256": metadata["files"]["clean"]["sha256"],
                            "dirty_sha256": metadata["files"]["dirty"]["sha256"],
                            "labels_sha256": metadata["files"]["labels"]["sha256"],
                        }
                    )
                    rows.append(row)

    if args.uci_archive:
        if not args.uci_sha256:
            raise SystemExit("--uci-sha256 is required with --uci-archive")
        uci_dir = data_dir / "uci_har_base"
        uci_clean = uci_dir / "uci_har_clean.bin"
        uci_labels = uci_dir / "uci_har_labels.bin"
        uci_meta = uci_dir / "uci_har_base.json"
        base_command = [
            sys.executable,
            ROOT / "scripts" / "prepare_uci_har.py",
            "--archive", args.uci_archive,
            "--expected-sha256", args.uci_sha256,
            "--clean-out", uci_clean,
            "--labels-out", uci_labels,
            "--meta-out", uci_meta,
            "--dirty-frac", 0,
            "--seed", 7,
        ]
        commands.append(" ".join(map(str, base_command)))
        run(base_command)
        base_metadata = json.loads(uci_meta.read_text())
        for seed in seeds:
            for rate in rates:
                stem = f"uci_har_s{seed}_r{int(round(rate * 100)):02d}"
                dirty = data_dir / f"{stem}_dirty.bin"
                meta = data_dir / f"{stem}.json"
                command = [
                    sys.executable,
                    ROOT / "scripts" / "corrupt_existing_dataset.py",
                    "--clean", uci_clean,
                    "--dirty-out", dirty,
                    "--meta-out", meta,
                    "--base-meta", uci_meta,
                    "--dirty-frac", rate,
                    "--seed", seed,
                ]
                commands.append(" ".join(map(str, command)))
                run(command)
                metadata = json.loads(meta.read_text())
                for policy in ("none", "zero", "mean"):
                    row = evaluate(
                        uci_clean, dirty, uci_labels, policy, 6, args.iterations, args.uci_threshold
                    )
                    row.update(
                        {
                            "dataset": "uci_har",
                            "distribution": "normalized_human_activity",
                            "corruption_requested": rate,
                            "corruption_actual": metadata["dirty_frac_actual"],
                            "seed": seed,
                            "threshold": args.uci_threshold,
                            "clean_sha256": base_metadata["files"]["clean"]["sha256"],
                            "dirty_sha256": metadata["files"]["dirty"]["sha256"],
                            "labels_sha256": base_metadata["files"]["labels"]["sha256"],
                        }
                    )
                    rows.append(row)

    write_csv(csv_path, rows)
    write_csv(summary_path, quality_summary(rows))
    validation = validate_quality(rows)
    validation_path.write_text(json.dumps(validation, indent=2) + "\n")

    manifest = {
        "schema_version": 1,
        "run_id": run_id,
        "started_utc": started.isoformat(),
        "finished_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "quick" if args.quick else "full",
        "model_kind": "host_native_quality",
        "source_digest": source_digest(),
        "source_diff_digest": source_diff_digest(),
        "top_commit": git_value(ROOT, "rev-parse", "HEAD"),
        "impica_commit": git_value(ROOT / "IMPICA", "rev-parse", "HEAD"),
        "checkpoint": "results/raw/gate3_postbuild_checkpoint_20260301",
        "docker_image": "sepim-impica@sha256:e5caacbf042ea2c2dd87a350ca35467d09aec2c0e4fac2a1de728bb1a93f308a",
        "parameters": {
            key: str(value) if isinstance(value, Path) else value
            for key, value in vars(args).items()
        },
        "rates": rates,
        "seeds": seeds,
        "rows": len(rows),
        "result_csv": str(csv_path.relative_to(ROOT)),
        "summary_csv": str(summary_path.relative_to(ROOT)),
        "quality_validation": str(validation_path.relative_to(ROOT)),
        "commands": commands,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"[PASS] rows={len(rows)} csv={csv_path} manifest={manifest_path}")


if __name__ == "__main__":
    main()
