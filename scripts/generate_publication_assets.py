#!/usr/bin/env python3
"""Generate canonical publication CSV datasets from result CSVs."""

import argparse
import csv
import hashlib
import json
import math
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def rows(path):
    with path.open(newline="") as stream:
        return list(csv.DictReader(stream))


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def number(value, digits=3):
    return f"{float(value):.{digits}f}"


def write_csv(path, fieldnames, data):
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(data)


def display_path(path, evidence_root):
    resolved = path.resolve()
    for base in (evidence_root.resolve(), ROOT.resolve()):
        try:
            return resolved.relative_to(base).as_posix()
        except ValueError:
            continue
    return resolved.as_posix()


def mean_by(items, key_fields, value_field):
    groups = defaultdict(list)
    for item in items:
        groups[tuple(item[field] for field in key_fields)].append(float(item[value_field]))
    return {key: statistics.fmean(values) for key, values in groups.items()}


def exact(items, **criteria):
    output = []
    for item in items:
        if all(str(item[key]) == str(value) for key, value in criteria.items()):
            output.append(item)
    return output


def validate_native(items):
    """Reject native CSVs that did not satisfy the publication trace gate."""
    if not items:
        return
    required = {
        "cleaning_mode", "imputation", "model_kind", "points", "dims",
        "visible_reads", "visible_writes", "visible_bytes",
        "simulator_dma_bytes", "simulator_ticks", "status_polls",
        "trace_digest", "native_dma_burst_bytes", "native_compute_lanes",
        "native_pipeline_buffers",
        "dma_action_reads", "dma_action_writes", "dma_action_count",
    }
    missing = required.difference(items[0])
    if missing:
        raise SystemExit(f"native CSV lacks required fields: {sorted(missing)}")
    groups = defaultdict(list)
    for item in items:
        if item["model_kind"] != "gem5_native_e2e_kmeans":
            raise SystemExit(f"ineligible native model kind: {item['model_kind']}")
        if item["cleaning_mode"] not in ["off", "pim-oblivious"]:
            raise SystemExit(f"ineligible native cleaning mode: {item['cleaning_mode']}")
        if int(item["simulator_ticks"]) <= 0 or int(item["status_polls"]) <= 0:
            raise SystemExit("native CSV contains non-positive ticks or polls")
        if int(item["simulator_dma_bytes"]) != int(item["visible_bytes"]):
            raise SystemExit("native DMA bytes differ from the public transcript")
        groups[(item["cleaning_mode"], item["imputation"], item["points"], item["dims"])].append(item)
    fixed = (
        "visible_reads", "visible_writes", "visible_bytes",
        "simulator_dma_bytes", "simulator_ticks", "status_polls",
        "trace_digest", "native_dma_burst_bytes", "native_compute_lanes",
        "native_pipeline_buffers",
        "dma_action_reads", "dma_action_writes", "dma_action_count",
    )
    for key, group in groups.items():
        for field in fixed:
            values = {item[field] for item in group}
            if len(values) != 1:
                raise SystemExit(
                    f"native trace gate failed for group={key}, field={field}: {values}"
                )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quality", type=Path, required=True, help="quality summary CSV")
    parser.add_argument("--performance", type=Path, required=True, help="individual performance CSV")
    parser.add_argument("--native", type=Path, help="optional native gem5 CSV")
    parser.add_argument("--out-dir", type=Path, default=ROOT / "paper" / "generated")
    parser.add_argument(
        "--evidence-root",
        type=Path,
        default=ROOT,
        help="base used for display paths in the generated manifest",
    )
    args = parser.parse_args()
    out = args.out_dir
    out.mkdir(parents=True, exist_ok=True)
    quality = rows(args.quality)

    from collections import defaultdict
    quality_groups = defaultdict(list)
    for row in quality:
        group_key = (row["dataset"], row.get("distribution", ""), row["corruption_requested"], row["policy"])
        quality_groups[group_key].append(row)

    for row in quality:
        group_key = (row["dataset"], row.get("distribution", ""), row["corruption_requested"], row["policy"])
        group = quality_groups[group_key]
        row["valid_count"] = len(group)
        row["seed_count"] = len(group)
        for key in ["wcss_ratio", "centroid_drift", "nmi", "aggregation_error"]:
            if all(key in r for r in group):
                row[key + "_mean"] = sum(float(r[key]) for r in group) / len(group)
    performance = rows(args.performance)
    native = rows(args.native) if args.native else []
    validate_native(native)

    quality_plot = []
    for rate in (0.0, 0.01, 0.05, 0.10, 0.20, 0.40):
        row = exact(
            quality,
            dataset="uci_har",
            corruption_requested=str(rate),
            policy="mean",
        )
        if row:
            quality_plot.append(
                {
                    "rate_pct": rate * 100,
                    "wcss_ratio": row[0]["wcss_ratio_mean"],
                    "centroid_drift": row[0]["centroid_drift_mean"],
                    "nmi": row[0]["nmi_mean"],
                    "aggregation_error": row[0]["aggregation_error_mean"],
                }
            )
    write_csv(
        out / "quality_uci_mean.csv",
        ("rate_pct", "wcss_ratio", "centroid_drift", "nmi", "aggregation_error"),
        quality_plot,
    )

    selected = [
        row for row in performance
        if int(row["target_mib"]) == 4
        and int(row["dims"]) == 8
        and int(row["clusters"]) == 8
        and row["workload"] == "aggregate"
        and row["imputation"] == "mean"
        and (
            (row["cleaning_mode"] in ("host-conditional", "pim-oblivious") and int(row["block_bytes"]) == 0)
            or (row["cleaning_mode"] in ("hybrid-sparse", "hybrid-oblivious") and int(row["block_bytes"]) == 4096)
        )
    ]
    completion = mean_by(selected, ("corruption_rate", "cleaning_mode"), "completion_cycles")
    transactions = mean_by(selected, ("corruption_rate", "cleaning_mode"), "transaction_count")
    leakage_plot = []
    mode_columns = {
        "host-conditional": "hostconditional",
        "hybrid-sparse": "hybridsparse",
        "pim-oblivious": "pimoblivious",
        "hybrid-oblivious": "hybridoblivious",
    }
    rates = sorted({float(row["corruption_rate"]) for row in selected})
    for rate in rates:
        item = {"rate_pct": rate * 100}
        for mode, column in mode_columns.items():
            item[f"{column}_cycles"] = completion[(str(rate), mode)]
            item[f"{column}_transactions"] = transactions[(str(rate), mode)]
        leakage_plot.append(item)
    leakage_fields = ["rate_pct"] + [
        f"{column}_{metric}"
        for column in mode_columns.values()
        for metric in ("cycles", "transactions")
    ]
    write_csv(out / "leakage.csv", leakage_fields, leakage_plot)

    overhead_selected = [
        row for row in performance
        if math.isclose(float(row["corruption_rate"]), 0.10)
        and int(row["dims"]) == 32
        and int(row["clusters"]) == 8
        and row["workload"] == "kmeans"
        and row["imputation"] == "mean"
        and (
            (not row["cleaning_mode"].startswith("hybrid-") and int(row["block_bytes"]) == 0)
            or (row["cleaning_mode"].startswith("hybrid-") and int(row["block_bytes"]) == 16384)
        )
    ]
    overhead = mean_by(overhead_selected, ("target_mib", "cleaning_mode"), "overhead_pct")
    overhead_zero_selected = [
        row for row in performance
        if math.isclose(float(row["corruption_rate"]), 0.10)
        and int(row["dims"]) == 32
        and int(row["clusters"]) == 8
        and row["workload"] == "kmeans"
        and row["imputation"] == "zero"
        and row["cleaning_mode"] == "pim-oblivious"
        and int(row["block_bytes"]) == 0
    ]
    overhead_zero = mean_by(
        overhead_zero_selected, ("target_mib", "cleaning_mode"), "overhead_pct"
    )
    overhead_plot = []
    modes = ("host-conditional", "host-branchless", "pim-oblivious", "hybrid-sparse", "hybrid-oblivious")
    for size in (4, 16, 64):
        item = {"size_mib": size}
        for mode in modes:
            item[mode.replace("-", "")] = overhead[(str(size), mode)]
        overhead_plot.append(item)
    write_csv(
        out / "overhead.csv",
        ["size_mib"] + [mode.replace("-", "") for mode in modes],
        overhead_plot,
    )

    hybrid_block_selected = [
        row for row in performance
        if int(row["target_mib"]) == 4
        and math.isclose(float(row["corruption_rate"]), 0.10)
        and int(row["dims"]) == 32
        and int(row["clusters"]) == 8
        and int(row["iterations"]) == 20
        and row["workload"] == "kmeans"
        and row["imputation"] == "mean"
        and row["cleaning_mode"] in ("hybrid-sparse", "hybrid-oblivious")
    ]
    hybrid_block_overhead = mean_by(
        hybrid_block_selected, ("block_bytes", "cleaning_mode"), "overhead_pct"
    )
    hybrid_block_runtime = mean_by(
        hybrid_block_selected, ("block_bytes", "cleaning_mode"), "runtime_sec"
    )
    hybrid_block_throughput = mean_by(
        hybrid_block_selected, ("block_bytes", "cleaning_mode"), "throughput_mib_s"
    )
    hybrid_block_plot = []
    for block_bytes in (1024, 4096, 16384, 65536, 131072):
        block_key = str(block_bytes)
        hybrid_block_plot.append({
            "block_kib": block_bytes // 1024,
            "hybrid_sparse_overhead": hybrid_block_overhead[
                (block_key, "hybrid-sparse")
            ],
            "hybrid_oblivious_overhead": hybrid_block_overhead[
                (block_key, "hybrid-oblivious")
            ],
            "hybrid_oblivious_runtime_sec": hybrid_block_runtime[
                (block_key, "hybrid-oblivious")
            ],
            "hybrid_oblivious_throughput_mib_s": hybrid_block_throughput[
                (block_key, "hybrid-oblivious")
            ],
        })
    write_csv(
        out / "hybrid_block.csv",
        [
            "block_kib", "hybrid_sparse_overhead", "hybrid_oblivious_overhead",
            "hybrid_oblivious_runtime_sec", "hybrid_oblivious_throughput_mib_s",
        ],
        hybrid_block_plot,
    )

    uci_rows = {
        (float(row["corruption_requested"]), row["policy"]): row
        for row in quality if row["dataset"] == "uci_har"
    }
    write_csv(
        out / "policy_tradeoff.csv",
        ("policy_id", "overhead_pct", "aggregation_error"),
        (
            {
                "policy_id": 1,
                "overhead_pct": overhead_zero[("4", "pim-oblivious")],
                "aggregation_error": uci_rows[(0.10, "zero")]["aggregation_error_mean"],
            },
            {
                "policy_id": 2,
                "overhead_pct": overhead[("4", "pim-oblivious")],
                "aggregation_error": uci_rows[(0.10, "mean")]["aggregation_error_mean"],
            },
        ),
    )

    phase_candidates = [
        (1, "pim-oblivious", 0),
        (2, "hybrid-oblivious", 1024),
        (3, "hybrid-oblivious", 16384),
        (4, "hybrid-oblivious", 131072),
    ]
    phase_selected = [
        row for row in performance
        if int(row["target_mib"]) == 4
        and math.isclose(float(row["corruption_rate"]), 0.10)
        and int(row["dims"]) == 32
        and int(row["clusters"]) == 8
        and int(row["iterations"]) == 20
        and row["workload"] == "kmeans"
        and row["imputation"] == "mean"
    ]
    phase_plot = []
    for case_id, mode, block_bytes in phase_candidates:
        case = [
            row for row in phase_selected
            if row["cleaning_mode"] == mode
            and int(row["block_bytes"]) == block_bytes
        ]
        phase_plot.append({
            "case_id": case_id,
            "scan_sec": statistics.fmean(float(row["scan_cycles"]) for row in case) / 1e9,
            "clean_sec": statistics.fmean(float(row["clean_compute_cycles"]) for row in case) / 1e9,
            "access_sec": statistics.fmean(float(row["access_cycles"]) for row in case) / 1e9,
            "workload_sec": statistics.fmean(float(row["workload_cycles"]) for row in case) / 1e9,
        })
    write_csv(
        out / "phase_breakdown.csv",
        ("case_id", "scan_sec", "clean_sec", "access_sec", "workload_sec"),
        phase_plot,
    )

    manifest_inputs = {
        display_path(args.quality, args.evidence_root): sha256(args.quality),
        display_path(args.performance, args.evidence_root): sha256(args.performance),
    }
    if args.native:
        manifest_inputs[display_path(args.native, args.evidence_root)] = sha256(args.native)
    outputs = sorted(path for path in out.iterdir() if path.name != "manifest.json")
    manifest = {
        "schema_version": 1,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "inputs": manifest_inputs,
        "outputs": {path.name: sha256(path) for path in outputs},
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"[PASS] publication assets generated under {out}")


if __name__ == "__main__":
    main()
