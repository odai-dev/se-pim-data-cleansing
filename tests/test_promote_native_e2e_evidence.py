#!/usr/bin/env python3
"""Synthetic, gem5-free tests for the native evidence promotion gate."""

from __future__ import annotations

import copy
import csv
import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "promote_native_e2e_evidence",
    ROOT / "scripts" / "promote_native_e2e_evidence.py",
)
assert SPEC and SPEC.loader
promotion = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = promotion
SPEC.loader.exec_module(promotion)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def artifact(path: str, tag: str, size: int = 17):
    return {"path": path, "bytes": size, "sha256": digest(tag)}


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def write_csv(path: Path, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


class Fixture:
    def __init__(self, root: Path):
        self.root = root
        self.commit_top = "a" * 40
        self.commit_impica = "b" * 40
        self.source_diff = digest("source-diff")
        self.source_tree = digest("source-tree")
        self.disk = artifact("disk.img", "disk", 4096)
        self.checkpoint_provenance = artifact(
            "checkpoint/checkpoint_provenance.json", "checkpoint-provenance", 31
        )
        self.generation_manifest = artifact(
            "data/dataset_generation_manifest.json", "generation", 41
        )
        self.selected_checkpoint_files = [
            artifact("m5.cpt", "m5-cpt", 101),
            artifact("system.physmem.store0.pmem", "pmem", 202),
        ]
        self.selected_checkpoint_tree = digest("selected-checkpoint-tree")
        self.config_ini = artifact("config.ini", "checkpoint-config", 303)
        self.system_terminal = artifact("system.terminal", "checkpoint-terminal", 404)
        self.dataset_artifacts = [
            artifact(f"data/file-{index:02d}", f"dataset-{index}", index + 1)
            for index in range(48)
        ]
        self.common_artifacts = {
            "gem5_opt": artifact("gem5.opt", "gem5", 1000),
            "aarch64_guest": artifact("kmeans_sepim_fs", "guest", 1001),
            "test_driver_ko": artifact("test-driver.ko", "driver", 1002),
            "disk_image": self.disk,
            "kernel": artifact("vmlinux", "kernel", 1003),
            "dtb": artifact("board.dtb", "dtb", 1004),
            "bootloader": artifact("boot.arm64", "boot", 1005),
            "kmeans_oracle": artifact("kmeans_digest_oracle", "oracle", 1006),
            "dataset_generator": artifact("corrupt_dataset.py", "generator", 1007),
            "dataset_wrapper": artifact("generate_matrix.py", "wrapper", 1008),
        }
        self.fused = self.make_native("fused")
        self.separate = self.make_native("separate")
        self.audit = self.make_audit()
        self.regression = self.make_regression()

    def git_provenance(self):
        def repo(commit: str, tag: str):
            return {
                "commit": commit,
                "tracked_diff_sha256": digest(f"{tag}-tracked"),
                "tracked_diff_bytes": 0,
                "untracked_paths_sha256": digest(f"{tag}-untracked"),
                "untracked_path_count": 0,
                "status_sha256": digest(f"{tag}-status"),
                "status_bytes": 0,
            }

        return {
            "status": "valid_commits_and_worktree_views",
            "repositories": {
                "top": repo(self.commit_top, "top"),
                "IMPICA": repo(self.commit_impica, "impica"),
            },
            "source_diff_digest": self.source_diff,
            "source_diff_digest_encoding": "synthetic-length-prefixed-v1",
        }

    def metadata(self):
        records = []
        payload_bytes = promotion.FULL_POINTS * promotion.FULL_DIMS * 4
        dataset_bytes = payload_bytes + 32
        for seed in promotion.FULL_SEEDS:
            for rate in promotion.FULL_RATES:
                tag = int(round(rate * 100))
                records.append({
                    "format": {
                        "magic_hex": "0x4b4d4453", "version": 1,
                        "float": "float32", "null_sentinel": -999999.0,
                    },
                    "seed": seed,
                    "source": "synthetic-gaussian-mixture",
                    "distribution_name": "balanced",
                    "clusters": promotion.FULL_DATA_CLUSTERS,
                    "points": promotion.FULL_POINTS,
                    "dims": promotion.FULL_DIMS,
                    "dirty_frac_requested": rate,
                    "dirty_count": round(rate * promotion.FULL_POINTS),
                    "dirty_frac_actual": round(rate * promotion.FULL_POINTS)
                    / promotion.FULL_POINTS,
                    "distribution": {"nan": 0, "null": 0, "outlier": 0},
                    "dirty_indices": {"nan": [], "null": [], "outlier": []},
                    "files": {
                        "clean": artifact(f"s{seed}_r{tag}_clean.bin", f"clean-{seed}", dataset_bytes),
                        "dirty": artifact(f"s{seed}_r{tag}_dirty.bin", f"dirty-{seed}-{tag}", dataset_bytes),
                        "labels": artifact(f"s{seed}_r{tag}_labels.bin", f"labels-{seed}", 131100),
                    },
                    "metadata_file": artifact(f"s{seed}_r{tag}.json", f"meta-{seed}-{tag}", 999),
                })
        return records

    def native_rows(self, role: str):
        rows = []
        payload_bytes = promotion.FULL_POINTS * promotion.FULL_DIMS * 4
        dataset_bytes = payload_bytes + 32
        metadata = {(record["seed"], round(record["dirty_frac_requested"], 9)): record
                    for record in self.metadata()}
        for seed in promotion.FULL_SEEDS:
            for rate in promotion.FULL_RATES:
                rate_tag = int(round(rate * 100))
                stem = f"s{seed:03d}_r{rate_tag:03d}"
                for slot in ("off", "zero", "mean"):
                    mode = "off" if slot == "off" else "pim-oblivious"
                    policy = "zero" if slot == "off" else slot
                    path = "fused" if role == "fused" and slot == "zero" else "separate"
                    suffix = "off" if slot == "off" else f"pim_{slot}"
                    if slot == "zero" and path == "fused":
                        suffix += "_fused"
                    case_id = f"{stem}_{suffix}"
                    transcript = promotion.expected_transcript(mode, policy, path)
                    clock = 1000
                    clean_ticks = transcript["clean_bound_cycles"] * clock
                    work_ticks = transcript["work_bound_cycles"] * clock
                    total_ticks = clean_ticks + work_ticks
                    record = metadata[(seed, round(rate, 9))]
                    input_kind = "clean" if slot == "off" else "dirty"
                    input_hash = record["files"][input_kind]["sha256"]
                    output_key = f"{stem}_off" if rate == 0.0 else case_id
                    output = digest(f"output-{output_key}")[:16]
                    trace = transcript["trace_digest"] or "1234567890abcdef"
                    row = {
                        "cleaning_mode": mode,
                        "imputation": policy,
                        "model_kind": "gem5_native_e2e_kmeans",
                        "workload": "kmeans",
                        "dataset_file": record["files"][input_kind]["path"],
                        "corruption_frac": f"{(0.0 if slot == 'off' else rate):.4f}",
                        "seed": str(seed),
                        "points": str(promotion.FULL_POINTS),
                        "dims": str(promotion.FULL_DIMS),
                        "iterations": str(promotion.FULL_ITERATIONS),
                        "clusters": str(promotion.FULL_WORK_CLUSTERS),
                        "visible_reads": str(transcript["read_actions"]),
                        "visible_writes": str(transcript["write_actions"]),
                        "visible_bytes": str(transcript["transferred_bytes"]),
                        "completion_cycles": str(transcript["total_bound_cycles"]),
                        "simulator_ticks": str(total_ticks),
                        "simulator_dma_bytes": str(transcript["transferred_bytes"]),
                        "status_polls": "2",
                        "trace_digest": trace,
                        "native_e2e": "1",
                        "total_ticks": str(total_ticks),
                        "clean_ticks": str(clean_ticks),
                        "work_ticks": str(work_ticks),
                        "output_digest": output,
                        "reference_output_digest": output,
                        "dma_read_actions": str(transcript["read_actions"]),
                        "dma_write_actions": str(transcript["write_actions"]),
                        "submitted_read_packets": str(transcript["read_packets"]),
                        "submitted_write_packets": str(transcript["write_packets"]),
                        "device_clock_period_ticks": str(clock),
                        "correctness": "1",
                        "native_zero_path": path,
                        "fused_zero_kmeans": str(transcript["fused_zero_kmeans"]),
                        "cleaner_validation_lanes": str(transcript["cleaner_validation_lanes"]),
                        "kmeans_arithmetic_cores": str(transcript["kmeans_arithmetic_cores"]),
                        "fused_validation_cycles": str(transcript["fused_validation_cycles"]),
                        "fused_write_bound_cycles": str(transcript["fused_write_bound_cycles"]),
                        "fused_overlap_credit_cycles": str(transcript["fused_overlap_credit_cycles"]),
                        "case_id": case_id,
                        "input_kind": input_kind,
                        "input_corruption_frac": str(0.0 if slot == "off" else rate),
                        "paired_corruption_frac": str(rate),
                        "input_sha256": input_hash,
                        "clean_sha256": record["files"]["clean"]["sha256"],
                        "dirty_sha256": record["files"]["dirty"]["sha256"],
                        "public_input_bytes": str(dataset_bytes),
                        "dataset_file_bytes": str(dataset_bytes),
                        "payload_bytes": str(payload_bytes),
                        "host_oracle_output_digest": output,
                        "reference_kind": "host_kmeans_fixed_iteration_oracle",
                        "cpu_type": "timing",
                        "cpu_class": "TimingSimpleCPU",
                        "mem_mode": "timing",
                        "evidence_tier": "native_candidate_timing_direct_restore_padded_command_measurement",
                        "latency_semantics": (
                            "fixed_schedule_padded_native_device_command_with_public_"
                            "iteration0_compute_write_overlap"
                            if transcript["fused_zero_kmeans"]
                            else "fixed_schedule_padded_native_device_command"
                        ),
                        "checkpoint_cpu_type": "timing",
                        "restore_strategy": "direct",
                        "restore_with_cpu": "timing",
                        "checkpoint_restore_semantics": "same_cpu_class_direct_restore",
                        "configured_initial_mem_mode": "timing",
                        "cpu_switch_used": "False",
                        "cpu_switch_warmup_ticks": "0",
                        "num_cpus": "4",
                        "cache_line_size_bytes": "64",
                        "case_config_ini_sha256": digest("config"),
                        "guest_workload_sha256": self.common_artifacts["aarch64_guest"]["sha256"],
                        "guest_driver_sha256": self.common_artifacts["test_driver_ko"]["sha256"],
                        "guest_dataset_sha256": input_hash,
                        "guest_artifact_attestation_kind": "atomic_guest_hash_preflight_same_checkpoint_and_disk",
                        "run_id": f"native-{role}",
                    }
                    rows.append(row)
        return rows

    def paired_rows(self, native_rows):
        native = {row["case_id"]: row for row in native_rows}
        rows = []
        for seed in promotion.FULL_SEEDS:
            for rate in promotion.FULL_RATES:
                tag = int(round(rate * 100))
                stem = f"s{seed:03d}_r{tag:03d}"
                baseline = native[f"{stem}_off"]
                for policy in promotion.POLICIES:
                    candidates = [row for row in native_rows
                                  if row["case_id"].startswith(stem + "_pim_" + policy)]
                    self_case = candidates[0]
                    baseline_ticks = int(baseline["total_ticks"])
                    cleaned_ticks = int(self_case["total_ticks"])
                    incremental = cleaned_ticks - baseline_ticks
                    work_delta = int(self_case["work_ticks"]) - int(baseline["work_ticks"])
                    overhead = incremental * 100.0 / baseline_ticks
                    rows.append({
                        "model_kind": "gem5_native_e2e_kmeans",
                        "evidence_tier": baseline["evidence_tier"],
                        "cpu_type": "timing", "cpu_class": "TimingSimpleCPU", "mem_mode": "timing",
                        "checkpoint_cpu_type": "timing", "restore_strategy": "direct",
                        "restore_with_cpu": "timing",
                        "checkpoint_restore_semantics": baseline["checkpoint_restore_semantics"],
                        "cpu_switch_used": "False", "num_cpus": "4",
                        "cache_line_size_bytes": "64",
                        "guest_workload_sha256": baseline["guest_workload_sha256"],
                        "guest_driver_sha256": baseline["guest_driver_sha256"],
                        "workload": "kmeans", "iterations": str(promotion.FULL_ITERATIONS),
                        "clusters": str(promotion.FULL_WORK_CLUSTERS), "policy": policy,
                        "native_zero_path": self_case["native_zero_path"],
                        "seed": str(seed), "corruption_frac": f"{rate:.6f}",
                        "points": str(promotion.FULL_POINTS), "dims": str(promotion.FULL_DIMS),
                        "baseline_case_id": baseline["case_id"],
                        "cleaned_case_id": self_case["case_id"],
                        "baseline_total_ticks": str(baseline_ticks),
                        "cleaned_total_ticks": str(cleaned_ticks),
                        "clean_ticks": self_case["clean_ticks"],
                        "baseline_work_ticks": baseline["work_ticks"],
                        "cleaned_work_ticks": self_case["work_ticks"],
                        "work_tick_delta": str(work_delta),
                        "expected_work_tick_delta": str(work_delta),
                        "incremental_ticks": str(incremental),
                        "expected_incremental_ticks": str(incremental),
                        "measured_overhead_pct": f"{overhead:.12f}",
                        "fixed_schedule_overhead_pct": f"{overhead:.12f}",
                        "device_clock_period_ticks": baseline["device_clock_period_ticks"],
                        "baseline_status_polls": "2", "cleaned_status_polls": "2",
                        "baseline_trace_digest": baseline["trace_digest"],
                        "cleaned_trace_digest": self_case["trace_digest"],
                        "baseline_output_digest": baseline["output_digest"],
                        "cleaned_output_digest": self_case["output_digest"],
                        "correctness": "1", "run_id": baseline["run_id"],
                    })
        return rows

    def make_native(self, role: str) -> Path:
        native_rows = self.native_rows(role)
        paired_rows = self.paired_rows(native_rows)
        native_csv = self.root / f"{role}-native.csv"
        paired_csv = self.root / f"{role}-paired.csv"
        write_csv(native_csv, native_rows)
        write_csv(paired_csv, paired_rows)
        snapshot = {
            "artifacts": copy.deepcopy(self.common_artifacts),
            "checkpoint": {
                "directory": "/workspace/checkpoint",
                "restore_index": 1,
                "selected_checkpoint": "cpt.1",
                "m5_cpt_sha256": self.selected_checkpoint_files[0]["sha256"],
                "selected_checkpoint_tree_sha256": self.selected_checkpoint_tree,
                "selected_checkpoint_files": copy.deepcopy(self.selected_checkpoint_files),
            },
            "bound_checkpoint_tree": {
                "files": [
                    *[
                        {
                            **copy.deepcopy(record),
                            "path": f"selected_checkpoint/cpt.1/{record['path']}",
                        }
                        for record in self.selected_checkpoint_files
                    ],
                    copy.deepcopy(self.config_ini),
                    copy.deepcopy(self.system_terminal),
                ],
                "tree_sha256": digest("bound-checkpoint"),
            },
            "checkpoint_provenance": copy.deepcopy(self.checkpoint_provenance),
            "dataset_generation_manifest": copy.deepcopy(self.generation_manifest),
            "selected_dataset_artifacts": copy.deepcopy(self.dataset_artifacts),
        }
        snapshot_hash = promotion.canonical_sha256(snapshot)
        generation_parameters = {
            "points": promotion.FULL_POINTS, "dims": promotion.FULL_DIMS,
            "clusters": promotion.FULL_DATA_CLUSTERS,
            "seeds": list(promotion.FULL_SEEDS), "rates": list(promotion.FULL_RATES),
            "distribution": "balanced",
        }
        oracle_records = [{
            "case_id": row["case_id"], "digest": row["output_digest"],
            "points": promotion.FULL_POINTS, "dims": promotion.FULL_DIMS,
            "clusters": promotion.FULL_WORK_CLUSTERS,
            "iterations": promotion.FULL_ITERATIONS, "dirty_remaining": 0,
            "dataset_sha256": row["input_sha256"],
        } for row in native_rows]
        criteria = {
            "timing_measurement": True,
            "same_class_timing_checkpoint": True,
            "direct_restore_without_cpu_switch": True,
            "strict_checkpoint_provenance": True,
            "strict_dataset_generation_transcript": True,
                "non_quick_publication_matrix": True,
                "full_36_case_matrix": True,
                "valid_top_and_impica_commits": True,
        }
        attested_by_path = {}
        for row in native_rows:
            previous = attested_by_path.setdefault(
                row["dataset_file"], row["input_sha256"]
            )
            if previous != row["input_sha256"]:
                raise AssertionError("synthetic guest path has conflicting hashes")
        document = {
            "schema_version": 6, "run_id": f"native-{role}",
            "model_kind": "gem5_native_e2e_kmeans",
            "evidence_tier": "native_candidate_timing_direct_restore_padded_command_measurement",
            "cpu_configuration": {
                "requested_cpu_type": "timing", "measurement_cpu_class": "TimingSimpleCPU",
                "effective_measurement_mem_mode": "timing", "checkpoint_cpu_type": "timing",
                "checkpoint_mem_mode": "timing", "num_cpus": 4, "restore_strategy": "direct",
                "restore_with_cpu": "timing",
                "checkpoint_restore_semantics": "same_cpu_class_direct_restore",
                "switch_after_restore": False, "cpu_switch_used": False,
                "switch_warmup_ticks": 0,
            },
            "checkpoint": {
                "selected_checkpoint_tree_sha256": self.selected_checkpoint_tree,
                "provenance": {
                    "status": "schema_1_checkpoint_lineage_validated",
                    "publication_eligible": True,
                    "creation_kind": "timing_recheckpoint_from_parent",
                    "parent_checkpoint_tree_sha256": digest("parent-checkpoint-tree"),
                    "creator_inputs_validated": [
                        "baseline_runner", "checkpoint_creator", "common_helpers",
                        "guest_checkpoint_script", "provenance_helper",
                    ],
                    "artifact": copy.deepcopy(self.checkpoint_provenance),
                },
            },
            "guest_artifact_attestation": {
                "status": "pass",
                "kind": "atomic_guest_hash_preflight_same_checkpoint_and_disk",
                "purpose": "byte_attestation_only_excluded_from_timing_evidence",
                "guest_workload_sha256": self.common_artifacts["aarch64_guest"]["sha256"],
                "guest_driver_sha256": self.common_artifacts["test_driver_ko"]["sha256"],
                "unique_dataset_files": 24,
                "datasets": [
                    {"guest_path": path, "sha256": value}
                    for path, value in sorted(attested_by_path.items())
                ],
                "cpu_configuration": {
                    "requested_cpu_type": "atomic",
                    "measurement_cpu_class": "AtomicSimpleCPU",
                    "effective_mem_mode": "atomic",
                    "checkpoint_cpu_type": "timing",
                    "cpu_switch_used": False,
                    "num_cpus": 4,
                },
            },
            "immutable_input_provenance": {
                "status": "start_snapshot_revalidated_unchanged_at_finish",
                "publication_eligible": True,
                "publication_eligibility": {
                    "eligible": True, "criteria": criteria, "ineligible_reasons": [],
                },
                "snapshot_sha256": snapshot_hash,
                "start_snapshot": snapshot,
                "finish_revalidation": {
                    "status": "exact_object_equality_pass", "snapshot_sha256": snapshot_hash,
                },
            },
            "docker_image": "sepim@sha256:" + "c" * 64,
            "top_commit": self.commit_top, "impica_commit": self.commit_impica,
            "git_provenance": self.git_provenance(),
            "source_diff_digest": self.source_diff, "source_tree_sha256": self.source_tree,
            "parameters": {
                "points": promotion.FULL_POINTS, "dims": promotion.FULL_DIMS,
                "data_clusters": promotion.FULL_DATA_CLUSTERS, "workload": "kmeans",
                "workload_iterations": promotion.FULL_ITERATIONS,
                "workload_clusters": promotion.FULL_WORK_CLUSTERS,
                "native_zero_path": role,
                "seeds": list(promotion.FULL_SEEDS), "rates": list(promotion.FULL_RATES),
                "policies": list(promotion.POLICIES), "modes": ["off", "pim-oblivious"],
                "completion_observation": (
                    "guest performs exactly one completion STATUS read after the "
                    "mandatory command-acceptance STATUS read"
                ),
                "fixed_phase_bound_cycles": {
                    "base": promotion.NATIVE_BOUND_BASE_CYCLES,
                    "per_dma_action": promotion.NATIVE_BOUND_ACTION_CYCLES,
                    "per_submitted_packet": promotion.NATIVE_BOUND_PACKET_CYCLES,
                    "cleaner_validation_lanes": promotion.NATIVE_CLEANER_VALIDATION_LANES,
                    "kmeans_arithmetic_cores": promotion.NATIVE_KMEANS_ARITHMETIC_CORES,
                },
            },
            "dataset_id": "canonical-dataset",
            "dataset_generation_provenance": {
                "status": "supplied_strictly_validated_generation_transcript",
                "artifact": copy.deepcopy(self.generation_manifest),
                "validated_parameters": generation_parameters,
                "validated_outputs": copy.deepcopy(self.dataset_artifacts),
            },
            "dataset_metadata": self.metadata(),
            "reference": {
                "kind": "host_kmeans_fixed_iteration_oracle",
                "binary": copy.deepcopy(self.common_artifacts["kmeans_oracle"]),
                "records": oracle_records,
            },
            "native_result_csv": str(native_csv), "paired_result_csv": str(paired_csv),
            "validation": {
                "status": "pass", "rows": 36, "pairs": 24, "secure_groups": 3,
                "fixed_fields": list(promotion.SECURE_FIELDS),
            },
        }
        path = self.root / f"{role}-manifest.json"
        write_json(path, document)
        return path

    def make_audit(self) -> Path:
        path = self.root / "assembly-audit.json"
        assembly = self.root / "pim_cleaner.s"
        assembly.write_text("pim_clean_oblivious:\n\tcsel x0, x1, x2, eq\n", encoding="utf-8")
        write_json(path, {
            "schema_version": 1, "assembly": str(assembly),
            "assembly_sha256": hashlib.sha256(assembly.read_bytes()).hexdigest(),
            "function": "pim_clean_oblivious",
            "forbidden_secret_dependent_branches": [],
            "required_mask_instructions": {
                "floating_compare_mask": True, "integer_mask_select": True,
                "conditional_select_for_empty_mean": True,
            },
            "result": "pass",
        })
        return path

    def make_regression(self) -> Path:
        entries = [{"path": ".", "type": "directory", "mode": 0o755, "mtime_ns": 1}]
        for record in self.selected_checkpoint_files:
            entries.append({
                "path": f"cpt.1/{record['path']}", "type": "file",
                "bytes": record["bytes"], "sha256": record["sha256"],
                "mode": 0o644, "mtime_ns": 1,
            })
        entries.append({
            "path": "checkpoint_provenance.json", "type": "file",
            "bytes": self.checkpoint_provenance["bytes"],
            "sha256": self.checkpoint_provenance["sha256"],
            "mode": 0o644, "mtime_ns": 1,
        })
        for record in (self.config_ini, self.system_terminal):
            entries.append({
                "path": record["path"], "type": "file", "bytes": record["bytes"],
                "sha256": record["sha256"], "mode": 0o644, "mtime_ns": 1,
            })
        snapshot = {
            "disk": {**copy.deepcopy(self.disk), "mode": 0o644, "mtime_ns": 1},
            "checkpoint": {
                "path": "/checkpoint", "entries": entries,
                "tree_sha256": digest("regression-checkpoint-tree"),
            },
        }
        case_order = [
            "table2_pass1", "table2_pass2", "dma_full", "controlled_full",
            "hashtable_canonical", "trace_cpu_full", "trace_sepim_full",
            "kmeans_legacy_full",
        ]
        cases = []
        for case_id in case_order:
            cases.append({
                "id": case_id, "workload": case_id, "mode": "full", "pass": True,
                "cpu": {"class": "AtomicSimpleCPU"}, "validation": {"status": "pass"},
                "checkpoint_role": "regression_only_atomic_restore",
                "guest_script": artifact(f"{case_id}.rcS", f"{case_id}-rcs"),
                "terminal": artifact(f"{case_id}.terminal", f"{case_id}-terminal"),
                "output_tree": {"files": [], "tree_sha256": digest(f"{case_id}-tree")},
            })
        limitation = "Dynamic legacy PimDevice DMA event IDs 0..5 remain incompletely covered."
        document = {
            "schema_version": 2, "mode": "full", "status": "passed",
            "publication_eligible": True,
            "promotability": {
                "eligible": True,
                "checks": {
                    "mode_is_full": True, "status_passed": True,
                    "exact_case_matrix": True, "all_cases_passed": True,
                    "network_disabled": True, "container_reference_pinned": True,
                    "container_content_id_pinned": True,
                    "source_evidence_immutable": True,
                    "runtime_inputs_immutable": True,
                    "injected_artifacts_immutable": True,
                    "event_coverage_limitation_preserved": True,
                },
                "ineligible_reasons": [], "policy": "full exact pinned immutable only",
            },
            "source_disk": "/disk.img", "source_checkpoint": "/checkpoint",
            "source_evidence_start": snapshot,
            "source_evidence_end": copy.deepcopy(snapshot),
            "source_evidence_immutable": True, "network": "none",
            "container_image_requested": "sepim@sha256:" + "d" * 64,
            "container_image": {
                "requested": "sepim@sha256:" + "d" * 64,
                "image_id": "sha256:" + "e" * 64,
                "repo_digests": ["sepim@sha256:" + "d" * 64],
                "requested_reference_pinned": True, "network": "none",
            },
            "commands": [{"phase": "synthetic", "network": "none"}],
            "runtime_inputs": {
                "gem5": artifact("gem5.opt", "regression-runtime-gem5", 1000),
            },
            "runtime_inputs_end": {
                "gem5": artifact("gem5.opt", "regression-runtime-gem5", 1000),
            },
            "runtime_inputs_immutable": True,
            "injected_artifacts": {
                "sepim_cmd": artifact("sepim_cmd", "regression-sepim-cmd", 2000),
            },
            "injected_artifacts_end": {
                "sepim_cmd": artifact("sepim_cmd", "regression-sepim-cmd", 2000),
            },
            "injected_artifacts_immutable": True,
            "case_plan": [
                {"id": case_id, "workload": case_id, "mode": "full"}
                for case_id in case_order
            ],
            "cases": cases,
            "legacy_dma_event_coverage": {
                "declared_event_ids": [0, 1, 2, 3, 4, 5],
                "dedicated_dynamic_harness": False, "status": "incomplete",
                "publication_claim_allowed": False, "limitation": limitation,
            },
            "limitations": [limitation],
        }
        path = self.root / "regression.json"
        write_json(path, document)
        return path


class PromotionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.fixture = Fixture(self.root)

    def tearDown(self):
        self.temporary.cleanup()

    def run_promote(self, *, separate=False, run_id="promoted"):
        return promotion.promote(
            fused_manifest=self.fixture.fused,
            separate_manifest=self.fixture.separate if separate else None,
            regression_manifest=self.fixture.regression,
            assembly_audit=self.fixture.audit,
            run_id=run_id,
            out_root=self.root / "out",
        )

    def mutate_json(self, path: Path, callback):
        value = json.loads(path.read_text(encoding="utf-8"))
        callback(value)
        write_json(path, value)

    def test_valid_fused_only_emits_bound_bundle(self):
        output = self.run_promote()
        manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["variants"], ["fused-zero", "separate-mean"])
        self.assertEqual(manifest["validation"]["native_schema"], 6)
        self.assertEqual(manifest["limitations"], [
            "Dynamic legacy PimDevice DMA event IDs 0..5 remain incompletely covered."
        ])
        expected = hashlib.sha256((output / "manifest.json").read_bytes()).hexdigest()
        self.assertEqual((output / "manifest.json.sha256").read_text().split()[0], expected)
        with self.assertRaisesRegex(promotion.PromotionError, "overwrite"):
            self.run_promote()

    def test_valid_fused_and_separate_emits_three_variants(self):
        output = self.run_promote(separate=True)
        manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(
            manifest["variants"], ["fused-zero", "separate-zero", "separate-mean"]
        )
        with (output / "individual.csv").open(newline="") as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual(len(rows), 36)

    def test_rejects_legacy_schema5(self):
        self.mutate_json(self.fixture.fused, lambda value: value.update(schema_version=5))
        with self.assertRaisesRegex(promotion.PromotionError, "schema_version=6"):
            self.run_promote()

    def test_rejects_noncanonical_shape_and_cpu_switch(self):
        self.mutate_json(
            self.fixture.fused,
            lambda value: value["parameters"].update(points=512),
        )
        with self.assertRaisesRegex(promotion.PromotionError, "points"):
            self.run_promote()
        self.fixture.fused = self.fixture.make_native("fused")
        self.mutate_json(
            self.fixture.fused,
            lambda value: value["cpu_configuration"].update(cpu_switch_used=True),
        )
        with self.assertRaisesRegex(promotion.PromotionError, "CPU switch"):
            self.run_promote()

    def test_rejects_bad_row_poll_output_and_forbidden_column(self):
        manifest = json.loads(self.fixture.fused.read_text())
        csv_path = Path(manifest["native_result_csv"])
        with csv_path.open(newline="") as stream:
            rows = list(csv.DictReader(stream))
        rows[0]["status_polls"] = "1"
        write_csv(csv_path, rows)
        with self.assertRaisesRegex(
            promotion.PromotionError,
            "one acceptance and one completion STATUS read",
        ):
            self.run_promote()
        self.fixture.fused = self.fixture.make_native("fused")
        manifest = json.loads(self.fixture.fused.read_text())
        csv_path = Path(manifest["native_result_csv"])
        with csv_path.open(newline="") as stream:
            rows = list(csv.DictReader(stream))
        rows[0]["reference_output_digest"] = "0" * 16
        write_csv(csv_path, rows)
        with self.assertRaisesRegex(promotion.PromotionError, "digests differ"):
            self.run_promote()
        self.fixture.fused = self.fixture.make_native("fused")
        manifest = json.loads(self.fixture.fused.read_text())
        csv_path = Path(manifest["native_result_csv"])
        with csv_path.open(newline="") as stream:
            rows = list(csv.DictReader(stream))
        for row in rows:
            row["dirty_reported"] = "0"
        write_csv(csv_path, rows)
        with self.assertRaisesRegex(promotion.PromotionError, "dirty_reported"):
            self.run_promote()

    def test_rejects_incomplete_native_provenance(self):
        self.mutate_json(
            self.fixture.fused,
            lambda value: value["immutable_input_provenance"].update(publication_eligible=False),
        )
        with self.assertRaisesRegex(promotion.PromotionError, "not publication eligible"):
            self.run_promote()

    def test_rejects_regression_and_assembly_failures_without_output(self):
        self.mutate_json(
            self.fixture.regression,
            lambda value: value.update(mode="quick", publication_eligible=False),
        )
        with self.assertRaisesRegex(promotion.PromotionError, "passed full run"):
            self.run_promote()
        self.assertFalse((self.root / "out" / "promoted").exists())
        self.fixture.regression = self.fixture.make_regression()
        self.mutate_json(self.fixture.audit, lambda value: value.update(result="fail"))
        with self.assertRaisesRegex(promotion.PromotionError, "did not pass"):
            self.run_promote()

    def test_rejects_unpinned_regression_and_source_mismatch(self):
        self.mutate_json(
            self.fixture.regression,
            lambda value: value["container_image"].update(requested="sepim:latest"),
        )
        with self.assertRaisesRegex(promotion.PromotionError, "not digest-pinned"):
            self.run_promote()
        self.fixture.regression = self.fixture.make_regression()
        self.mutate_json(
            self.fixture.regression,
            lambda value: value["source_evidence_start"]["disk"].update(sha256=digest("other")),
        )
        # Keep the manifest's own immutability assertion internally consistent;
        # it must still fail the native/regression cross-binding.
        value = json.loads(self.fixture.regression.read_text())
        value["source_evidence_end"] = copy.deepcopy(value["source_evidence_start"])
        write_json(self.fixture.regression, value)
        with self.assertRaisesRegex(promotion.PromotionError, "does not match native evidence disk"):
            self.run_promote()

    def test_rejects_cross_evidence_source_mismatch(self):
        def mutate(value):
            replacement = digest("different-source")
            value["source_diff_digest"] = replacement
            value["git_provenance"]["source_diff_digest"] = replacement

        self.mutate_json(self.fixture.separate, mutate)
        with self.assertRaisesRegex(promotion.PromotionError, "does not share commits"):
            self.run_promote(separate=True)


if __name__ == "__main__":
    unittest.main()
