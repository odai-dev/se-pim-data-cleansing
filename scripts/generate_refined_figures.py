#!/usr/bin/env python3
"""
Generate publication-grade, high-DPI figures for IEEE two-column paper format.
Resolves reviewer feedback:
- Crystal-clear details and text (proper 8-10 pt font in single-column 3.5" width).
- Zero label/legend overlaps.
- High resolution (600 DPI) for DOCX and PDF inclusion.
- Clean, uncluttered layout matching the original paper style.
"""

import csv
from pathlib import Path
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import numpy as np

# Set global IEEE publication style
plt.rcParams['font.family'] = 'serif'
plt.rcParams['font.serif'] = ['Liberation Serif', 'Times New Roman', 'DejaVu Serif']
plt.rcParams['mathtext.fontset'] = 'stix'
plt.rcParams['axes.titlesize'] = 10
plt.rcParams['axes.labelsize'] = 9.5
plt.rcParams['xtick.labelsize'] = 8.5
plt.rcParams['ytick.labelsize'] = 8.5
plt.rcParams['legend.fontsize'] = 8.0
plt.rcParams['figure.titlesize'] = 10

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "paper" / "generated"
OUT_DIR = ROOT / "paper" / "refined_figures"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def read_csv(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def generate_figure1():
    """Fig. 1: PIM-Cleanser Execution Flow (Architecture Flowchart)"""
    fig, ax = plt.subplots(figsize=(3.5, 4.3), dpi=600)
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.axis("off")

    steps = [
        (8, 85, 84, 11, "Confidential Dirty Dataset", "NaNs, Null Sentinels (-999999.0f), & Outliers", "data"),
        (8, 69, 84, 11, "Host Enclave Issues LOCK_MEM", "External bus & CPU-side mappings blocked", "host"),
        (5, 48, 90, 16, "PIM Engine Executes pim_cleaner", "Sequential scan, branchless detection, & in-place repair\nFixed schedule & invariant memory writes", "pim"),
        (8, 33, 84, 11, "Validation Decisions Confined to PIM", "Security Guarantee: Observable trace is strictly invariant", "security"),
        (8, 17, 84, 11, "PIM Core Executes Compute Kernel", "Sanitized data feeds downstream workload (e.g., k-means)", "compute"),
        (8, 1, 84, 11, "Host Receives Result & Issues UNLOCK_MEM", "Enclave receives output; normal memory access restored", "host")
    ]

    colors = {
        "data": {"edge": "#2b5c8f", "face": "#f0f4f8", "lw": 1.2, "ls": "-"},
        "host": {"edge": "#4a5568", "face": "#f7fafc", "lw": 1.2, "ls": "-"},
        "pim": {"edge": "#1a365d", "face": "#ebf8ff", "lw": 2.0, "ls": "-"},
        "security": {"edge": "#c53030", "face": "#fff5f5", "lw": 1.4, "ls": "--"},
        "compute": {"edge": "#2b5c8f", "face": "#f0f4f8", "lw": 1.2, "ls": "-"},
    }

    for x, y, w, h, title, sub, btype in steps:
        c = colors[btype]
        box = patches.FancyBboxPatch(
            (x, y), w, h,
            boxstyle="round,pad=0.8,rounding_size=2.0",
            ec=c["edge"], fc=c["face"], lw=c["lw"], ls=c["ls"]
        )
        ax.add_patch(box)
        
        cx = x + w / 2.0
        cy_title = y + h * 0.65
        cy_sub = y + h * 0.28
        
        title_color = "#9b2c2c" if btype == "security" else ("#0f2942" if btype == "pim" else "#1a202c")
        sub_color = "#742a2a" if btype == "security" else ("#1a365d" if btype == "pim" else "#4a5568")

        ax.text(cx, cy_title, title, ha="center", va="center",
                fontsize=8.5, fontweight="bold", color=title_color)
        ax.text(cx, cy_sub, sub, ha="center", va="center",
                fontsize=7.2, color=sub_color)

    arrow_props = dict(facecolor="#2b5c8f", edgecolor="#2b5c8f", width=1.0, headwidth=4.5, headlength=5.0)
    y_transitions = [
        (85, 80),
        (69, 64),
        (48, 44),
        (33, 28),
        (17, 12),
    ]
    for y_top, y_bot in y_transitions:
        ax.annotate("", xy=(50, y_bot), xytext=(50, y_top),
                    arrowprops=arrow_props)

    plt.tight_layout(pad=0.2)
    fig.savefig(OUT_DIR / "image1.png", dpi=600)
    plt.close(fig)
    print("Generated Fig 1: image1.png")


def generate_figure2():
    """Fig. 2: Performance–Quality Policy Tradeoff"""
    rows = read_csv(DATA_DIR / "policy_tradeoff.csv")
    labels = ["Zero Imputation", "Mean Imputation"]
    overhead = [float(r["overhead_pct"]) for r in rows]
    agg_err = [float(r["aggregation_error"]) for r in rows]

    fig, ax1 = plt.subplots(figsize=(3.5, 2.7), dpi=600)
    x = np.arange(len(labels))
    width = 0.38

    bars = ax1.bar(x, overhead, width, color="#2b6cb0", edgecolor="#1a365d", lw=1.2, label="Calibrated Overhead (%)", zorder=3)
    ax1.set_ylabel("Calibrated Overhead (%)", color="#1a365d", fontweight="bold")
    ax1.set_ylim(0, 0.17)
    ax1.set_yticks([0.00, 0.04, 0.08, 0.12, 0.16])
    ax1.tick_params(axis='y', labelcolor="#1a365d")
    ax1.set_xticks(x)
    ax1.set_xticklabels(labels, fontweight="bold")
    ax1.grid(axis='y', linestyle='--', alpha=0.35, zorder=0)

    for bar in bars:
        height = bar.get_height()
        ax1.annotate(f"{height:.3f}%",
                    xy=(bar.get_x() + bar.get_width() / 2, height),
                    xytext=(0, 4), textcoords="offset points",
                    ha='center', va='bottom', fontsize=8, fontweight="bold", color="#1a365d")

    ax2 = ax1.twinx()
    line = ax2.plot(x, agg_err, color="#c53030", marker="D", markersize=7, lw=2.0,
                    label="Aggregation Error", zorder=4)
    ax2.set_ylabel("UCI HAR Aggregation Error", color="#9b2c2c", fontweight="bold")
    ax2.set_ylim(-0.005, 0.09)
    ax2.set_yticks([0.00, 0.02, 0.04, 0.06, 0.08])
    ax2.tick_params(axis='y', labelcolor="#9b2c2c")

    ax2.annotate(f"{agg_err[0]:.4f}", xy=(x[0], agg_err[0]), xytext=(12, -2),
                 textcoords="offset points", fontsize=8, fontweight="bold", color="#9b2c2c")
    ax2.annotate(f"{agg_err[1]:.4f}", xy=(x[1], agg_err[1]), xytext=(10, 4),
                 textcoords="offset points", fontsize=8, fontweight="bold", color="#9b2c2c")

    lines_1, labels_1 = ax1.get_legend_handles_labels()
    lines_2, labels_2 = ax2.get_legend_handles_labels()
    ax1.legend(lines_1 + lines_2, labels_1 + labels_2, loc="upper left",
               framealpha=0.92, edgecolor="#cbd5e0", fontsize=8)

    plt.tight_layout()
    fig.savefig(OUT_DIR / "image2.png", dpi=600)
    plt.close(fig)
    print("Generated Fig 2: image2.png")


def generate_figure3():
    """Fig. 3: Mean-Imputation Quality Sensitivity Across Corruption Rates"""
    rows = read_csv(DATA_DIR / "quality_uci_mean.csv")
    rates = [float(r["rate_pct"]) for r in rows]
    wcss = [float(r["wcss_ratio"]) for r in rows]
    nmi = [float(r["nmi"]) for r in rows]

    fig, ax = plt.subplots(figsize=(3.5, 2.6), dpi=600)

    ax.plot(rates, wcss, color="#2b6cb0", marker="o", markersize=6.5, lw=1.8,
            label="WCSS Ratio", zorder=3)
    ax.plot(rates, nmi, color="#c53030", marker="s", markersize=6.5, lw=1.8,
            label="Normalized Mutual Info (NMI)", zorder=3)

    ax.set_xlabel("Data Corruption Rate (%)", fontweight="bold")
    ax.set_ylabel("Quality Metric Value", fontweight="bold")
    ax.set_xlim(-1.5, 42)
    ax.set_ylim(0.35, 1.08)
    ax.set_xticks([0, 5, 10, 20, 30, 40])
    ax.set_yticks([0.4, 0.6, 0.8, 1.0])
    ax.grid(True, linestyle="--", alpha=0.35)

    ax.legend(loc="center right", framealpha=0.92, edgecolor="#cbd5e0", fontsize=8.5)

    plt.tight_layout()
    fig.savefig(OUT_DIR / "image3.png", dpi=600)
    plt.close(fig)
    print("Generated Fig 3: image3.png")


def generate_figure4():
    """Fig. 4: Calibrated Hybrid-Oblivious Runtime and Throughput vs Public Block Size"""
    rows = read_csv(DATA_DIR / "hybrid_block.csv")
    blocks = [int(r["block_kib"]) for r in rows]
    runtimes = [float(r["hybrid_oblivious_runtime_sec"]) for r in rows]
    throughputs = [float(r["hybrid_oblivious_throughput_mib_s"]) for r in rows]

    fig, ax1 = plt.subplots(figsize=(3.5, 2.7), dpi=600)

    x_positions = np.arange(len(blocks))

    line1 = ax1.plot(x_positions, runtimes, color="#2b6cb0", marker="o", markersize=6.5, lw=1.8,
                     label="Runtime (s)", zorder=3)
    ax1.set_xlabel("DMA Block Size (KiB)", fontweight="bold")
    ax1.set_ylabel("Calibrated Runtime (s)", color="#1a365d", fontweight="bold")
    ax1.set_ylim(-0.02, 0.95)
    ax1.set_yticks([0.0, 0.2, 0.4, 0.6, 0.8])
    ax1.set_xticks(x_positions)
    ax1.set_xticklabels([str(b) for b in blocks])
    ax1.tick_params(axis='y', labelcolor="#1a365d")
    ax1.grid(True, linestyle="--", alpha=0.35)

    ax2 = ax1.twinx()
    line2 = ax2.plot(x_positions, throughputs, color="#c53030", marker="s", markersize=6.5, lw=1.8,
                     label="Throughput (MiB/s)", zorder=3)
    ax2.set_ylabel("Throughput (MiB/s)", color="#9b2c2c", fontweight="bold")
    ax2.set_ylim(-5, 185)
    ax2.set_yticks([0, 50, 100, 150])
    ax2.tick_params(axis='y', labelcolor="#9b2c2c")

    lines = line1 + line2
    labels = [l.get_label() for l in lines]
    ax1.legend(lines, labels, loc="upper center", framealpha=0.92, edgecolor="#cbd5e0", fontsize=8.5)

    plt.tight_layout()
    fig.savefig(OUT_DIR / "image4.png", dpi=600)
    plt.close(fig)
    print("Generated Fig 4: image4.png")


def generate_figure5():
    """Fig. 5: Continuous Single-Axis Stacked Bar Chart (Option A)"""
    rows = read_csv(DATA_DIR / "phase_breakdown.csv")
    categories = ["PIM", "Hyb. 1K", "Hyb. 16K", "Hyb. 128K"]
    
    scan = np.array([float(r["scan_sec"]) for r in rows])
    clean = np.array([float(r["clean_sec"]) for r in rows])
    access = np.array([float(r["access_sec"]) for r in rows])
    workload = np.array([float(r["workload_sec"]) for r in rows])
    totals = scan + clean + access + workload

    fig, ax = plt.subplots(figsize=(3.5, 2.7), dpi=600)
    x = np.arange(len(categories))
    width = 0.48

    colors = {
        "workload": "#718096",
        "access": "#dd6b20",
        "clean": "#38a169",
        "scan": "#3182ce",
    }

    ax.bar(x, scan, width, label="Scan", color=colors["scan"], edgecolor="black", lw=0.6)
    ax.bar(x, clean, width, bottom=scan, label="Clean", color=colors["clean"], edgecolor="black", lw=0.6)
    ax.bar(x, access, width, bottom=scan+clean, label="Access", color=colors["access"], edgecolor="black", lw=0.6)
    ax.bar(x, workload, width, bottom=scan+clean+access, label="Workload", color=colors["workload"], edgecolor="black", lw=0.6)

    # Clean total labels above bars with ample clearance
    for i, total in enumerate(totals):
        ax.annotate(f"{total:.3f}s", xy=(x[i], total), xytext=(0, 4),
                    textcoords="offset points", ha="center", va="bottom",
                    fontsize=7.8, fontweight="bold", color="#1a202c")

    ax.set_ylabel("Calibrated Time (s)", fontweight="bold")
    ax.set_ylim(0, 1.05)
    ax.set_yticks([0.0, 0.2, 0.4, 0.6, 0.8, 1.0])
    ax.set_xticks(x)
    ax.set_xticklabels(categories, fontweight="bold")
    ax.grid(axis="y", linestyle="--", alpha=0.35)

    handles, labels = ax.get_legend_handles_labels()
    ax.legend(reversed(handles), reversed(labels), loc="upper right",
              ncol=2, framealpha=0.92, edgecolor="#cbd5e0", fontsize=7.8)

    plt.tight_layout()
    fig.savefig(OUT_DIR / "image5.png", dpi=600)
    plt.close(fig)
    print("Generated Fig 5: image5.png (Continuous Single Axis)")


def generate_figure6():
    """Fig. 6: Clean, Uncluttered Empirical Leakage Control (Original clean layout at 600 DPI)"""
    rows = read_csv(DATA_DIR / "leakage.csv")
    rates = [float(r["rate_pct"]) for r in rows]
    
    host_cond = [float(r["hostconditional_cycles"]) for r in rows]
    hyb_sparse = [float(r["hybridsparse_cycles"]) for r in rows]
    pim_obliv = [float(r["pimoblivious_cycles"]) for r in rows]
    hyb_obliv = [float(r["hybridoblivious_cycles"]) for r in rows]

    fig, ax = plt.subplots(figsize=(3.5, 2.7), dpi=600)

    ax.semilogy(rates, host_cond, color="#0052cc", marker="o", markersize=6.0, lw=1.8,
                label="host-conditional", zorder=3)
    ax.semilogy(rates, hyb_sparse, color="#d32f2f", marker="^", markersize=6.5, lw=1.8, ls="--",
                label="hybrid-sparse", zorder=3)
    ax.semilogy(rates, hyb_obliv, color="#212121", marker="D", markersize=5.5, lw=1.8, ls=":",
                label="hybrid-oblivious", zorder=3)
    ax.semilogy(rates, pim_obliv, color="#795548", marker="s", markersize=6.0, lw=1.8,
                label="pim-oblivious", zorder=3)

    ax.set_xlabel("Corruption (%)", fontweight="bold", fontsize=9.5)
    ax.set_ylabel("Cleaning completion (modeled cycles)", fontweight="bold", fontsize=9.5)
    ax.set_xlim(-1.5, 42)
    ax.set_ylim(1e4, 5e10)
    ax.set_xticks([0, 10, 20, 30, 40])
    ax.grid(True, which="both", linestyle="--", alpha=0.35)

    ax.legend(loc="lower left", bbox_to_anchor=(0.02, 0.08), ncol=2,
              frameon=True, framealpha=0.92, edgecolor="#cbd5e0", fontsize=7.5)

    plt.tight_layout()
    fig.savefig(OUT_DIR / "image6.png", dpi=600)
    plt.close(fig)
    print("Generated Fig 6: image6.png (Clean uncrowded layout)")


if __name__ == "__main__":
    generate_figure1()
    generate_figure2()
    generate_figure3()
    generate_figure4()
    generate_figure5()
    generate_figure6()
    print("[SUCCESS] All 6 refined figures generated at 600 DPI in paper/refined_figures/")
