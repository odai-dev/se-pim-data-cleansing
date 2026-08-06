#!/usr/bin/env python3
"""Generate the transparent, gem5-calibrated PIM-Cleanser performance matrix.

This is an analytical functional model, never a native gem5 result.  Its memory
transaction latency is calibrated from the fixed-transcript native gate and the
SE-PIM controlled-access formula.  Compute work is reported from explicit,
public-shape operation-count assumptions.
"""

import argparse
import csv
import functools
import hashlib
import json
import math
import random
import statistics
import struct
import subprocess
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODES = (
    "off",
    "host-conditional",
    "host-branchless",
    "pim-oblivious",
    "hybrid-sparse",
    "hybrid-oblivious",
)
SECURE_MODES = {"host-branchless", "pim-oblivious", "hybrid-oblivious"}
LEAKY_MODES = {"host-conditional", "hybrid-sparse"}
FREQUENCY_HZ = 1_000_000_000
PIM_CORES = 16
PIM_CLEANER_VECTOR_WIDTH = 4
PIM_CLEANER_LANES = PIM_CORES * PIM_CLEANER_VECTOR_WIDTH
HEADER_BYTES = 32
GEM5_TICKS_PER_SECOND = 1_000_000_000_000
NATIVE_REFERENCE_BYTES = 256 * 1024
NATIVE_DMA_BURST_BYTES = 128 * 1024
NATIVE_ZERO_TICKS = 1_165_250
NATIVE_MEAN_TICKS = 2_513_000
NATIVE_DEVICE_CLOCK_TICKS = 1_000
NATIVE_PIPELINE_BUFFERS = 2
MODEL_VERSION = "functional-calibrated-v4-native-pipeline2-vector4-burst128k"
CALIBRATION_SOURCE = "IMPICA/gem5/src/dev/arm/pimDevice_hashtable.cc"
NATIVE_CALIBRATION_CSV = "results/csv/native_clean_pipeline2c_full_20260714.csv"


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def file_sha256(path):
    return sha256_bytes(path.read_bytes())


def git_value(cwd, *args):
    result = subprocess.run(
        ["git", *args], cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
    )
    return result.stdout.strip() if result.returncode == 0 else "unavailable"


def source_digest():
    paths = (
        ROOT / CALIBRATION_SOURCE,
        ROOT / "IMPICA/workloads/kmeans_sepim_fs/pim_cleaner.c",
        ROOT / "IMPICA/workloads/kmeans_sepim_fs/host_cleaner.c",
        Path(__file__),
    )
    digest = hashlib.sha256()
    for path in paths:
        digest.update(str(path.relative_to(ROOT)).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


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


def controlled_access_cycles(byte_count):
    # Exact SecAccessData formula, including AES-GCM 16-byte chunks.
    return 90000 + (byte_count * 13) // 10 + (byte_count + 15) // 16


def validate_native_calibration():
    path = ROOT / NATIVE_CALIBRATION_CSV
    if not path.is_file():
        raise RuntimeError(f"missing native calibration CSV: {path}")
    with path.open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) != 24:
        raise RuntimeError(f"expected 24 native calibration rows, found {len(rows)}")
    expected_ticks = {"zero": NATIVE_ZERO_TICKS, "mean": NATIVE_MEAN_TICKS}
    for policy, ticks in expected_ticks.items():
        group = [row for row in rows if row["imputation"] == policy]
        if len(group) != 12 or {int(row["simulator_ticks"]) for row in group} != {ticks}:
            raise RuntimeError(f"native calibration tick mismatch for {policy}")
        for field, expected in (
            ("native_dma_burst_bytes", NATIVE_DMA_BURST_BYTES),
            ("native_compute_lanes", PIM_CLEANER_LANES),
            ("native_pipeline_buffers", NATIVE_PIPELINE_BUFFERS),
        ):
            if {int(row[field]) for row in group} != {expected}:
                raise RuntimeError(f"native calibration {field} mismatch for {policy}")
        if {
            int(row["points"]) * int(row["dims"]) * 4 for row in group
        } != {NATIVE_REFERENCE_BYTES}:
            raise RuntimeError(f"native calibration byte shape mismatch for {policy}")
    return path


def public_trace_digest(mode, policy, points, dims, block_bytes, reads, writes, byte_count):
    descriptor = (
        f"v1|{mode}|{policy}|{points}|{dims}|{block_bytes}|{reads}|{writes}|{byte_count}"
    )
    return sha256_bytes(descriptor.encode())[:16]


def secret_trace_digest(public_digest, values):
    digest = hashlib.sha256(public_digest.encode())
    for value in values:
        digest.update(struct.pack("<Q", value))
    return digest.hexdigest()[:16]


@functools.lru_cache(maxsize=1)
def dirty_layout(points, fraction, seed):
    count = int(points * fraction)
    randomizer = random.Random(seed ^ 0xA5A55A5A)
    return tuple(sorted(randomizer.sample(range(points), count))) if count else ()


def workload_cycles(points, dims, clusters, workload, iterations):
    if workload == "kmeans":
        # Per point/cluster/feature: subtract, multiply, accumulate; plus centroid update.
        operations = iterations * (3 * points * clusters * dims + 2 * points * dims)
    else:
        # Sum and count each feature once.
        operations = 2 * points * dims
    return math.ceil(operations / PIM_CORES)


def repair_cycles(dirty_count, dims):
    nan_count = dirty_count // 3
    null_count = dirty_count // 3
    outlier_count = dirty_count - nan_count - null_count
    return (
        nan_count * (18 + dims * 8)
        + null_count * (14 + dims * 5)
        + outlier_count * (16 + dims * 6)
    )


def fixed_clean_cycles(points, dims, policy):
    features = points * dims
    scan = features * (18 if policy == "mean" else 8) + points * 12
    clean = features * 12 + points * 10
    return scan, clean


def pim_oblivious_cycles(data_bytes, features, dims, policy):
    """Scale measured DMA and fixed-lane compute, including zero-policy overlap."""
    passes = 2 if policy == "mean" else 1
    reference_ticks = NATIVE_MEAN_TICKS if policy == "mean" else NATIVE_ZERO_TICKS
    reference_features = NATIVE_REFERENCE_BYTES // 4
    reference_compute_ticks = (
        passes * math.ceil(reference_features / PIM_CLEANER_LANES)
        * NATIVE_DEVICE_CLOCK_TICKS
    )
    reference_dma_ticks = reference_ticks - reference_compute_ticks
    if reference_dma_ticks <= 0:
        raise RuntimeError("native calibration implies non-positive DMA time")
    if policy == "zero":
        # The two-chunk native gate directly measures a two-buffer pipeline.
        # Compute is the bottleneck, so only the first public read and final
        # unconditional write remain outside the overlapped steady state.
        record_bytes = dims * 4
        chunk_bytes = (NATIVE_DMA_BURST_BYTES // record_bytes) * record_bytes
        if chunk_bytes <= 0:
            raise RuntimeError("public record exceeds the native DMA buffer")
        remaining = data_bytes
        chunk_values = []
        while remaining:
            current = min(remaining, chunk_bytes)
            chunk_values.append(current // 4)
            remaining -= current
        scan_cycles = sum(
            math.ceil(values / PIM_CLEANER_LANES) for values in chunk_values
        )
        clean_cycles = 0
        edge_bytes = (chunk_values[0] + chunk_values[-1]) * 4
        dma_cycles = math.ceil(
            reference_dma_ticks * edge_bytes * FREQUENCY_HZ
            / (2 * NATIVE_DMA_BURST_BYTES * GEM5_TICKS_PER_SECOND)
        )
    else:
        per_pass_compute = math.ceil(features / PIM_CLEANER_LANES)
        scan_cycles = per_pass_compute
        clean_cycles = per_pass_compute
        dma_cycles = math.ceil(
            reference_dma_ticks * data_bytes * FREQUENCY_HZ
            / (NATIVE_REFERENCE_BYTES * GEM5_TICKS_PER_SECOND)
        )
    return scan_cycles, clean_cycles, dma_cycles


def sparse_blocks(dirty_indices, points_per_block):
    if not dirty_indices:
        return []
    return sorted({index // points_per_block for index in dirty_indices})


@functools.lru_cache(maxsize=5)
def cached_sparse_blocks(points, fraction, seed, points_per_block):
    return tuple(sparse_blocks(dirty_layout(points, fraction, seed), points_per_block))


def model_row(size_mib, fraction, seed, dims, clusters, workload, mode, block_bytes, policy):
    target_bytes = size_mib * 1024 * 1024
    point_bytes = dims * 4
    points = (target_bytes - HEADER_BYTES) // point_bytes
    data_bytes = points * point_bytes
    actual_bytes = HEADER_BYTES + data_bytes
    dirty_indices = dirty_layout(points, fraction, seed)
    dirty_count = len(dirty_indices)
    scan_cycles = 0
    clean_cycles = 0
    access_cycles = 0
    visible_reads = 0
    visible_writes = 0
    visible_bytes = 0
    padded_bytes = 0
    dma_action_reads = 0
    dma_action_writes = 0
    trace_values = []

    if mode in ("host-conditional", "hybrid-sparse"):
        scan_cycles = points * (24 + dims * 6)

    if mode == "host-conditional":
        visible_reads = points
        visible_writes = dirty_count
        visible_bytes = (visible_reads + visible_writes) * point_bytes
        access_cycles = visible_reads * controlled_access_cycles(point_bytes)
        access_cycles += visible_writes * controlled_access_cycles(point_bytes)
        clean_cycles = repair_cycles(dirty_count, dims)
        trace_values = dirty_indices
    elif mode == "host-branchless":
        scan_cycles, clean_cycles = fixed_clean_cycles(points, dims, policy)
        visible_reads = points
        visible_writes = points
        visible_bytes = 2 * data_bytes
        access_cycles = 2 * points * controlled_access_cycles(point_bytes)
    elif mode == "pim-oblivious":
        scan_cycles, clean_cycles, access_cycles = pim_oblivious_cycles(
            data_bytes, points * dims, dims, policy
        )
        cache_lines = math.ceil(data_bytes / 64)
        burst_count = math.ceil(data_bytes / NATIVE_DMA_BURST_BYTES)
        read_passes = 2 if policy == "mean" else 1
        visible_reads = cache_lines * read_passes
        visible_writes = cache_lines
        visible_bytes = data_bytes * (read_passes + 1)
        dma_action_reads = burst_count * read_passes
        dma_action_writes = burst_count
    elif mode in ("hybrid-sparse", "hybrid-oblivious"):
        points_per_block = max(1, block_bytes // point_bytes)
        total_blocks = math.ceil(points / points_per_block)
        if mode == "hybrid-sparse":
            blocks = cached_sparse_blocks(points, fraction, seed, points_per_block)
            clean_cycles = dirty_count * (28 + dims * 8) // 4
            trace_values = blocks
        else:
            blocks = range(total_blocks)
            fixed_scan, fixed_clean = fixed_clean_cycles(points, dims, policy)
            clean_cycles = (fixed_scan + fixed_clean) // 4
        visible_reads = len(blocks)
        visible_writes = len(blocks)
        for block in blocks:
            start = block * points_per_block
            actual_points = min(points_per_block, points - start)
            actual_block_bytes = actual_points * point_bytes
            transfer_bytes = math.ceil(actual_block_bytes / block_bytes) * block_bytes
            visible_bytes += transfer_bytes * 2
            padded_bytes += (transfer_bytes - actual_block_bytes) * 2
            access_cycles += 2 * controlled_access_cycles(transfer_bytes)

    cleaning_completion_cycles = scan_cycles + clean_cycles + access_cycles
    compute_cycles = workload_cycles(points, dims, clusters, workload, 20)
    total_cycles = cleaning_completion_cycles + compute_cycles
    public_digest = public_trace_digest(
        mode, policy, points, dims, block_bytes, visible_reads, visible_writes, visible_bytes
    )
    trace_digest = (
        secret_trace_digest(public_digest, trace_values) if mode in LEAKY_MODES else public_digest
    )
    cleaning_sec = cleaning_completion_cycles / FREQUENCY_HZ
    workload_sec = compute_cycles / FREQUENCY_HZ
    total_sec = total_cycles / FREQUENCY_HZ
    baseline_sec = workload_sec
    return {
        "model_kind": "functional_calibrated",
        "model_version": MODEL_VERSION,
        "cleaning_mode": mode,
        "imputation": policy,
        "workload": workload,
        "target_mib": size_mib,
        "actual_bytes": actual_bytes,
        "actual_mib": actual_bytes / (1024 * 1024),
        "corruption_rate": fraction,
        "seed": seed,
        "dims": dims,
        "clusters": clusters,
        "iterations": 20,
        "pim_cores": PIM_CORES,
        "pim_cleaner_vector_width": PIM_CLEANER_VECTOR_WIDTH,
        "pim_cleaner_lanes": PIM_CLEANER_LANES,
        "native_dma_burst_bytes": NATIVE_DMA_BURST_BYTES if mode == "pim-oblivious" else 0,
        "native_pipeline_buffers": NATIVE_PIPELINE_BUFFERS if mode == "pim-oblivious" else 0,
        "block_bytes": block_bytes,
        "points": points,
        "dirty_count_internal": dirty_count,
        "scan_cycles": scan_cycles,
        "clean_compute_cycles": clean_cycles,
        "access_cycles": access_cycles,
        "completion_cycles": cleaning_completion_cycles,
        "workload_cycles": compute_cycles,
        "total_cycles": total_cycles,
        "cleaning_sec": cleaning_sec,
        "workload_sec": workload_sec,
        "runtime_sec": total_sec,
        "overhead_pct": ((total_sec / baseline_sec) - 1) * 100 if baseline_sec else 0,
        "visible_reads": visible_reads,
        "visible_writes": visible_writes,
        "transaction_count": visible_reads + visible_writes + (1 if mode == "pim-oblivious" else 0),
        "dma_action_reads": dma_action_reads,
        "dma_action_writes": dma_action_writes,
        "dma_action_count": dma_action_reads + dma_action_writes,
        "transferred_bytes": visible_bytes,
        "padding_bytes": padded_bytes,
        "throughput_mib_s": (data_bytes / (1024 * 1024) / cleaning_sec) if cleaning_sec else 0,
        "trace_digest": trace_digest,
    }


def pearson(xs, ys):
    xmean = statistics.fmean(xs)
    ymean = statistics.fmean(ys)
    numerator = sum((x - xmean) * (y - ymean) for x, y in zip(xs, ys))
    denominator = math.sqrt(
        sum((x - xmean) ** 2 for x in xs) * sum((y - ymean) ** 2 for y in ys)
    )
    return numerator / denominator if denominator else 0.0


def validate_security(rows):
    secure_groups = defaultdict(list)
    leaky_groups = defaultdict(list)
    for row in rows:
        key = (
            row["cleaning_mode"], row["imputation"], row["workload"], row["target_mib"],
            row["dims"], row["clusters"], row["block_bytes"],
        )
        if row["cleaning_mode"] in SECURE_MODES:
            secure_groups[key].append(row)
        elif row["cleaning_mode"] in LEAKY_MODES:
            leaky_groups[key].append(row)

    fields = (
        "transaction_count", "transferred_bytes", "padding_bytes", "completion_cycles", "trace_digest"
    )
    failures = []
    for key, group in secure_groups.items():
        for field in fields:
            if len({row[field] for row in group}) != 1:
                failures.append({"group": key, "field": field})

    correlations = []
    for key, group in leaky_groups.items():
        rate_means = defaultdict(list)
        for row in group:
            rate_means[row["corruption_rate"]].append(row)
        rates = sorted(rate_means)
        transactions = [statistics.fmean(r["transaction_count"] for r in rate_means[x]) for x in rates]
        completions = [statistics.fmean(r["completion_cycles"] for r in rate_means[x]) for x in rates]
        correlations.append(
            {
                "group": key,
                "transaction_rate_correlation": pearson(rates, transactions),
                "completion_rate_correlation": pearson(rates, completions),
                "distinct_transaction_means": len(set(transactions)),
                "distinct_completion_means": len(set(completions)),
                "transactions_monotonic": all(
                    current <= following for current, following in zip(transactions, transactions[1:])
                ),
                "completion_monotonic": all(
                    current <= following for current, following in zip(completions, completions[1:])
                ),
            }
        )
    transaction_max_by_mode = {
        mode: max(
            item["transaction_rate_correlation"]
            for item in correlations if item["group"][0] == mode
        )
        for mode in LEAKY_MODES
    }
    completion_max_by_mode = {
        mode: max(
            item["completion_rate_correlation"]
            for item in correlations if item["group"][0] == mode
        )
        for mode in LEAKY_MODES
    }
    dependency_failures = [
        item for item in correlations
        if item["distinct_completion_means"] < 2 or not item["completion_monotonic"]
    ]
    if (
        failures
        or dependency_failures
        or any(value < 0.8 for value in transaction_max_by_mode.values())
        or any(value < 0.8 for value in completion_max_by_mode.values())
    ):
        raise RuntimeError(
            f"security validation failed: fixed={failures[:3]} "
            f"dependency={dependency_failures[:3]} transaction_max={transaction_max_by_mode} "
            f"completion_max={completion_max_by_mode}"
        )
    return {
        "secure_modes": sorted(SECURE_MODES),
        "secure_group_count": len(secure_groups),
        "secure_trace_equality": "pass",
        "leaky_modes": sorted(LEAKY_MODES),
        "leaky_group_count": len(leaky_groups),
        "minimum_transaction_rate_correlation": min(
            item["transaction_rate_correlation"] for item in correlations
        ),
        "minimum_completion_rate_correlation": min(
            item["completion_rate_correlation"] for item in correlations
        ),
        "maximum_transaction_rate_correlation_by_mode": transaction_max_by_mode,
        "maximum_completion_rate_correlation_by_mode": completion_max_by_mode,
        "transaction_saturation_note": (
            "Large sparse blocks can touch every block by 1% corruption, so transaction counts "
            "saturate; completion time remains dirty-count-dependent."
        ),
        "correlations": correlations,
    }


def write_csv(path, rows):
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def summarize(rows):
    groups = defaultdict(list)
    for row in rows:
        key = tuple(
            row[field]
            for field in (
                "model_kind", "cleaning_mode", "imputation", "workload", "target_mib",
                "dims", "clusters", "block_bytes", "corruption_rate",
            )
        )
        groups[key].append(row)
    output = []
    for key, group in sorted(groups.items(), key=lambda item: tuple(map(str, item[0]))):
        base = dict(zip(
            ("model_kind", "cleaning_mode", "imputation", "workload", "target_mib",
             "dims", "clusters", "block_bytes", "corruption_rate"), key
        ))
        for field in ("runtime_sec", "overhead_pct", "transaction_count", "transferred_bytes",
                      "padding_bytes", "completion_cycles", "throughput_mib_s"):
            values = [float(row[field]) for row in group]
            base[f"{field}_mean"] = statistics.fmean(values)
            base[f"{field}_std"] = statistics.stdev(values) if len(values) > 1 else 0.0
        base["seed_count"] = len(group)
        output.append(base)
    return output


def main():
    parser = argparse.ArgumentParser(description="Run calibrated PIM-Cleanser matrix")
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--run-id", help="unique output identifier (auto-generated by default)")
    args = parser.parse_args()
    native_calibration_path = validate_native_calibration()
    if args.quick:
        sizes, rates, seeds = (4,), (0.01, 0.40), (7, 19)
        dims_values, cluster_values = (4, 32), (4, 16)
        blocks = (1024, 16384, 131072)
    else:
        sizes, rates, seeds = (4, 16, 64), (0.01, 0.10, 0.40), (7, 19, 42)
        dims_values, cluster_values = (4, 8, 32, 64), (4, 8, 16)
        blocks = (1024, 4096, 16384, 65536, 131072)

    started = datetime.now(timezone.utc)
    run_id = args.run_id or (
        f"performance_{'quick' if args.quick else 'full'}_{time.strftime('%Y%m%d_%H%M%S')}"
    )
    raw_dir = ROOT / "results/raw" / run_id
    csv_dir = ROOT / "results/csv"
    raw_dir.mkdir(parents=True, exist_ok=True)
    csv_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for size_mib in sizes:
        for fraction in rates:
            for seed in seeds:
                for dims in dims_values:
                    for clusters in cluster_values:
                        for workload in ("kmeans", "aggregate"):
                            for policy in ("zero", "mean"):
                                for mode in MODES:
                                    mode_blocks = blocks if mode.startswith("hybrid-") else (0,)
                                    for block_bytes in mode_blocks:
                                        rows.append(model_row(
                                            size_mib, fraction, seed, dims, clusters, workload,
                                            mode, block_bytes, policy,
                                        ))

    individual_path = csv_dir / f"{run_id}.csv"
    summary_path = csv_dir / f"{run_id}_summary.csv"
    validation_path = raw_dir / "security_validation.json"
    write_csv(individual_path, rows)
    write_csv(summary_path, summarize(rows))
    validation = validate_security(rows)
    validation_path.write_text(json.dumps(validation, indent=2, default=str) + "\n")
    manifest = {
        "schema_version": 1,
        "run_id": run_id,
        "started_utc": started.isoformat(),
        "finished_utc": datetime.now(timezone.utc).isoformat(),
        "command": " ".join(__import__("sys").argv),
        "model_kind": "functional_calibrated",
        "model_version": MODEL_VERSION,
        "warning": "Analytical model; values are not native gem5 execution ticks.",
        "calibration": {
            "source": CALIBRATION_SOURCE,
            "source_sha256": file_sha256(ROOT / CALIBRATION_SOURCE),
            "controlled_access_cycles": "90000 + floor(bytes*13/10) + ceil(bytes/16)",
            "frequency_hz": FREQUENCY_HZ,
            "pim_cores": PIM_CORES,
            "pim_cleaner_vector_width": PIM_CLEANER_VECTOR_WIDTH,
            "pim_cleaner_lanes": PIM_CLEANER_LANES,
            "native_dma_burst_bytes": NATIVE_DMA_BURST_BYTES,
            "native_pipeline_buffers": NATIVE_PIPELINE_BUFFERS,
            "native_reference_bytes": NATIVE_REFERENCE_BYTES,
            "native_zero_ticks": NATIVE_ZERO_TICKS,
            "native_mean_ticks": NATIVE_MEAN_TICKS,
            "native_csv": str(native_calibration_path.relative_to(ROOT)),
            "native_csv_sha256": file_sha256(native_calibration_path),
            "compute_assumption": (
                "one fp32 validation/select per vector lane-cycle; four lanes on each of "
                "16 modeled PIM cores"
            ),
            "overlap_assumption": (
                "zero repair uses the directly gated two-buffer pipeline; its first read "
                "and final unconditional write are outside the compute-dominated steady state"
            ),
        },
        "parameters": {
            "sizes_mib": sizes, "rates": rates, "seeds": seeds, "dims": dims_values,
            "clusters": cluster_values, "blocks": blocks, "iterations": 20,
            "workloads": ["kmeans", "aggregate"], "modes": MODES,
            "imputation": ["zero", "mean"],
        },
        "top_commit": git_value(ROOT, "rev-parse", "HEAD"),
        "impica_commit": git_value(ROOT / "IMPICA", "rev-parse", "HEAD"),
        "source_digest": source_digest(),
        "source_diff_digest": source_diff_digest(),
        "checkpoint": "results/raw/gate3_postbuild_checkpoint_20260301",
        "docker_image": "sepim-impica@sha256:e5caacbf042ea2c2dd87a350ca35467d09aec2c0e4fac2a1de728bb1a93f308a",
        "rows": len(rows),
        "individual_csv": str(individual_path.relative_to(ROOT)),
        "summary_csv": str(summary_path.relative_to(ROOT)),
        "security_validation": str(validation_path.relative_to(ROOT)),
    }
    (raw_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"[PASS] rows={len(rows)} csv={individual_path}")
    print(
        "[PASS] secure transcript equality; leaky correlation ranges "
        f"transactions={validation['minimum_transaction_rate_correlation']:.6f}.."
        f"{max(validation['maximum_transaction_rate_correlation_by_mode'].values()):.6f} "
        f"completion={validation['minimum_completion_rate_correlation']:.6f}.."
        f"{max(validation['maximum_completion_rate_correlation_by_mode'].values()):.6f}"
    )


if __name__ == "__main__":
    main()
