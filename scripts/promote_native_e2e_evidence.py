#!/usr/bin/env python3
"""Fail-closed promotion gate for native PIM-Cleanser timing evidence.

This program does not run gem5 and does not trust the summary numbers emitted by
the experiment runner.  It re-reads the two canonical CSVs, reconstructs the
public DMA transcript and fixed completion bound, checks the independent oracle
digests, binds the result to the checkpoint/dataset provenance and SE-PIM
regressions, and only then writes a small publication-facing evidence bundle.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
import re
import shutil
import statistics
import sys
import tempfile
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


ROOT = Path(__file__).resolve().parents[1]
FULL_POINTS = 8192
FULL_DIMS = 8
FULL_DATA_CLUSTERS = 6
FULL_WORK_CLUSTERS = 4
FULL_ITERATIONS = 20
FULL_SEEDS = (7, 19, 42)
FULL_RATES = (0.0, 0.01, 0.10, 0.40)
POLICIES = ("zero", "mean")

NATIVE_DMA_ACTION_BYTES = 128 * 1024
DMA_PACKET_BYTES = 64
NATIVE_CLEANER_VALIDATION_LANES = 64
NATIVE_KMEANS_ARITHMETIC_CORES = 16
NATIVE_BOUND_BASE_CYCLES = 512
NATIVE_BOUND_ACTION_CYCLES = 256
NATIVE_BOUND_PACKET_CYCLES = 10
NATIVE_DATA_BASE = 0xFC000000
FNV1A64_OFFSET = 14695981039346656037
FNV1A64_PRIME = 1099511628211

RUN_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*\Z")
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
COMMIT_RE = re.compile(r"[0-9a-f]{40}\Z")
HEX64_RE = re.compile(r"[0-9a-f]{16}\Z")
PINNED_IMAGE_RE = re.compile(r".+@sha256:[0-9a-f]{64}\Z")
EXPECTED_REGRESSION_CASES = {
    "table2_pass1",
    "table2_pass2",
    "dma_full",
    "controlled_full",
    "hashtable_canonical",
    "trace_cpu_full",
    "trace_sepim_full",
    "kmeans_legacy_full",
}


class PromotionError(RuntimeError):
    """An evidence invariant failed."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise PromotionError(message)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    return sha256_bytes(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )


def require_sha256(value: Any, label: str) -> str:
    require(isinstance(value, str) and SHA256_RE.fullmatch(value) is not None,
            f"{label} must be a lowercase SHA-256")
    return value


def require_commit(value: Any, label: str) -> str:
    require(isinstance(value, str) and COMMIT_RE.fullmatch(value) is not None,
            f"{label} must be a lowercase 40-hex Git commit")
    return value


def artifact_core(value: Any, label: str) -> Dict[str, Any]:
    require(isinstance(value, dict), f"{label} must be an artifact object")
    require(isinstance(value.get("path"), str) and value["path"],
            f"{label}.path is invalid")
    size = value.get("bytes")
    require(isinstance(size, int) and not isinstance(size, bool) and size >= 0,
            f"{label}.bytes is invalid")
    require_sha256(value.get("sha256"), f"{label}.sha256")
    return {"path": value["path"], "bytes": size, "sha256": value["sha256"]}


def contains_forbidden_key(value: Any) -> bool:
    if isinstance(value, dict):
        return any(
            key == "dirty_reported" or contains_forbidden_key(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(contains_forbidden_key(item) for item in value)
    return False


def stable_json(path: Path, label: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    path = path.resolve()
    require(path.is_file(), f"{label} is missing: {path}")
    before = path.stat()
    data = path.read_bytes()
    after = path.stat()
    identity_before = (before.st_dev, before.st_ino, before.st_size,
                       before.st_mtime_ns, before.st_ctime_ns)
    identity_after = (after.st_dev, after.st_ino, after.st_size,
                      after.st_mtime_ns, after.st_ctime_ns)
    require(identity_before == identity_after,
            f"{label} changed while it was read: {path}")
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise PromotionError(f"{label} is not valid UTF-8 JSON: {path}") from error
    require(isinstance(value, dict), f"{label} must contain a JSON object")
    require(b"dirty_reported" not in data,
            f"{label} contains forbidden dirty_reported data")
    require(not contains_forbidden_key(value),
            f"{label} contains forbidden dirty_reported data")
    record = {"path": str(path), "bytes": len(data), "sha256": sha256_bytes(data)}
    return value, record


def resolve_recorded_path(value: Any, manifest_path: Path, label: str) -> Path:
    require(isinstance(value, str) and value, f"{label} path is missing")
    path = Path(value)
    if path.is_absolute():
        if path.is_file():
            return path.resolve()
        local_peer = manifest_path.parent / path.name
        if local_peer.is_file():
            return local_peer.resolve()
        csv_peer = ROOT / "results" / "csv" / path.name
        if csv_peer.is_file():
            return csv_peer.resolve()
        return path.resolve()
    candidates = [ROOT / path, manifest_path.parent / path]
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    # Preserve the conventional project-root interpretation in the error.
    return candidates[0].resolve()


def stable_csv(path: Path, label: str) -> Tuple[List[Dict[str, str]], Dict[str, Any]]:
    path = path.resolve()
    require(path.is_file(), f"{label} is missing: {path}")
    before = path.stat()
    data = path.read_bytes()
    after = path.stat()
    require(
        (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns,
         before.st_ctime_ns)
        == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns,
            after.st_ctime_ns),
        f"{label} changed while it was read",
    )
    try:
        text = data.decode("utf-8")
    except UnicodeError as error:
        raise PromotionError(f"{label} is not UTF-8") from error
    reader = csv.DictReader(io.StringIO(text, newline=""))
    require("dirty_reported" not in text,
            f"{label} contains forbidden dirty_reported data")
    require(reader.fieldnames is not None and len(reader.fieldnames) == len(set(reader.fieldnames)),
            f"{label} has missing or duplicate headers")
    require("dirty_reported" not in reader.fieldnames,
            f"{label} exposes forbidden dirty_reported column")
    rows = list(reader)
    require(all(None not in row for row in rows), f"{label} contains ragged rows")
    require(sha256_file(path) == sha256_bytes(data),
            f"{label} changed after parsing")
    return rows, {"path": str(path), "bytes": len(data), "sha256": sha256_bytes(data)}


def parse_int(row: Mapping[str, str], field: str, label: str,
              *, minimum: int = 0) -> int:
    try:
        raw = row[field]
        require(raw is not None and re.fullmatch(r"[0-9]+", raw) is not None,
                f"{label}.{field} is not an unsigned integer")
        value = int(raw)
    except KeyError as error:
        raise PromotionError(f"{label} is missing {field}") from error
    require(value >= minimum, f"{label}.{field} is below {minimum}")
    return value


def parse_float(row: Mapping[str, str], field: str, label: str) -> float:
    try:
        value = float(row[field])
    except (KeyError, TypeError, ValueError) as error:
        raise PromotionError(f"{label}.{field} is not numeric") from error
    require(math.isfinite(value), f"{label}.{field} is non-finite")
    return value


def parse_bool(row: Mapping[str, str], field: str, label: str) -> bool:
    try:
        value = row[field].strip().lower()
    except (KeyError, AttributeError) as error:
        raise PromotionError(f"{label}.{field} is not Boolean") from error
    require(value in {"true", "false", "1", "0"},
            f"{label}.{field} is not Boolean")
    return value in {"true", "1"}


def digest16(row: Mapping[str, str], field: str, label: str) -> str:
    value = row.get(field, "").lower()
    require(HEX64_RE.fullmatch(value) is not None,
            f"{label}.{field} must be 16 lowercase hex digits")
    return value


def ceil_div(value: int, divisor: int) -> int:
    return (value + divisor - 1) // divisor


def dma_chunks(data_bytes: int, chunk_bytes: int) -> List[Tuple[int, int]]:
    return [
        (NATIVE_DATA_BASE + offset, min(chunk_bytes, data_bytes - offset))
        for offset in range(0, data_bytes, chunk_bytes)
    ]


def submitted_packets(chunks: Iterable[Tuple[int, int]]) -> int:
    return sum(
        ceil_div(address % DMA_PACKET_BYTES + size, DMA_PACKET_BYTES)
        for address, size in chunks
    )


def phase_bound(actions: int, packets: int, compute: int) -> int:
    return (NATIVE_BOUND_BASE_CYCLES
            + actions * NATIVE_BOUND_ACTION_CYCLES
            + packets * NATIVE_BOUND_PACKET_CYCLES + compute)


def fnv_add_u64(digest: int, value: int) -> int:
    for byte in range(8):
        digest ^= (value >> (8 * byte)) & 0xFF
        digest = (digest * FNV1A64_PRIME) & 0xFFFFFFFFFFFFFFFF
    return digest


def expected_transcript(mode: str, policy: str, native_zero_path: str) -> Dict[str, Any]:
    """Reconstruct the canonical N/D/K/I public transcript and deadline."""
    points, dims, clusters, iterations = (
        FULL_POINTS, FULL_DIMS, FULL_WORK_CLUSTERS, FULL_ITERATIONS
    )
    require(native_zero_path in {"separate", "fused"}, "invalid native zero path")
    fused = mode == "pim-oblivious" and policy == "zero" and native_zero_path == "fused"
    require(not (native_zero_path == "fused" and not fused),
            "fused path is valid only for pim-oblivious zero k-means")
    data_bytes = points * dims * 4
    record_bytes = dims * 4
    record_chunk = (NATIVE_DMA_ACTION_BYTES // record_bytes) * record_bytes
    raw_chunks = dma_chunks(data_bytes, NATIVE_DMA_ACTION_BYTES)
    work_chunks = dma_chunks(data_bytes, record_chunk)
    events: List[Tuple[int, int, int]] = []
    clean_bound = 0
    exact_digest = True
    if mode == "pim-oblivious" and policy == "zero" and not fused:
        clean_packets = submitted_packets(work_chunks)
        clean_compute = sum(
            ceil_div(size // 4, NATIVE_CLEANER_VALIDATION_LANES)
            for _, size in work_chunks
        )
        clean_bound = phase_bound(2 * len(work_chunks), 2 * clean_packets, clean_compute)
        exact_digest = len(work_chunks) <= 1
        for first in range(0, len(work_chunks), 2):
            batch = work_chunks[first:first + 2]
            events.extend((1, address, size) for address, size in batch)
            events.extend((2, address, size) for address, size in batch)
    elif fused:
        pass
    elif mode == "pim-oblivious" and policy == "mean":
        clean_packets = submitted_packets(raw_chunks)
        clean_compute = 2 * sum(
            ceil_div(size // 4, NATIVE_CLEANER_VALIDATION_LANES)
            for _, size in raw_chunks
        )
        clean_bound = phase_bound(3 * len(raw_chunks), 3 * clean_packets, clean_compute)
        events.extend((1, address, size) for address, size in raw_chunks)
        for address, size in raw_chunks:
            events.extend(((1, address, size), (2, address, size)))
    else:
        require(mode == "off", f"unsupported mode/policy {mode}/{policy}")

    centroid_events = [
        (3, NATIVE_DATA_BASE + (cluster * points // clusters) * record_bytes,
         record_bytes)
        for cluster in range(clusters)
    ]
    events.extend(centroid_events)
    for iteration in range(iterations):
        if fused and iteration == 0:
            for address, size in work_chunks:
                events.extend(((3, address, size), (2, address, size)))
        else:
            events.extend((3, address, size) for address, size in work_chunks)
    work_actions = clusters + iterations * len(work_chunks) + (len(work_chunks) if fused else 0)
    work_packets = (
        submitted_packets((address, size) for _, address, size in centroid_events)
        + (iterations + (1 if fused else 0)) * submitted_packets(work_chunks)
    )
    init = ceil_div(clusters * dims, NATIVE_CLEANER_VALIDATION_LANES)
    reset = init + ceil_div(clusters, NATIVE_CLEANER_VALIDATION_LANES)
    update = reset
    scan_cycles = []
    for _, size in work_chunks:
        records = size // record_bytes
        scan_cycles.append(ceil_div(
            3 * records * clusters * dims + 2 * records * dims,
            NATIVE_KMEANS_ARITHMETIC_CORES,
        ))
    digest_cycles = ceil_div(4 * clusters * dims, NATIVE_CLEANER_VALIDATION_LANES)
    scan_total = iterations * sum(scan_cycles)
    auxiliary = init + iterations * (reset + update) + digest_cycles
    validation = init if fused else 0
    write_bound = 0
    overlap = 0
    if fused:
        for (address, size), classification in zip(work_chunks, scan_cycles):
            records = size // record_bytes
            validation += ceil_div(records * dims, NATIVE_CLEANER_VALIDATION_LANES)
            bound = NATIVE_BOUND_ACTION_CYCLES + submitted_packets([(address, size)]) * NATIVE_BOUND_PACKET_CYCLES
            write_bound += bound
            overlap += min(classification, bound)
    scheduled_compute = scan_total + auxiliary + validation
    work_bound = phase_bound(work_actions, work_packets, scheduled_compute) - overlap

    digest = FNV1A64_OFFSET
    reads = writes = read_packets = write_packets = transferred = 0
    for operation, address, size in events:
        for value in (operation, address, size):
            digest = fnv_add_u64(digest, value)
        packets = submitted_packets([(address, size)])
        transferred += size
        if operation == 2:
            writes += 1
            write_packets += packets
        else:
            reads += 1
            read_packets += packets
    return {
        "trace_digest": f"{digest:016x}" if exact_digest else None,
        "read_actions": reads,
        "write_actions": writes,
        "read_packets": read_packets,
        "write_packets": write_packets,
        "transferred_bytes": transferred,
        "clean_bound_cycles": clean_bound,
        "work_bound_cycles": work_bound,
        "total_bound_cycles": clean_bound + work_bound,
        "fused_zero_kmeans": int(fused),
        "cleaner_validation_lanes": NATIVE_CLEANER_VALIDATION_LANES,
        "kmeans_arithmetic_cores": NATIVE_KMEANS_ARITHMETIC_CORES,
        "fused_validation_cycles": validation,
        "fused_write_bound_cycles": write_bound,
        "fused_overlap_credit_cycles": overlap,
    }


SECURE_FIELDS = (
    "total_ticks", "clean_ticks", "work_ticks", "simulator_ticks",
    "simulator_dma_bytes", "status_polls", "visible_reads", "visible_writes",
    "dma_read_actions", "dma_write_actions", "submitted_read_packets",
    "submitted_write_packets", "visible_bytes", "completion_cycles",
    "device_clock_period_ticks", "trace_digest", "native_zero_path",
    "fused_zero_kmeans", "cleaner_validation_lanes", "kmeans_arithmetic_cores",
    "fused_validation_cycles", "fused_write_bound_cycles",
    "fused_overlap_credit_cycles", "cpu_type", "mem_mode", "evidence_tier",
    "restore_strategy", "restore_with_cpu", "checkpoint_restore_semantics",
    "cpu_switch_used", "num_cpus", "cache_line_size_bytes", "guest_workload_sha256",
    "guest_driver_sha256",
)


@dataclass
class NativeEvidence:
    role: str
    manifest_path: Path
    document: Dict[str, Any]
    manifest_artifact: Dict[str, Any]
    native_rows: List[Dict[str, str]]
    paired_rows: List[Dict[str, str]]
    native_csv_artifact: Dict[str, Any]
    paired_csv_artifact: Dict[str, Any]


def validate_git_provenance(document: Mapping[str, Any], label: str) -> None:
    top = require_commit(document.get("top_commit"), f"{label}.top_commit")
    impica = require_commit(document.get("impica_commit"), f"{label}.impica_commit")
    require_sha256(document.get("source_diff_digest"), f"{label}.source_diff_digest")
    require_sha256(document.get("source_tree_sha256"), f"{label}.source_tree_sha256")
    provenance = document.get("git_provenance")
    require(isinstance(provenance, dict), f"{label}.git_provenance is required")
    require(provenance.get("status") == "valid_commits_and_worktree_views",
            f"{label}.git_provenance status is not valid")
    require(provenance.get("source_diff_digest") == document["source_diff_digest"],
            f"{label}.git_provenance digest mismatch")
    require(isinstance(provenance.get("source_diff_digest_encoding"), str)
            and provenance["source_diff_digest_encoding"],
            f"{label}.git_provenance encoding is missing")
    repos = provenance.get("repositories")
    require(isinstance(repos, dict) and set(repos) == {"top", "IMPICA"},
            f"{label}.git_provenance repository set is invalid")
    for name, expected in (("top", top), ("IMPICA", impica)):
        record = repos[name]
        require(isinstance(record, dict) and record.get("commit") == expected,
                f"{label}.git_provenance {name} commit mismatch")
        for field in ("tracked_diff_sha256", "untracked_paths_sha256", "status_sha256"):
            require_sha256(record.get(field), f"{label}.git_provenance.{name}.{field}")
        for field in ("tracked_diff_bytes", "untracked_path_count", "status_bytes"):
            require(isinstance(record.get(field), int) and record[field] >= 0,
                    f"{label}.git_provenance.{name}.{field} is invalid")


def validate_native_manifest_header(document: Mapping[str, Any], role: str) -> None:
    # Schema 6 introduced direct TimingSimpleCPU restoration and fail-closed Git
    # provenance.  Legacy schema 5 evidence is deliberately not promotable.
    require(document.get("schema_version") == 6,
            f"{role} native manifest must be schema_version=6")
    require(document.get("model_kind") == "gem5_native_e2e_kmeans",
            f"{role} is not direct native k-means evidence")
    parameters = document.get("parameters")
    require(isinstance(parameters, dict), f"{role}.parameters is missing")
    expected = {
        "points": FULL_POINTS,
        "dims": FULL_DIMS,
        "data_clusters": FULL_DATA_CLUSTERS,
        "workload": "kmeans",
        "workload_iterations": FULL_ITERATIONS,
        "workload_clusters": FULL_WORK_CLUSTERS,
    }
    for field, value in expected.items():
        require(parameters.get(field) == value,
                f"{role}.parameters.{field} must be {value!r}")
    expected_path = "fused" if role == "fused" else "separate"
    require(parameters.get("native_zero_path") == expected_path,
            f"{role} has wrong native_zero_path")
    require(list(parameters.get("seeds", [])) == list(FULL_SEEDS),
            f"{role} seed matrix is not canonical")
    rates = parameters.get("rates")
    require(isinstance(rates, (list, tuple)) and len(rates) == len(FULL_RATES)
            and all(abs(float(a) - b) <= 1e-12 for a, b in zip(rates, FULL_RATES)),
            f"{role} corruption-rate matrix is not canonical")
    require(set(parameters.get("policies", [])) == set(POLICIES),
            f"{role} policies are not zero/mean")
    require(set(parameters.get("modes", [])) == {"off", "pim-oblivious"},
            f"{role} modes are invalid")
    require(parameters.get("completion_observation") and
            "exactly one completion STATUS read" in parameters["completion_observation"],
            f"{role} does not declare the one-completion-read contract")
    bounds = parameters.get("fixed_phase_bound_cycles")
    require(isinstance(bounds, dict), f"{role} fixed bound description is missing")
    for field, value in (
        ("base", NATIVE_BOUND_BASE_CYCLES),
        ("per_dma_action", NATIVE_BOUND_ACTION_CYCLES),
        ("per_submitted_packet", NATIVE_BOUND_PACKET_CYCLES),
        ("cleaner_validation_lanes", NATIVE_CLEANER_VALIDATION_LANES),
        ("kmeans_arithmetic_cores", NATIVE_KMEANS_ARITHMETIC_CORES),
    ):
        require(bounds.get(field) == value, f"{role} bound constant {field} mismatch")

    cpu = document.get("cpu_configuration")
    require(isinstance(cpu, dict), f"{role}.cpu_configuration is missing")
    require(cpu.get("requested_cpu_type") == "timing", f"{role} is not timing CPU evidence")
    require(cpu.get("measurement_cpu_class") == "TimingSimpleCPU",
            f"{role} did not measure with TimingSimpleCPU")
    require(cpu.get("effective_measurement_mem_mode") == "timing",
            f"{role} did not measure in timing memory mode")
    require(cpu.get("num_cpus") == 4, f"{role} must use four measurement CPUs")
    require(cpu.get("checkpoint_cpu_type") == "timing"
            and cpu.get("checkpoint_mem_mode") == "timing",
            f"{role} checkpoint must be a timing-mode checkpoint")
    require(cpu.get("restore_strategy") == "direct",
            f"{role} did not use direct restore")
    require(cpu.get("restore_with_cpu") == "timing",
            f"{role} did not restore directly into timing CPUs")
    require(cpu.get("checkpoint_restore_semantics")
            == "same_cpu_class_direct_restore",
            f"{role} checkpoint must restore into the same timing CPU class")
    require(cpu.get("cpu_switch_used", cpu.get("switch_after_restore")) is False,
            f"{role} used a runtime CPU switch")
    require(cpu.get("switch_after_restore") is False,
            f"{role} switch_after_restore must be false")
    require(cpu.get("switch_warmup_ticks") == 0,
            f"{role} has nonzero CPU-switch warmup")
    require(document.get("evidence_tier")
            == "native_candidate_timing_direct_restore_padded_command_measurement",
            f"{role} has a non-promotable evidence tier")
    eligibility = document.get("immutable_input_provenance", {}).get(
        "publication_eligibility")
    require(isinstance(eligibility, dict) and eligibility.get("eligible") is True,
            f"{role} publication eligibility failed")
    require(not eligibility.get("ineligible_reasons"),
            f"{role} publication eligibility has rejection reasons")
    expected_criteria = {
        "timing_measurement",
        "same_class_timing_checkpoint",
        "direct_restore_without_cpu_switch",
        "strict_checkpoint_provenance",
        "strict_dataset_generation_transcript",
        "non_quick_publication_matrix",
        "full_36_case_matrix",
        "valid_top_and_impica_commits",
    }
    criteria = eligibility.get("criteria")
    require(isinstance(criteria, dict) and set(criteria) == expected_criteria
            and all(value is True for value in criteria.values()),
            f"{role} publication criteria do not all pass")
    validate_git_provenance(document, role)


def validate_immutable_provenance(document: Mapping[str, Any], role: str) -> None:
    immutable = document.get("immutable_input_provenance")
    require(isinstance(immutable, dict), f"{role} immutable provenance is missing")
    require(immutable.get("status") == "start_snapshot_revalidated_unchanged_at_finish",
            f"{role} immutable provenance did not pass")
    require(immutable.get("publication_eligible") is True,
            f"{role} immutable provenance is not publication eligible")
    snapshot = immutable.get("start_snapshot")
    require(isinstance(snapshot, dict), f"{role} start snapshot is missing")
    snapshot_digest = require_sha256(immutable.get("snapshot_sha256"),
                                     f"{role}.snapshot_sha256")
    require(canonical_sha256(snapshot) == snapshot_digest,
            f"{role} immutable snapshot digest does not reconstruct")
    finish = immutable.get("finish_revalidation")
    require(isinstance(finish, dict)
            and finish.get("status") == "exact_object_equality_pass"
            and finish.get("snapshot_sha256") == snapshot_digest,
            f"{role} finish snapshot revalidation failed")
    artifacts = snapshot.get("artifacts")
    required_artifacts = {
        "gem5_opt", "aarch64_guest", "test_driver_ko", "disk_image", "kernel",
        "dtb", "bootloader", "kmeans_oracle", "dataset_generator", "dataset_wrapper",
    }
    require(isinstance(artifacts, dict) and set(artifacts) >= required_artifacts,
            f"{role} immutable artifact set is incomplete")
    for name in required_artifacts:
        artifact_core(artifacts[name], f"{role}.snapshot.artifacts.{name}")
    checkpoint_snapshot = snapshot.get("checkpoint")
    require(isinstance(checkpoint_snapshot, dict), f"{role} checkpoint snapshot is missing")
    require_sha256(checkpoint_snapshot.get("m5_cpt_sha256"), f"{role}.checkpoint.m5_cpt_sha256")
    require_sha256(checkpoint_snapshot.get("selected_checkpoint_tree_sha256"),
                   f"{role}.checkpoint.selected_checkpoint_tree_sha256")
    selected = checkpoint_snapshot.get("selected_checkpoint_files")
    require(isinstance(selected, list) and selected,
            f"{role} selected checkpoint file list is empty")
    for index, record in enumerate(selected):
        artifact_core(record, f"{role}.selected_checkpoint_files[{index}]")
    artifact_core(snapshot.get("checkpoint_provenance"),
                  f"{role}.snapshot.checkpoint_provenance")
    artifact_core(snapshot.get("dataset_generation_manifest"),
                  f"{role}.snapshot.dataset_generation_manifest")
    datasets = snapshot.get("selected_dataset_artifacts")
    require(isinstance(datasets, list) and len(datasets) == 48,
            f"{role} must bind exactly 48 selected dataset artifacts")
    for index, record in enumerate(datasets):
        artifact_core(record, f"{role}.selected_dataset_artifacts[{index}]")

    checkpoint = document.get("checkpoint")
    require(isinstance(checkpoint, dict), f"{role} checkpoint record is missing")
    require(checkpoint.get("selected_checkpoint_tree_sha256")
            == checkpoint_snapshot["selected_checkpoint_tree_sha256"],
            f"{role} checkpoint tree identity mismatch")
    provenance = checkpoint.get("provenance")
    require(isinstance(provenance, dict)
            and provenance.get("status") == "schema_1_checkpoint_lineage_validated"
            and provenance.get("publication_eligible") is True,
            f"{role} strict checkpoint provenance failed")
    artifact_core(provenance.get("artifact"), f"{role}.checkpoint.provenance.artifact")
    creation_kind = provenance.get("creation_kind")
    require(creation_kind in {"cold_boot", "timing_recheckpoint_from_parent"},
            f"{role} checkpoint creation lineage is missing")
    if creation_kind == "timing_recheckpoint_from_parent":
        require_sha256(provenance.get("parent_checkpoint_tree_sha256"),
                       f"{role}.checkpoint.parent_checkpoint_tree_sha256")
    else:
        require(provenance.get("parent_checkpoint_tree_sha256") is None,
                f"{role} cold-boot checkpoint unexpectedly declares a parent")
    expected_creators = {
        "baseline_runner", "checkpoint_creator", "common_helpers",
        "guest_checkpoint_script", "provenance_helper",
    }
    if creation_kind == "cold_boot":
        expected_creators.add("disk_preparer")
    require(set(provenance.get("creator_inputs_validated", [])) == expected_creators,
            f"{role} checkpoint creator inputs were not fully validated")

    generation = document.get("dataset_generation_provenance")
    require(isinstance(generation, dict)
            and generation.get("status") == "supplied_strictly_validated_generation_transcript",
            f"{role} strict dataset generation transcript is missing")
    artifact_core(generation.get("artifact"), f"{role}.dataset_generation.artifact")
    require(generation.get("artifact") == snapshot.get("dataset_generation_manifest"),
            f"{role} generation-manifest identity differs from immutable snapshot")
    validated = generation.get("validated_parameters")
    require(isinstance(validated, dict), f"{role} validated generation parameters missing")
    for field, value in (("points", FULL_POINTS), ("dims", FULL_DIMS),
                         ("clusters", FULL_DATA_CLUSTERS)):
        require(validated.get(field) == value,
                f"{role} generation parameter {field} mismatch")
    require(list(validated.get("seeds", [])) == list(FULL_SEEDS),
            f"{role} generation seeds mismatch")
    gen_rates = validated.get("rates", [])
    require(len(gen_rates) == 4 and all(abs(float(a) - b) <= 1e-12
                                       for a, b in zip(gen_rates, FULL_RATES)),
            f"{role} generation rates mismatch")
    require(validated.get("distribution") == "balanced",
            f"{role} generation distribution must be balanced")
    outputs = generation.get("validated_outputs")
    require(isinstance(outputs, list) and len(outputs) == 48,
            f"{role} generation transcript must validate 48 outputs")
    for index, record in enumerate(outputs):
        artifact_core(record, f"{role}.validated_outputs[{index}]")


def expected_case_ids(native_zero_path: str) -> Dict[str, Tuple[int, float, str]]:
    result: Dict[str, Tuple[int, float, str]] = {}
    for seed in FULL_SEEDS:
        for rate in FULL_RATES:
            stem = f"s{seed:03d}_r{int(round(rate * 100)):03d}"
            zero_suffix = "pim_zero_fused" if native_zero_path == "fused" else "pim_zero"
            result[f"{stem}_off"] = (seed, rate, "off")
            result[f"{stem}_{zero_suffix}"] = (seed, rate, "zero")
            result[f"{stem}_pim_mean"] = (seed, rate, "mean")
    return result


def validate_reference_and_metadata(document: Mapping[str, Any],
                                    rows: Sequence[Mapping[str, str]], role: str) -> None:
    reference = document.get("reference")
    require(isinstance(reference, dict)
            and reference.get("kind") == "host_kmeans_fixed_iteration_oracle",
            f"{role} reference is not the host fixed-iteration oracle")
    artifact_core(reference.get("binary"), f"{role}.reference.binary")
    records = reference.get("records")
    require(isinstance(records, list) and len(records) == 36,
            f"{role} requires 36 independent oracle records")
    by_case = {record.get("case_id"): record for record in records if isinstance(record, dict)}
    require(len(by_case) == 36, f"{role} has duplicate/missing oracle case IDs")
    for row in rows:
        case_id = row["case_id"]
        record = by_case.get(case_id)
        require(record is not None, f"{role} lacks oracle record for {case_id}")
        require(record.get("points") == FULL_POINTS and record.get("dims") == FULL_DIMS
                and record.get("clusters") == FULL_WORK_CLUSTERS
                and record.get("iterations") == FULL_ITERATIONS
                and record.get("dirty_remaining") == 0,
                f"{role} oracle shape/cleanliness mismatch for {case_id}")
        require(record.get("digest") == row["output_digest"],
                f"{role} oracle digest mismatch for {case_id}")
        require(record.get("dataset_sha256") == row["input_sha256"],
                f"{role} oracle input hash mismatch for {case_id}")
    metadata = document.get("dataset_metadata")
    require(isinstance(metadata, list) and len(metadata) == 12,
            f"{role} must contain 12 dataset metadata records")
    seen = set()
    metadata_by_cell = {}
    for index, record in enumerate(metadata):
        require(isinstance(record, dict), f"{role} dataset metadata {index} is invalid")
        seed = record.get("seed")
        rate = record.get("dirty_frac_requested")
        require(seed in FULL_SEEDS and any(abs(float(rate) - value) <= 1e-12 for value in FULL_RATES),
                f"{role} dataset metadata matrix value is invalid")
        require((seed, round(float(rate), 9)) not in seen,
                f"{role} duplicate dataset metadata matrix cell")
        seen.add((seed, round(float(rate), 9)))
        metadata_by_cell[(seed, round(float(rate), 9))] = record
        require(record.get("points") == FULL_POINTS and record.get("dims") == FULL_DIMS
                and record.get("clusters") == FULL_DATA_CLUSTERS,
                f"{role} dataset metadata shape mismatch")
        require(record.get("distribution_name") == "balanced",
                f"{role} dataset distribution is not balanced")
        files = record.get("files")
        require(isinstance(files, dict) and set(files) == {"clean", "dirty", "labels"},
                f"{role} dataset file metadata is incomplete")
        for kind in files:
            artifact_core(files[kind], f"{role}.dataset_metadata[{index}].{kind}")
        artifact_core(record.get("metadata_file"), f"{role}.dataset_metadata[{index}].metadata_file")
    require(seen == {(seed, round(rate, 9)) for seed in FULL_SEEDS for rate in FULL_RATES},
            f"{role} dataset metadata matrix is incomplete")
    for row in rows:
        seed = int(row["seed"])
        paired_rate = round(float(row["paired_corruption_frac"]), 9)
        record = metadata_by_cell[(seed, paired_rate)]
        files = record["files"]
        require(row["clean_sha256"] == files["clean"]["sha256"]
                and row["dirty_sha256"] == files["dirty"]["sha256"],
                f"{role} row {row['case_id']} hashes differ from dataset metadata")
        expected_kind = row["input_kind"]
        require(row["input_sha256"] == files[expected_kind]["sha256"]
                and int(row["dataset_file_bytes"]) == files[expected_kind]["bytes"]
                and Path(row["dataset_file"]).name == files[expected_kind]["path"],
                f"{role} row {row['case_id']} input identity differs from metadata")


def validate_native_rows(rows: List[Dict[str, str]], document: Mapping[str, Any],
                         role: str) -> Dict[str, Dict[str, str]]:
    require(len(rows) == 36, f"{role} native CSV must contain 36 rows")
    path = "fused" if role == "fused" else "separate"
    expected_ids = expected_case_ids(path)
    by_case = {row.get("case_id"): row for row in rows}
    require(len(by_case) == 36 and set(by_case) == set(expected_ids),
            f"{role} native case set does not match the canonical 36 cases")
    artifacts = document["immutable_input_provenance"]["start_snapshot"]["artifacts"]
    expected_guest = artifacts["aarch64_guest"]["sha256"]
    expected_driver = artifacts["test_driver_ko"]["sha256"]
    attestation = document.get("guest_artifact_attestation")
    require(isinstance(attestation, dict)
            and attestation.get("status") == "pass"
            and attestation.get("kind")
            == "atomic_guest_hash_preflight_same_checkpoint_and_disk"
            and attestation.get("purpose")
            == "byte_attestation_only_excluded_from_timing_evidence",
            f"{role} guest artifact attestation is missing or invalid")
    require(attestation.get("guest_workload_sha256") == expected_guest
            and attestation.get("guest_driver_sha256") == expected_driver,
            f"{role} guest attestation executable hashes mismatch")
    attestation_cpu = attestation.get("cpu_configuration")
    require(isinstance(attestation_cpu, dict)
            and attestation_cpu.get("requested_cpu_type") == "atomic"
            and attestation_cpu.get("measurement_cpu_class") == "AtomicSimpleCPU"
            and attestation_cpu.get("effective_mem_mode") == "atomic"
            and attestation_cpu.get("checkpoint_cpu_type") == "timing"
            and attestation_cpu.get("cpu_switch_used") is False
            and attestation_cpu.get("num_cpus") == 4,
            f"{role} byte attestation CPU record is invalid")
    attested_datasets = attestation.get("datasets")
    require(isinstance(attested_datasets, list)
            and attestation.get("unique_dataset_files") == 24
            and len(attested_datasets) == 24,
            f"{role} byte attestation must cover exactly 24 guest inputs")
    attested_hashes = []
    attested_paths = set()
    for index, record in enumerate(attested_datasets):
        require(isinstance(record, dict)
                and isinstance(record.get("guest_path"), str)
                and record["guest_path"] not in attested_paths,
                f"{role} guest attestation dataset {index} is invalid")
        attested_paths.add(record["guest_path"])
        attested_hashes.append(require_sha256(
            record.get("sha256"), f"{role}.guest_attestation.datasets[{index}]"
        ))
    groups: Dict[Tuple[str, str, str], List[Mapping[str, str]]] = defaultdict(list)
    for case_id, row in by_case.items():
        label = f"{role}:{case_id}"
        seed, rate, slot = expected_ids[case_id]
        mode = "off" if slot == "off" else "pim-oblivious"
        policy = "zero" if slot == "off" else slot
        row_path = "fused" if slot == "zero" and role == "fused" else "separate"
        require(row.get("model_kind") == "gem5_native_e2e_kmeans"
                and row.get("workload") == "kmeans", f"{label} is not native k-means")
        require(parse_int(row, "native_e2e", label) == 1,
                f"{label} does not declare native end-to-end execution")
        require(row.get("cleaning_mode") == mode and row.get("imputation") == policy,
                f"{label} mode/policy mismatch")
        require(row.get("native_zero_path") == row_path,
                f"{label} native zero path mismatch")
        require(parse_int(row, "points", label, minimum=1) == FULL_POINTS
                and parse_int(row, "dims", label, minimum=1) == FULL_DIMS
                and parse_int(row, "iterations", label, minimum=1) == FULL_ITERATIONS
                and parse_int(row, "clusters", label, minimum=1) == FULL_WORK_CLUSTERS
                and parse_int(row, "seed", label) == seed,
                f"{label} public shape mismatch")
        expected_input_rate = 0.0 if slot == "off" else rate
        require(abs(parse_float(row, "corruption_frac", label) - expected_input_rate) <= 1e-9,
                f"{label} input corruption fraction mismatch")
        require(abs(parse_float(row, "paired_corruption_frac", label) - rate) <= 1e-9,
                f"{label} paired corruption fraction mismatch")
        require(row.get("input_kind") == ("clean" if slot == "off" else "dirty"),
                f"{label} clean/dirty assignment mismatch")
        for field in ("input_sha256", "clean_sha256", "dirty_sha256",
                      "guest_workload_sha256", "guest_driver_sha256",
                      "guest_dataset_sha256"):
            require_sha256(row.get(field), f"{label}.{field}")
        require(row["guest_workload_sha256"] == expected_guest
                and row["guest_driver_sha256"] == expected_driver,
                f"{label} guest executable hashes mismatch immutable inputs")
        require(row["guest_dataset_sha256"] == row["input_sha256"],
                f"{label} guest dataset hash mismatch")
        require(row.get("guest_artifact_attestation_kind")
                == "atomic_guest_hash_preflight_same_checkpoint_and_disk",
                f"{label} does not bind the accepted byte attestation")
        expected_input_hash = row["clean_sha256"] if slot == "off" else row["dirty_sha256"]
        require(row["input_sha256"] == expected_input_hash,
                f"{label} input hash does not match its clean/dirty assignment")
        payload_bytes = FULL_POINTS * FULL_DIMS * 4
        require(parse_int(row, "payload_bytes", label) == payload_bytes
                and parse_int(row, "public_input_bytes", label) == payload_bytes + 32
                and parse_int(row, "dataset_file_bytes", label) == payload_bytes + 32,
                f"{label} public dataset byte geometry mismatch")
        require(parse_int(row, "correctness", label) == 1,
                f"{label} correctness failed")
        output = digest16(row, "output_digest", label)
        require(output == digest16(row, "reference_output_digest", label)
                == digest16(row, "host_oracle_output_digest", label),
                f"{label} guest/reference/host output digests differ")
        require(row.get("reference_kind") == "host_kmeans_fixed_iteration_oracle",
                f"{label} reference kind is invalid")
        require(row.get("cpu_type") == "timing" and row.get("cpu_class") == "TimingSimpleCPU"
                and row.get("mem_mode") == "timing", f"{label} is not TimingSimpleCPU evidence")
        require(row.get("evidence_tier")
                == "native_candidate_timing_direct_restore_padded_command_measurement",
                f"{label} has a non-promotable evidence tier")
        require(row.get("checkpoint_cpu_type") == "timing"
                and row.get("restore_strategy") == "direct"
                and row.get("restore_with_cpu") == "timing"
                and row.get("checkpoint_restore_semantics")
                == "same_cpu_class_direct_restore",
                f"{label} same-class direct timing restore record is invalid")
        require(parse_bool(row, "cpu_switch_used", label) is False
                and parse_int(row, "cpu_switch_warmup_ticks", label) == 0,
                f"{label} used a CPU switch")
        require(parse_int(row, "num_cpus", label) == 4
                and parse_int(row, "cache_line_size_bytes", label) == DMA_PACKET_BYTES,
                f"{label} CPU/cache public configuration mismatch")

        transcript = expected_transcript(mode, policy, row_path)
        expected_latency = (
            "fixed_schedule_padded_native_device_command_with_public_"
            "iteration0_compute_write_overlap"
            if transcript["fused_zero_kmeans"]
            else "fixed_schedule_padded_native_device_command"
        )
        require(row.get("latency_semantics") == expected_latency,
                f"{label} latency semantics do not match its execution path")
        clock = parse_int(row, "device_clock_period_ticks", label, minimum=1)
        total = parse_int(row, "total_ticks", label, minimum=1)
        clean = parse_int(row, "clean_ticks", label)
        work = parse_int(row, "work_ticks", label, minimum=1)
        completion = parse_int(row, "completion_cycles", label, minimum=1)
        require(parse_int(row, "status_polls", label) == 2,
                f"{label} must perform one acceptance and one completion STATUS read")
        require(total == clean + work == parse_int(row, "simulator_ticks", label),
                f"{label} total/phase/simulator tick accounting mismatch")
        require(completion == ceil_div(total, clock),
                f"{label} completion-cycle conversion mismatch")
        require(clean == transcript["clean_bound_cycles"] * clock
                and work == transcript["work_bound_cycles"] * clock
                and total == transcript["total_bound_cycles"] * clock
                and completion == transcript["total_bound_cycles"],
                f"{label} fixed public completion arithmetic mismatch")
        observed_expected = {
            "dma_read_actions": "read_actions",
            "dma_write_actions": "write_actions",
            "submitted_read_packets": "read_packets",
            "submitted_write_packets": "write_packets",
            "simulator_dma_bytes": "transferred_bytes",
            "visible_bytes": "transferred_bytes",
            "fused_zero_kmeans": "fused_zero_kmeans",
            "cleaner_validation_lanes": "cleaner_validation_lanes",
            "kmeans_arithmetic_cores": "kmeans_arithmetic_cores",
            "fused_validation_cycles": "fused_validation_cycles",
            "fused_write_bound_cycles": "fused_write_bound_cycles",
            "fused_overlap_credit_cycles": "fused_overlap_credit_cycles",
        }
        for observed, expected in observed_expected.items():
            require(parse_int(row, observed, label) == transcript[expected],
                    f"{label}.{observed} differs from reconstructed public transcript")
        require(parse_int(row, "visible_reads", label) == transcript["read_actions"]
                and parse_int(row, "visible_writes", label) == transcript["write_actions"],
                f"{label} visible-action aliases mismatch")
        trace = digest16(row, "trace_digest", label)
        if transcript["trace_digest"] is not None:
            require(trace == transcript["trace_digest"],
                    f"{label} FNV trace digest does not reconstruct")
        groups[(mode, policy, row_path)].append(row)

    require(set(attested_hashes) == {row["input_sha256"] for row in rows},
            f"{role} guest attestation hashes do not cover all native inputs")

    for key, group in groups.items():
        for field in SECURE_FIELDS:
            require(len({row.get(field) for row in group}) == 1,
                    f"{role} fixed transcript differs across secrets for {key}, field {field}")
    return by_case


def validate_paired_rows(rows: List[Dict[str, str]], native: Mapping[str, Mapping[str, str]],
                         role: str) -> List[Dict[str, str]]:
    require(len(rows) == 24, f"{role} paired CSV must contain 24 rows")
    expected_keys = {(seed, round(rate, 9), policy)
                     for seed in FULL_SEEDS for rate in FULL_RATES for policy in POLICIES}
    by_key: Dict[Tuple[int, float, str], Dict[str, str]] = {}
    for row in rows:
        label = f"{role}:paired[{len(by_key)}]"
        seed = parse_int(row, "seed", label)
        rate = round(parse_float(row, "corruption_frac", label), 9)
        policy = row.get("policy")
        key = (seed, rate, policy)
        require(key in expected_keys and key not in by_key,
                f"{label} has duplicate or noncanonical seed/rate/policy")
        baseline_id = row.get("baseline_case_id")
        cleaned_id = row.get("cleaned_case_id")
        require(baseline_id in native and cleaned_id in native,
                f"{label} refers to missing native cases")
        baseline, cleaned = native[baseline_id], native[cleaned_id]
        require(cleaned.get("imputation") == policy,
                f"{label} cleaned policy mismatch")
        require(row.get("native_zero_path") == cleaned.get("native_zero_path"),
                f"{label} native zero path differs from native CSV")
        require(parse_int(row, "points", label, minimum=1) == FULL_POINTS
                and parse_int(row, "dims", label, minimum=1) == FULL_DIMS
                and parse_int(row, "clusters", label, minimum=1) == FULL_WORK_CLUSTERS
                and parse_int(row, "iterations", label, minimum=1) == FULL_ITERATIONS,
                f"{label} public workload shape mismatch")
        for field in (
            "model_kind", "evidence_tier", "cpu_type", "cpu_class", "mem_mode",
            "checkpoint_cpu_type", "restore_strategy", "restore_with_cpu",
            "checkpoint_restore_semantics", "num_cpus", "cache_line_size_bytes",
            "guest_workload_sha256", "guest_driver_sha256",
        ):
            require(row.get(field) == baseline.get(field),
                    f"{label}.{field} differs from baseline native CSV")
        require(parse_bool(row, "cpu_switch_used", label) is False,
                f"{label} reports a CPU switch")
        for field, source in (
            ("baseline_total_ticks", (baseline, "total_ticks")),
            ("cleaned_total_ticks", (cleaned, "total_ticks")),
            ("clean_ticks", (cleaned, "clean_ticks")),
            ("baseline_work_ticks", (baseline, "work_ticks")),
            ("cleaned_work_ticks", (cleaned, "work_ticks")),
            ("baseline_status_polls", (baseline, "status_polls")),
            ("cleaned_status_polls", (cleaned, "status_polls")),
        ):
            require(parse_int(row, field, label) == int(source[0][source[1]]),
                    f"{label}.{field} differs from native CSV")
        baseline_ticks = int(baseline["total_ticks"])
        cleaned_ticks = int(cleaned["total_ticks"])
        incremental = cleaned_ticks - baseline_ticks
        work_delta = int(cleaned["work_ticks"]) - int(baseline["work_ticks"])
        require(parse_int(row, "incremental_ticks", label) == incremental
                and parse_int(row, "expected_incremental_ticks", label) == incremental,
                f"{label} incremental tick arithmetic mismatch")
        require(parse_int(row, "work_tick_delta", label) == work_delta
                and parse_int(row, "expected_work_tick_delta", label) == work_delta,
                f"{label} work tick delta mismatch")
        expected_pct = incremental * 100.0 / baseline_ticks
        require(abs(parse_float(row, "measured_overhead_pct", label) - expected_pct) <= 5e-12
                and abs(parse_float(row, "fixed_schedule_overhead_pct", label) - expected_pct) <= 5e-12,
                f"{label} overhead percentage arithmetic mismatch")
        require(parse_int(row, "correctness", label) == 1
                and parse_int(row, "baseline_status_polls", label) == 2
                and parse_int(row, "cleaned_status_polls", label) == 2,
                f"{label} correctness/two-read contract failed")
        require(digest16(row, "baseline_output_digest", label) == baseline["output_digest"]
                and digest16(row, "cleaned_output_digest", label) == cleaned["output_digest"]
                and digest16(row, "baseline_trace_digest", label) == baseline["trace_digest"]
                and digest16(row, "cleaned_trace_digest", label) == cleaned["trace_digest"],
                f"{label} paired digest differs from native CSV")
        if rate == 0.0:
            require(baseline["output_digest"] == cleaned["output_digest"],
                    f"{label} clean input changed the k-means output")
        by_key[key] = row
    require(set(by_key) == expected_keys, f"{role} paired matrix is incomplete")
    return [by_key[key] for key in sorted(by_key)]


def load_native(path: Path, role: str) -> NativeEvidence:
    document, manifest_artifact = stable_json(path, f"{role} native manifest")
    validate_native_manifest_header(document, role)
    validate_immutable_provenance(document, role)
    validation = document.get("validation")
    require(isinstance(validation, dict) and validation.get("status") == "pass"
            and validation.get("rows") == 36 and validation.get("pairs") == 24
            and validation.get("secure_groups") == 3,
            f"{role} validation summary is not 36-row/24-pair pass")
    fixed_fields = validation.get("fixed_fields")
    require(isinstance(fixed_fields, list) and set(SECURE_FIELDS).issubset(fixed_fields),
            f"{role} validation summary omits fixed transcript fields")
    native_path = resolve_recorded_path(document.get("native_result_csv"), path,
                                        f"{role}.native_result_csv")
    paired_path = resolve_recorded_path(document.get("paired_result_csv"), path,
                                        f"{role}.paired_result_csv")
    native_rows, native_artifact = stable_csv(native_path, f"{role} native CSV")
    paired_rows, paired_artifact = stable_csv(paired_path, f"{role} paired CSV")
    native_by_case = validate_native_rows(native_rows, document, role)
    paired_rows = validate_paired_rows(paired_rows, native_by_case, role)
    validate_reference_and_metadata(document, native_rows, role)
    # Final TOCTOU re-hash after all cross-file checks.
    require(sha256_file(native_path) == native_artifact["sha256"]
            and sha256_file(paired_path) == paired_artifact["sha256"],
            f"{role} CSV changed during promotion validation")
    require(sha256_file(path.resolve()) == manifest_artifact["sha256"],
            f"{role} manifest changed during promotion validation")
    return NativeEvidence(role, path.resolve(), document, manifest_artifact,
                          native_rows, paired_rows, native_artifact, paired_artifact)


def comparable_native_identity(evidence: NativeEvidence) -> Dict[str, Any]:
    document = evidence.document
    snapshot = document["immutable_input_provenance"]["start_snapshot"]
    return {
        "top_commit": document["top_commit"],
        "impica_commit": document["impica_commit"],
        "source_diff_digest": document["source_diff_digest"],
        "source_tree_sha256": document["source_tree_sha256"],
        "docker_image": document.get("docker_image"),
        "dataset_id": document.get("dataset_id"),
        "dataset_generation_manifest": artifact_core(
            snapshot["dataset_generation_manifest"], "dataset generation identity"),
        "disk_image": artifact_core(snapshot["artifacts"]["disk_image"], "disk identity"),
        "checkpoint_tree_sha256": snapshot["checkpoint"]["selected_checkpoint_tree_sha256"],
        "checkpoint_provenance": artifact_core(snapshot["checkpoint_provenance"],
                                                "checkpoint provenance identity"),
        "guest": artifact_core(snapshot["artifacts"]["aarch64_guest"], "guest identity"),
        "driver": artifact_core(snapshot["artifacts"]["test_driver_ko"], "driver identity"),
        "oracle": artifact_core(snapshot["artifacts"]["kmeans_oracle"], "oracle identity"),
        "dataset_artifacts": [artifact_core(item, "dataset identity")
                              for item in snapshot["selected_dataset_artifacts"]],
    }


def comparable_rows(rows: Sequence[Mapping[str, str]], predicate) -> List[Dict[str, str]]:
    # config.ini commits to the case-specific readfile pathname, which includes
    # the run directory even when the CPU graph and every executable/data byte
    # are identical.  Its hash is validated within each native run but is not a
    # cross-run scientific identity field.
    excluded = {"run_id", "case_config_ini_sha256"}
    return sorted(
        ({key: value for key, value in row.items() if key not in excluded}
         for row in rows if predicate(row)),
        key=lambda row: (row.get("case_id", row.get("baseline_case_id", "")),
                         row.get("policy", "")),
    )


def validate_cross_evidence(fused: NativeEvidence, separate: NativeEvidence) -> None:
    require(comparable_native_identity(fused) == comparable_native_identity(separate),
            "fused/separate evidence does not share commits, sources, checkpoint, and datasets")
    fused_off_mean = comparable_rows(
        fused.native_rows, lambda row: row.get("cleaning_mode") == "off"
        or row.get("imputation") == "mean")
    separate_off_mean = comparable_rows(
        separate.native_rows, lambda row: row.get("cleaning_mode") == "off"
        or row.get("imputation") == "mean")
    require(fused_off_mean == separate_off_mean,
            "fused/separate off or mean native controls differ")
    fused_mean = comparable_rows(fused.paired_rows,
                                 lambda row: row.get("policy") == "mean")
    separate_mean = comparable_rows(separate.paired_rows,
                                    lambda row: row.get("policy") == "mean")
    require(fused_mean == separate_mean,
            "fused/separate paired mean controls differ")


def validate_assembly(path: Path) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    document, artifact = stable_json(path, "assembly audit")
    require(document.get("schema_version") == 1 and document.get("result") == "pass",
            "assembly audit did not pass schema 1")
    require(document.get("function") == "pim_clean_oblivious",
            "assembly audit targets the wrong function")
    require(document.get("forbidden_secret_dependent_branches") == [],
            "assembly audit found a secret-dependent branch")
    masks = document.get("required_mask_instructions")
    require(isinstance(masks, dict) and masks
            and all(value is True for value in masks.values()),
            "assembly audit lacks required mask/select instructions")
    require_sha256(document.get("assembly_sha256"), "assembly audit assembly_sha256")
    assembly_path = resolve_recorded_path(document.get("assembly"), path,
                                          "assembly audit assembly")
    require(assembly_path.is_file(), f"audited assembly is missing: {assembly_path}")
    require(sha256_file(assembly_path) == document["assembly_sha256"],
            "audited assembly bytes do not match the audit report")
    return document, artifact


def checkpoint_entry_map(snapshot: Mapping[str, Any]) -> Dict[str, Dict[str, Any]]:
    checkpoint = snapshot.get("checkpoint")
    require(isinstance(checkpoint, dict), "regression checkpoint identity is missing")
    entries = checkpoint.get("entries")
    require(isinstance(entries, list) and entries,
            "regression checkpoint tree entries are missing")
    result = {}
    for entry in entries:
        require(isinstance(entry, dict) and isinstance(entry.get("path"), str),
                "regression checkpoint tree entry is invalid")
        result[entry["path"]] = entry
    require_sha256(checkpoint.get("tree_sha256"), "regression checkpoint tree_sha256")
    return result


def validate_regression_source_matches(regression: Mapping[str, Any],
                                       native: NativeEvidence) -> None:
    start = regression["source_evidence_start"]
    native_snapshot = native.document["immutable_input_provenance"]["start_snapshot"]
    regression_disk = artifact_core(start.get("disk"), "regression source disk")
    native_disk = artifact_core(native_snapshot["artifacts"]["disk_image"], "native disk")
    require(regression_disk["bytes"] == native_disk["bytes"]
            and regression_disk["sha256"] == native_disk["sha256"],
            "regression source disk does not match native evidence disk")
    entries = checkpoint_entry_map(start)
    native_checkpoint = native_snapshot["checkpoint"]
    selected_name = native_checkpoint.get("selected_checkpoint")
    require(isinstance(selected_name, str) and selected_name,
            "native selected checkpoint name is missing")
    bound_tree = native_snapshot.get("bound_checkpoint_tree")
    require(isinstance(bound_tree, dict), "native bound checkpoint tree is missing")
    require_sha256(bound_tree.get("tree_sha256"), "native bound checkpoint tree")
    bound_files = bound_tree.get("files")
    require(isinstance(bound_files, list) and bound_files,
            "native bound checkpoint file list is missing")
    for record in bound_files:
        expected = artifact_core(record, "native bound checkpoint file")
        prefix = f"selected_checkpoint/{selected_name}/"
        if expected["path"].startswith(prefix):
            regression_path = f"{selected_name}/{expected['path'][len(prefix):]}"
        else:
            regression_path = expected["path"]
        candidate = entries.get(regression_path)
        require(isinstance(candidate, dict)
                and candidate.get("bytes") == expected["bytes"]
                and candidate.get("sha256") == expected["sha256"],
                f"regression checkpoint lacks matching {regression_path}")
    for name, expected_record in (
        ("checkpoint_provenance.json", native_snapshot["checkpoint_provenance"]),
    ):
        expected = artifact_core(expected_record, f"native {name}")
        candidate = entries.get(name)
        require(isinstance(candidate, dict)
                and candidate.get("bytes") == expected["bytes"]
                and candidate.get("sha256") == expected["sha256"],
                f"regression checkpoint does not match native {name}")


def validate_regression(path: Path, native: NativeEvidence) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    document, artifact = stable_json(path, "SE-PIM regression manifest")
    require(document.get("schema_version") == 2,
            "SE-PIM regression manifest must be schema_version=2")
    require(document.get("mode") == "full" and document.get("status") == "passed",
            "SE-PIM regression suite is not a passed full run")
    require(document.get("publication_eligible") is True,
            "SE-PIM regression suite is not publication eligible")
    promotability = document.get("promotability")
    require(isinstance(promotability, dict) and promotability.get("eligible") is True,
            "SE-PIM regression promotability gate failed")
    expected_checks = {
        "mode_is_full", "status_passed", "exact_case_matrix", "all_cases_passed",
        "network_disabled", "container_reference_pinned",
        "container_content_id_pinned", "source_evidence_immutable",
        "runtime_inputs_immutable", "injected_artifacts_immutable",
        "event_coverage_limitation_preserved",
    }
    checks = promotability.get("checks")
    require(isinstance(checks, dict) and set(checks) == expected_checks
            and all(value is True for value in checks.values())
            and promotability.get("ineligible_reasons") == []
            and isinstance(promotability.get("policy"), str)
            and promotability["policy"].strip(),
            "SE-PIM regression promotability checks do not all pass")
    require(document.get("source_evidence_immutable") is True
            and document.get("source_evidence_start") == document.get("source_evidence_end"),
            "SE-PIM regression source evidence changed")
    for prefix in ("runtime_inputs", "injected_artifacts"):
        start_inputs = document.get(prefix)
        end_inputs = document.get(f"{prefix}_end")
        require(document.get(f"{prefix}_immutable") is True
                and isinstance(start_inputs, dict) and start_inputs
                and start_inputs == end_inputs,
                f"SE-PIM regression {prefix} changed")
        for name, record in start_inputs.items():
            if isinstance(record, dict) and "sha256" in record:
                artifact_core(record, f"SE-PIM regression {prefix}.{name}")
    require(document.get("network") == "none",
            "SE-PIM regression containers did not use network=none")
    commands = document.get("commands")
    require(isinstance(commands, list) and commands
            and all(isinstance(command, dict) and command.get("network") == "none"
                    for command in commands),
            "SE-PIM regression command network records are incomplete")
    image = document.get("container_image")
    require(isinstance(image, dict), "SE-PIM regression image identity is missing")
    requested = image.get("requested", document.get("container_image_requested"))
    require(isinstance(requested, str) and PINNED_IMAGE_RE.fullmatch(requested) is not None,
            "SE-PIM regression image is not digest-pinned")
    require(image.get("requested_reference_pinned") is True,
            "SE-PIM regression image record does not attest a pinned reference")
    require(image.get("network", "none") == "none",
            "SE-PIM regression image record has non-none network")
    image_id = image.get("image_id")
    require(isinstance(image_id, str) and re.fullmatch(r"(?:sha256:)?[0-9a-f]{64}", image_id) is not None,
            "SE-PIM regression image_id is invalid")
    cases = document.get("cases")
    require(isinstance(cases, list) and len(cases) == 8,
            "SE-PIM regression must contain exactly eight cases")
    expected_case_order = [
        "table2_pass1", "table2_pass2", "dma_full", "controlled_full",
        "hashtable_canonical", "trace_cpu_full", "trace_sepim_full",
        "kmeans_legacy_full",
    ]
    by_id = {case.get("id"): case for case in cases if isinstance(case, dict)}
    require([case.get("id") for case in cases] == expected_case_order
            and set(by_id) == EXPECTED_REGRESSION_CASES,
            "SE-PIM regression case set is not the exact required eight")
    case_plan = document.get("case_plan")
    require(isinstance(case_plan, list)
            and [case.get("id") for case in case_plan if isinstance(case, dict)]
            == expected_case_order,
            "SE-PIM regression case plan is not the exact required eight")
    for case_id, case in by_id.items():
        require(case.get("pass") is True, f"SE-PIM regression case {case_id} failed")
        require(isinstance(case.get("validation"), dict),
                f"SE-PIM regression case {case_id} lacks validation")
        require(isinstance(case.get("checkpoint_role"), str)
                and case["checkpoint_role"],
                f"SE-PIM regression case {case_id} lacks checkpoint role")
        artifact_core(case.get("guest_script"), f"regression {case_id} guest script")
        artifact_core(case.get("terminal"), f"regression {case_id} terminal")
        output = case.get("output_tree")
        require(isinstance(output, dict), f"regression {case_id} output tree missing")
        require_sha256(output.get("tree_sha256"), f"regression {case_id} output tree")
    coverage = document.get("legacy_dma_event_coverage")
    require(isinstance(coverage, dict)
            and coverage.get("declared_event_ids") == [0, 1, 2, 3, 4, 5]
            and coverage.get("dedicated_dynamic_harness") is False
            and coverage.get("status") == "incomplete"
            and coverage.get("publication_claim_allowed") is False
            and isinstance(coverage.get("limitation"), str)
            and coverage["limitation"].strip(),
            "SE-PIM regression must explicitly retain incomplete legacy event coverage")
    validate_regression_source_matches(document, native)
    return document, artifact


def individual_records(fused: NativeEvidence,
                       separate: Optional[NativeEvidence]) -> List[Dict[str, Any]]:
    variants: List[Tuple[str, NativeEvidence, str]] = [
        ("fused-zero", fused, "zero"),
        ("separate-mean", separate or fused, "mean"),
    ]
    if separate is not None:
        variants.insert(1, ("separate-zero", separate, "zero"))
    output = []
    for variant, evidence, policy in variants:
        for row in evidence.paired_rows:
            if row["policy"] != policy:
                continue
            output.append({
                "variant": variant,
                "source_run_id": evidence.document["run_id"],
                "policy": policy,
                "native_zero_path": row["native_zero_path"],
                "seed": int(row["seed"]),
                "corruption_frac": f"{float(row['corruption_frac']):.6f}",
                "points": int(row["points"]),
                "dims": int(row["dims"]),
                "clusters": int(row["clusters"]),
                "iterations": int(row["iterations"]),
                "baseline_total_ticks": int(row["baseline_total_ticks"]),
                "cleaned_total_ticks": int(row["cleaned_total_ticks"]),
                "incremental_ticks": int(row["incremental_ticks"]),
                "clean_ticks": int(row["clean_ticks"]),
                "work_tick_delta": int(row["work_tick_delta"]),
                "device_clock_period_ticks": int(row["device_clock_period_ticks"]),
                "measured_overhead_pct": f"{float(row['measured_overhead_pct']):.12f}",
                "baseline_status_polls": int(row["baseline_status_polls"]),
                "cleaned_status_polls": int(row["cleaned_status_polls"]),
                "baseline_trace_digest": row["baseline_trace_digest"],
                "cleaned_trace_digest": row["cleaned_trace_digest"],
                "baseline_output_digest": row["baseline_output_digest"],
                "cleaned_output_digest": row["cleaned_output_digest"],
                "correctness": int(row["correctness"]),
            })
    return output


def summary_records(individual: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    groups: Dict[str, List[Mapping[str, Any]]] = defaultdict(list)
    for row in individual:
        groups[str(row["variant"])].append(row)
    result = []
    for variant in ("fused-zero", "separate-zero", "separate-mean"):
        rows = groups.get(variant)
        if not rows:
            continue
        percentages = [float(row["measured_overhead_pct"]) for row in rows]
        result.append({
            "variant": variant,
            "policy": rows[0]["policy"],
            "native_zero_path": rows[0]["native_zero_path"],
            "individual_runs": len(rows),
            "seeds": 3,
            "corruption_rates": 4,
            "baseline_total_ticks": rows[0]["baseline_total_ticks"],
            "cleaned_total_ticks": rows[0]["cleaned_total_ticks"],
            "incremental_ticks": rows[0]["incremental_ticks"],
            "mean_overhead_pct": f"{statistics.fmean(percentages):.12f}",
            "stddev_overhead_pct": f"{statistics.stdev(percentages):.12f}",
            "min_overhead_pct": f"{min(percentages):.12f}",
            "max_overhead_pct": f"{max(percentages):.12f}",
            "fixed_transcript": "pass",
            "correctness": "pass",
        })
    return result


def csv_bytes(rows: Sequence[Mapping[str, Any]]) -> bytes:
    require(bool(rows), "refusing to emit an empty promoted CSV")
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(rows[0].keys()), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def atomic_write(path: Path, data: bytes) -> None:
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    require(not temporary.exists(), f"temporary output already exists: {temporary}")
    try:
        with temporary.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def promote(*, fused_manifest: Path, separate_manifest: Optional[Path],
            regression_manifest: Path, assembly_audit: Path, run_id: str,
            out_root: Path) -> Path:
    require(RUN_ID_RE.fullmatch(run_id) is not None, "invalid promotion run ID")
    fused = load_native(fused_manifest, "fused")
    separate = load_native(separate_manifest, "separate") if separate_manifest else None
    if separate is not None:
        validate_cross_evidence(fused, separate)
    audit_document, audit_artifact = validate_assembly(assembly_audit)
    regression_document, regression_artifact = validate_regression(regression_manifest, fused)
    individual = individual_records(fused, separate)
    summary = summary_records(individual)

    out_root = out_root.resolve()
    destination = out_root / run_id
    require(not destination.exists(), f"refusing to overwrite promotion: {destination}")
    out_root.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{run_id}.tmp.", dir=str(out_root)))
    try:
        individual_data = csv_bytes(individual)
        summary_data = csv_bytes(summary)
        atomic_write(temporary / "individual.csv", individual_data)
        atomic_write(temporary / "summary.csv", summary_data)
        limitation = regression_document["legacy_dma_event_coverage"]["limitation"]
        manifest = {
            "schema_version": 1,
            "run_id": run_id,
            "status": "promoted",
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "claim_scope": (
                "direct TimingSimpleCPU native-device-command interval for canonical "
                "fixed-20 k-means; excludes file load, protected-buffer staging, "
                "lock/unlock, guest validation, and result-copy time"
            ),
            "canonical_matrix": {
                "points": FULL_POINTS,
                "dims": FULL_DIMS,
                "data_clusters": FULL_DATA_CLUSTERS,
                "workload_clusters": FULL_WORK_CLUSTERS,
                "iterations": FULL_ITERATIONS,
                "seeds": list(FULL_SEEDS),
                "corruption_rates": list(FULL_RATES),
                "raw_rows_per_native_manifest": 36,
                "paired_rows_per_native_manifest": 24,
            },
            "variants": [row["variant"] for row in summary],
            "source_evidence": {
                "fused_manifest": fused.manifest_artifact,
                "fused_native_csv": fused.native_csv_artifact,
                "fused_paired_csv": fused.paired_csv_artifact,
                "separate_manifest": separate.manifest_artifact if separate else None,
                "separate_native_csv": separate.native_csv_artifact if separate else None,
                "separate_paired_csv": separate.paired_csv_artifact if separate else None,
                "regression_manifest": regression_artifact,
                "assembly_audit": audit_artifact,
            },
            "validation": {
                "native_schema": 6,
                "timing_simple_cpu_direct_restore_no_switch": "pass",
                "checkpoint_and_dataset_immutable_provenance": "pass",
                "guest_and_input_hash_binding": "pass",
                "independent_output_reference": "pass",
                "one_status_poll": "pass",
                "fixed_transcript_across_equal_public_shapes": "pass",
                "independent_completion_and_dma_arithmetic": "pass",
                "dirty_count_result_absence": "pass",
                "source_csv_end_rehash": "pass",
                "fused_separate_cross_evidence": "pass" if separate else "not_supplied",
                "assembly_branch_audit": audit_document["result"],
                "sepim_full_regression_cases": 8,
                "sepim_source_immutable": True,
            },
            "limitations": [limitation],
            "outputs": {
                "summary_csv": {
                    "path": "summary.csv", "bytes": len(summary_data),
                    "sha256": sha256_bytes(summary_data),
                },
                "individual_csv": {
                    "path": "individual.csv", "bytes": len(individual_data),
                    "sha256": sha256_bytes(individual_data),
                },
            },
        }
        manifest_data = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
        atomic_write(temporary / "manifest.json", manifest_data)
        checksum = f"{sha256_bytes(manifest_data)}  manifest.json\n".encode("ascii")
        atomic_write(temporary / "manifest.json.sha256", checksum)
        # Re-hash all files immediately before the directory becomes visible.
        require(sha256_file(temporary / "summary.csv") == sha256_bytes(summary_data)
                and sha256_file(temporary / "individual.csv") == sha256_bytes(individual_data)
                and sha256_file(temporary / "manifest.json") == sha256_bytes(manifest_data),
                "promoted output changed before publication")
        os.rename(temporary, destination)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return destination


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("--fused-manifest", required=True, type=Path)
    value.add_argument("--separate-manifest", type=Path)
    value.add_argument("--regression-manifest", required=True, type=Path)
    value.add_argument("--assembly-audit", required=True, type=Path)
    value.add_argument("--run-id", required=True)
    value.add_argument("--out-root", type=Path, default=ROOT / "results" / "promoted")
    return value


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parser().parse_args(argv)
    try:
        destination = promote(
            fused_manifest=args.fused_manifest,
            separate_manifest=args.separate_manifest,
            regression_manifest=args.regression_manifest,
            assembly_audit=args.assembly_audit,
            run_id=args.run_id,
            out_root=args.out_root,
        )
    except (PromotionError, OSError) as error:
        print(f"[FAIL] {error}", file=sys.stderr)
        return 1
    print(f"[PASS] promoted publication evidence: {destination}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
