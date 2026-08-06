#!/usr/bin/env python3
"""Generate canonical LaTeX data, tables, and numeric macros from result CSVs."""

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
    macros = {
        "QualitySeedCount": next(iter(uci_rows.values()))["seed_count"],
        "UciMeanNmiTen": number(uci_rows[(0.10, "mean")]["nmi_mean"]),
        "UciZeroNmiTen": number(uci_rows[(0.10, "zero")]["nmi_mean"]),
        "UciMeanDriftTen": number(uci_rows[(0.10, "mean")]["centroid_drift_mean"]),
        "UciZeroDriftTen": number(uci_rows[(0.10, "zero")]["centroid_drift_mean"]),
        "UciMeanAggregationTen": number(uci_rows[(0.10, "mean")]["aggregation_error_mean"], 4),
        "UciZeroAggregationTen": number(uci_rows[(0.10, "zero")]["aggregation_error_mean"], 4),
        "UciMeanWcssRatioTen": number(uci_rows[(0.10, "mean")]["wcss_ratio_mean"]),
        "PerformanceRowCount": str(len(performance)),
        "CalibratedPimOverheadFour": number(overhead[("4", "pim-oblivious")]),
        "CalibratedPimOverheadSixtyFour": number(overhead[("64", "pim-oblivious")]),
        "CalibratedPimZeroOverheadFour": number(overhead_zero[("4", "pim-oblivious")]),
    }
    if native:
        ticks = mean_by(native, ("imputation",), "simulator_ticks")
        macros.update(
            {
                "NativeGateStatus": "passed",
                "NativeRowCount": str(len(native)),
                "NativeZeroTicks": number(ticks[("zero",)], 0),
                "NativeMeanTicks": number(ticks[("mean",)], 0),
                "NativeDmaBurstKiB": str(int(native[0]["native_dma_burst_bytes"]) // 1024),
                "NativeComputeLanes": native[0]["native_compute_lanes"],
                "NativePipelineBuffers": native[0]["native_pipeline_buffers"],
            }
        )
    else:
        macros.update(
            {
                "NativeGateStatus": "not used",
                "NativeRowCount": "0",
                "NativeZeroTicks": "--",
                "NativeMeanTicks": "--",
                "NativeDmaBurstKiB": "--",
                "NativeComputeLanes": "--",
                "NativePipelineBuffers": "--",
            }
        )
    macro_text = "\n".join(
        f"\\newcommand{{\\{name}}}{{{value}}}" for name, value in sorted(macros.items())
    ) + "\n"
    (out / "numbers.tex").write_text(macro_text)

    quality_table = [
        "\\begin{tabular}{lrrrr}",
        "\\toprule",
        "Policy & WCSS ratio & Drift & NMI & Agg. error \\\\",
        "\\midrule",
    ]
    for policy in ("none", "zero", "mean"):
        row = uci_rows[(0.10, policy)]
        def cell(field, digits=3):
            if int(row["valid_count"]) == 0:
                return "--"
            value = float(row[field])
            return "--" if not math.isfinite(value) else number(value, digits)
        quality_table.append(
            f"{policy.title()} & {cell('wcss_ratio_mean')} & {cell('centroid_drift_mean')} & "
            f"{cell('nmi_mean')} & {cell('aggregation_error_mean', 4)} \\\\"
        )
    quality_table.extend(("\\bottomrule", "\\end{tabular}"))
    (out / "quality_table.tex").write_text("\n".join(quality_table) + "\n")

    dataset_names = {
        ("synthetic", "balanced"): "Balanced Gaussian",
        ("synthetic", "skewed"): "Skewed/heavy-tailed",
        ("uci_har", "normalized_human_activity"): "UCI HAR",
    }
    dataset_table = [
        "\\begin{tabular}{lrrrl}",
        "\\toprule",
        "Dataset & Records & Features & Labels & Distribution \\\\",
        "\\midrule",
    ]
    for key, label in dataset_names.items():
        row = next(
            item for item in quality
            if (item["dataset"], item["distribution"]) == key
        )
        distribution = {
            "balanced": "Gaussian",
            "skewed": "skewed/$t$-tail",
            "normalized_human_activity": "normalized real",
        }[key[1]]
        dataset_table.append(
            f"{label} & {int(row['points']):,} & {int(row['dims']):,} & "
            f"{int(row['clusters'])} & {distribution} \\\\"
        )
    dataset_table.extend(("\\bottomrule", "\\end{tabular}"))
    (out / "datasets_table.tex").write_text("\n".join(dataset_table) + "\n")

    cross_table = [
        "\\begin{tabular}{llrrrr}",
        "\\toprule",
        "Dataset & Policy & WCSS ratio & Drift & NMI & Agg. error \\\\",
        "\\midrule",
    ]
    for key, label in dataset_names.items():
        for policy in ("zero", "mean"):
            row = next(
                item for item in quality
                if (item["dataset"], item["distribution"]) == key
                and math.isclose(float(item["corruption_requested"]), 0.10)
                and item["policy"] == policy
            )
            cross_table.append(
                f"{label} & {policy.title()} & {number(row['wcss_ratio_mean'])} & "
                f"{number(row['centroid_drift_mean'])} & {number(row['nmi_mean'])} & "
                f"{number(row['aggregation_error_mean'], 4)} \\\\"
            )
    cross_table.extend(("\\bottomrule", "\\end{tabular}"))
    (out / "quality_cross_table.tex").write_text("\n".join(cross_table) + "\n")

    matrix_table = [
        "\\begin{tabular}{ll}",
        "\\toprule",
        "Dimension & Values \\\\",
        "\\midrule",
        "Actual size (MiB) & " + ", ".join(sorted({row["target_mib"] for row in performance}, key=int)) + " \\\\",
        "Corruption (\\%) & " + ", ".join(
            f"{100 * value:g}" for value in sorted({float(row["corruption_rate"]) for row in performance})
        ) + " \\\\",
        "Seeds & " + ", ".join(sorted({row["seed"] for row in performance}, key=int)) + " \\\\",
        "Features & " + ", ".join(sorted({row["dims"] for row in performance}, key=int)) + " \\\\",
        "Clusters & " + ", ".join(sorted({row["clusters"] for row in performance}, key=int)) + " \\\\",
        "Hybrid block (KiB) & " + ", ".join(
            f"{value // 1024}" for value in sorted({int(row["block_bytes"]) for row in performance if int(row["block_bytes"])})
        ) + " \\\\",
        "Workloads & aggregation, fixed-20 $k$-means \\\\",
        "Repair & zero, per-feature mean \\\\",
        "\\bottomrule",
        "\\end{tabular}",
    ]
    (out / "matrix_table.tex").write_text("\n".join(matrix_table) + "\n")

    mode_counts = defaultdict(int)
    for row in performance:
        mode_counts[row["cleaning_mode"]] += 1
    evidence = {
        "off": ("baseline", "none"),
        "host-conditional": ("leaky control", "varies"),
        "host-branchless": ("fixed candidate", "equal"),
        "pim-oblivious": ("fixed candidate", "equal"),
        "hybrid-sparse": ("leaky control", "varies"),
        "hybrid-oblivious": ("fixed candidate", "equal"),
    }
    mode_table = [
        "\\begin{tabular}{lrrl}",
        "\\toprule",
        "Mode & Rows & Schedule result & Evidence role \\\\",
        "\\midrule",
    ]
    for mode in ("off", "host-conditional", "host-branchless", "pim-oblivious", "hybrid-sparse", "hybrid-oblivious"):
        role, trace = evidence[mode]
        mode_table.append(f"{mode} & {mode_counts[mode]:,} & {trace} & {role} \\\\")
    mode_table.extend(("\\bottomrule", "\\end{tabular}"))
    (out / "mode_evidence_table.tex").write_text("\n".join(mode_table) + "\n")

    if native:
        native_table = [
            "\\begin{tabular}{lrrrrrr}",
            "\\toprule",
            "Policy & DMA bytes & 64-B packets & Actions & Polls & gem5 ticks \\\\",
            "\\midrule",
        ]
        for policy in ("zero", "mean"):
            row = next(item for item in native if item["imputation"] == policy)
            native_table.append(
                f"{policy} & {int(row['simulator_dma_bytes']):,} & "
                f"{int(row['visible_reads']) + int(row['visible_writes']):,} & "
                f"{int(row['dma_action_count']):,} & "
                f"{int(row['status_polls']):,} & {int(row['simulator_ticks'])} \\\\"
            )
        native_table.extend(("\\bottomrule", "\\end{tabular}"))
        (out / "native_table.tex").write_text("\n".join(native_table) + "\n")
    else:
        native_table = [
            "\\begin{tabular}{lll}",
            "\\toprule",
            "Field & Status & Value \\\\",
            "\\midrule",
            "Native CSV & not supplied & -- \\\\",
            "Gate status & not used & -- \\\\",
            "gem5 ticks & placeholder & -- \\\\",
            "\\bottomrule",
            "\\end{tabular}",
        ]
        (out / "native_table.tex").write_text("\n".join(native_table) + "\n")

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
