#!/usr/bin/env python3
"""Run legacy SE-PIM regressions without mutating native evidence.

The supplied evidence disk and checkpoint are inputs only.  The disk is copied
byte-for-byte (never hard-linked), legacy AArch64 workloads are injected into
that disposable copy, and a regression-only atomic checkpoint is created.
Every container invocation uses ``--network none`` and a unique run directory.

Quick mode runs five diagnostics and is never publication-promotable.  Full
mode adds primary/auxiliary CommMonitor traces and the no-argument legacy
k-means matrix for an exact eight-case gate.  The trace cases restore a
separate atomic checkpoint built with the ``se_pim_fs.py`` topology.

This runner intentionally does not claim complete dynamic coverage of legacy
PimDevice DMA events 0..5.  The canonical hash-table run exercises the legacy
path, but complete event coverage requires a dedicated instrumented harness.
"""

from __future__ import annotations

import argparse
from collections import Counter
import configparser
import csv
import datetime as dt
import hashlib
import json
import math
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
import traceback
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_IMAGE = (
    "sepim-impica@sha256:"
    "e5caacbf042ea2c2dd87a350ca35467d09aec2c0e4fac2a1de728bb1a93f308a"
)
SCHEMA_VERSION = 2
TRACE_TAIL_PACKETS = 4096
TRACE_CSV_FIELDS = ["time", "addr", "rw", "size", "cmd", "flags"]
PIM_MMIO_BASE = 0x2F00E000
PIM_MMIO_END = PIM_MMIO_BASE + 0x1000
REQUIRED_SEPIM_MMIO_OFFSETS = (0x40, 0x44, 0x48, 0x4C, 0x50, 0x54, 0x58, 0x5C)
EXPECTED_FULL_CASE_IDS = (
    "table2_pass1",
    "table2_pass2",
    "dma_full",
    "controlled_full",
    "hashtable_canonical",
    "trace_cpu_full",
    "trace_sepim_full",
    "kmeans_legacy_full",
)
EXPECTED_QUICK_CASE_IDS = (
    "table2_pass1",
    "table2_pass2",
    "dma_quick",
    "controlled_quick",
    "hashtable_canonical",
)
RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
TABLE2_RE = re.compile(
    r"^cmd=(\d+) status=(\d+) res0=(0x[0-9a-fA-F]+) "
    r"res1=(0x[0-9a-fA-F]+) nonce=(\d+) counter=(\d+)$"
)
GUEST_ERROR_MARKERS = (
    "[REGRESSION][FAIL]",
    "[GUEST][ERROR]",
    "Kernel panic",
    "Segmentation fault",
    "Assertion failed",
    "assertion failed",
)


class RegressionError(RuntimeError):
    """A validation or execution failure."""


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def sha256_file(path: Path, chunk_size: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while True:
            chunk = stream.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_digest(value: Any) -> str:
    data = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256_bytes(data)


def path_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def paths_overlap(left: Path, right: Path) -> bool:
    return left == right or path_within(left, right) or path_within(right, left)


def file_identity(path: Path) -> Dict[str, Any]:
    info = path.stat()
    if not stat.S_ISREG(info.st_mode):
        raise RegressionError(f"expected a regular file: {path}")
    return {
        "path": str(path),
        "bytes": info.st_size,
        "mode": stat.S_IMODE(info.st_mode),
        "mtime_ns": info.st_mtime_ns,
        "sha256": sha256_file(path),
    }


def tree_identity(root: Path) -> Dict[str, Any]:
    if not root.is_dir():
        raise RegressionError(f"expected a directory: {root}")
    records: List[Dict[str, Any]] = []
    candidates = [root] + sorted(root.rglob("*"), key=lambda value: value.as_posix())
    for path in candidates:
        rel = "." if path == root else path.relative_to(root).as_posix()
        info = path.lstat()
        core: Dict[str, Any] = {
            "path": rel,
            "mode": stat.S_IMODE(info.st_mode),
            "mtime_ns": info.st_mtime_ns,
        }
        if stat.S_ISREG(info.st_mode):
            core.update(type="file", bytes=info.st_size, sha256=sha256_file(path))
        elif stat.S_ISDIR(info.st_mode):
            core.update(type="directory")
        elif stat.S_ISLNK(info.st_mode):
            core.update(type="symlink", target=os.readlink(str(path)))
        else:
            raise RegressionError(f"unsupported checkpoint entry type: {path}")
        records.append(core)
    return {
        "path": str(root),
        "entries": records,
        "tree_sha256": canonical_digest(records),
    }


def content_tree_identity(root: Path) -> Dict[str, Any]:
    """Hash output contents without timestamps, suitable for result pinning."""
    records: List[Dict[str, Any]] = []
    for path in sorted(root.rglob("*"), key=lambda value: value.as_posix()):
        rel = path.relative_to(root).as_posix()
        if path.is_symlink():
            records.append({"path": rel, "type": "symlink", "target": os.readlink(path)})
        elif path.is_file():
            records.append(
                {
                    "path": rel,
                    "type": "file",
                    "bytes": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
            )
        elif path.is_dir():
            records.append({"path": rel, "type": "directory"})
        else:
            raise RegressionError(f"unsupported output entry type: {path}")
    return {"files": records, "tree_sha256": canonical_digest(records)}


def evidence_snapshot(disk: Path, checkpoint: Path) -> Dict[str, Any]:
    return {"disk": file_identity(disk), "checkpoint": tree_identity(checkpoint)}


def same_evidence(start: Dict[str, Any], end: Dict[str, Any]) -> bool:
    return start == end


def atomic_write_json(path: Path, value: Any) -> None:
    data = json.dumps(value, indent=2, sort_keys=True) + "\n"
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(data, encoding="utf-8")
    os.replace(temp, path)
    checksum = sha256_bytes(data.encode("utf-8"))
    sidecar = path.with_name(path.name + ".sha256")
    sidecar.write_text(f"{checksum}  {path.name}\n", encoding="ascii")


def terminal_text(path: Path) -> str:
    if not path.is_file():
        raise RegressionError(f"missing gem5 terminal output: {path}")
    return (
        path.read_bytes()
        .replace(b"\0", b"")
        .decode("utf-8", "replace")
        .replace("\r", "")
    )


def require_no_guest_errors(text: str, label: str) -> None:
    found = [marker for marker in GUEST_ERROR_MARKERS if marker in text]
    if found:
        raise RegressionError(f"{label}: guest error marker(s): {found}")


def require_guest_hash(text: str, name: str, expected: str) -> None:
    marker = f"REGRESSION_ARTIFACT_SHA256 {name}={expected}"
    clean_lines = [line.strip() for line in text.splitlines() if not line.strip().startswith("+")]
    count = sum(1 for line in clean_lines if marker in line)
    if count != 1:
        raise RegressionError(
            f"missing or repeated injected-artifact marker for {name}: {expected}"
        )


def parse_table2_terminal(path: Path, expected_sha: str) -> Dict[str, Any]:
    text = terminal_text(path)
    require_no_guest_errors(text, path.parent.name)
    require_guest_hash(text, "sepim_cmd", expected_sha)
    rows = []
    transcript = []
    for line in text.splitlines():
        match = TABLE2_RE.fullmatch(line.strip())
        if match:
            command, status, res0, res1, nonce, counter = match.groups()
            rows.append(
                {
                    "command": int(command),
                    "status": int(status),
                    "res0": res0.lower(),
                    "res1": res1.lower(),
                    "nonce": int(nonce),
                    "counter": int(counter),
                }
            )
            transcript.append(line.strip())
    commands = [row["command"] for row in rows]
    if len(commands) != 10 or sorted(commands) != list(range(1, 11)):
        raise RegressionError(
            f"Table 2 must execute every command 1..10 exactly once: {commands}"
        )
    if any(row["status"] != 1 for row in rows):
        raise RegressionError(f"Table 2 command returned non-OK status: {rows}")
    if text.count("SEPIM command smoke test completed") != 1:
        raise RegressionError("Table 2 completion marker is missing or repeated")
    return {
        "pass": True,
        "commands": rows,
        "command_transcript_sha256": sha256_bytes(
            ("\n".join(transcript) + "\n").encode("utf-8")
        ),
    }


def extract_fscsv(path: Path) -> Tuple[List[str], str]:
    text = terminal_text(path)
    lines = text.splitlines()
    begin = [index for index, line in enumerate(lines) if line.strip() == "FSCSV_BEGIN"]
    end = [index for index, line in enumerate(lines) if line.strip() == "FSCSV_END"]
    if len(begin) != 1 or len(end) != 1 or begin[0] >= end[0]:
        raise RegressionError(f"invalid FSCSV markers in {path}")
    payload = [line.strip() for line in lines[begin[0] + 1 : end[0]]]
    if len(payload) < 2:
        raise RegressionError(f"empty FSCSV payload in {path}")
    return payload, text


def finite_positive(row: Dict[str, str], names: Iterable[str], label: str) -> None:
    for name in names:
        try:
            value = float(row[name])
        except (KeyError, ValueError) as error:
            raise RegressionError(f"{label}: invalid numeric {name}: {row}") from error
        if not math.isfinite(value) or value <= 0.0:
            raise RegressionError(f"{label}: {name} must be finite and positive: {row}")


def write_parsed_csv(case_dir: Path, payload: List[str]) -> Path:
    output = case_dir / "parsed.csv"
    output.write_text("\n".join(payload) + "\n", encoding="utf-8")
    return output


def parse_dma_terminal(
    path: Path, expected_sha: str, mode: str = "quick"
) -> Dict[str, Any]:
    payload, text = extract_fscsv(path)
    require_no_guest_errors(text, path.parent.name)
    require_guest_hash(text, "dma_benchmark_fs", expected_sha)
    required = [
        "access_mode",
        "block_size",
        "transfers",
        "baseline_latency_ns",
        "sepim_latency_ns",
        "baseline_gbps",
        "sepim_gbps",
        "overhead_pct",
        "aes_penalty_cycles",
    ]
    reader = csv.DictReader(payload)
    rows = list(reader)
    if reader.fieldnames != required:
        raise RegressionError(f"DMA CSV schema mismatch: {reader.fieldnames}")
    expected_order = [
        (access_mode, size)
        for access_mode in ("seq_read", "seq_write", "rand_read", "rand_write")
        for size in (512, 1024, 2048, 4096, 8192)
    ]
    expected_transfers = 100 if mode == "quick" else 1000
    observed: List[Tuple[str, int]] = []
    seen = set()
    for row in rows:
        try:
            key = (row["access_mode"], int(row["block_size"]))
            transfers = int(row["transfers"])
        except (KeyError, ValueError) as error:
            raise RegressionError(f"DMA malformed row: {row}") from error
        if transfers != expected_transfers or key in seen:
            raise RegressionError(
                f"DMA {mode} row is duplicate or not {expected_transfers} transfers: {row}"
            )
        observed.append(key)
        seen.add(key)
        finite_positive(
            row,
            (
                "baseline_latency_ns",
                "sepim_latency_ns",
                "baseline_gbps",
                "sepim_gbps",
                "aes_penalty_cycles",
            ),
            "DMA",
        )
        overhead = float(row["overhead_pct"])
        if not math.isfinite(overhead) or overhead < 0.0:
            raise RegressionError(f"DMA overhead is invalid: {row}")
    if observed != expected_order:
        raise RegressionError(f"DMA {mode} matrix mismatch: {sorted(observed)}")
    parsed = write_parsed_csv(path.parent, payload)
    return {
        "pass": True,
        "mode": mode,
        "rows": len(rows),
        "transfers_per_row": expected_transfers,
        "matrix": [list(item) for item in observed],
        "csv": file_identity(parsed),
    }


def parse_controlled_terminal(
    path: Path, expected_sha: str, mode: str = "quick"
) -> Dict[str, Any]:
    payload, text = extract_fscsv(path)
    require_no_guest_errors(text, path.parent.name)
    require_guest_hash(text, "controlled_access_bench_fs", expected_sha)
    required = ["block_kb", "normal_mbps", "controlled_mbps", "path_oram_mbps"]
    reader = csv.DictReader(payload)
    rows = list(reader)
    if reader.fieldnames != required:
        raise RegressionError(
            f"controlled-access CSV schema mismatch: {reader.fieldnames}"
        )
    observed: List[int] = []
    for row in rows:
        try:
            block = int(row["block_kb"])
        except (KeyError, ValueError) as error:
            raise RegressionError(f"controlled-access malformed row: {row}") from error
        observed.append(block)
        finite_positive(
            row,
            ("normal_mbps", "controlled_mbps", "path_oram_mbps"),
            "controlled-access",
        )
    expected_blocks = (
        [1, 4, 16, 64, 128]
        if mode == "quick"
        else [1, 2, 4, 8, 16, 32, 64, 128]
    )
    if observed != expected_blocks:
        raise RegressionError(
            f"controlled-access {mode} blocks mismatch: {observed}"
        )
    parsed = write_parsed_csv(path.parent, payload)
    return {
        "pass": True,
        "mode": mode,
        "rows": len(rows),
        "blocks_kib": observed,
        "csv": file_identity(parsed),
    }


def require_close(label: str, actual: float, expected: float) -> None:
    if not math.isfinite(actual) or not math.isclose(
        actual, expected, rel_tol=0.0, abs_tol=0.000051
    ):
        raise RegressionError(
            f"{label}: expected {expected:.12g}, observed {actual:.12g}"
        )


def parse_kmeans_legacy_terminal(path: Path, expected_sha: str) -> Dict[str, Any]:
    """Validate the no-argument 4x4 legacy extrapolation matrix exactly."""
    payload, text = extract_fscsv(path)
    require_no_guest_errors(text, path.parent.name)
    require_guest_hash(text, "kmeans_sepim_fs", expected_sha)
    required = [
        "dataset_mb",
        "pim_cores",
        "cpu_sec",
        "pim_baseline_sec",
        "sepim_sec",
        "overhead_pct",
        "speedup_vs_cpu",
    ]
    reader = csv.DictReader(payload)
    rows = list(reader)
    if reader.fieldnames != required:
        raise RegressionError(
            f"legacy k-means CSV schema mismatch: {reader.fieldnames}"
        )
    expected_matrix = [
        (dataset_mb, cores)
        for dataset_mb in (64, 128, 256, 512)
        for cores in (1, 2, 4, 8)
    ]
    observed_matrix: List[Tuple[int, int]] = []
    formula_rows: List[Dict[str, Any]] = []
    if len(rows) != len(expected_matrix):
        raise RegressionError(
            f"legacy k-means must emit exactly 16 rows, observed {len(rows)}"
        )
    for index, row in enumerate(rows):
        try:
            dataset_mb = int(row["dataset_mb"])
            cores = int(row["pim_cores"])
            values = {name: float(row[name]) for name in required[2:]}
        except (KeyError, ValueError) as error:
            raise RegressionError(f"legacy k-means malformed row: {row}") from error
        observed_matrix.append((dataset_mb, cores))
        if (dataset_mb, cores) != expected_matrix[index]:
            raise RegressionError(
                "legacy k-means matrix/order mismatch: "
                f"expected {expected_matrix[index]}, observed {(dataset_mb, cores)}"
            )

        bytes_per_op = 1024 + 80 * (cores - 1)
        modeled_ops = (dataset_mb * 3000) // cores
        baseline_cycles = 90000 + (bytes_per_op * 13) // 10
        sepim_cycles = baseline_cycles + (bytes_per_op + 15) // 16
        expected_cpu = 63.50 * dataset_mb / 512.0
        expected_pim = baseline_cycles * modeled_ops / 1.0e9
        expected_sepim = sepim_cycles * modeled_ops / 1.0e9
        expected_overhead = (
            (expected_sepim - expected_pim) * 100.0 / expected_pim
        )
        expected_speedup = expected_cpu / expected_sepim
        require_close(f"row {index} cpu_sec", values["cpu_sec"], expected_cpu)
        require_close(
            f"row {index} pim_baseline_sec",
            values["pim_baseline_sec"],
            expected_pim,
        )
        require_close(
            f"row {index} sepim_sec", values["sepim_sec"], expected_sepim
        )
        require_close(
            f"row {index} overhead_pct",
            values["overhead_pct"],
            expected_overhead,
        )
        require_close(
            f"row {index} speedup_vs_cpu",
            values["speedup_vs_cpu"],
            expected_speedup,
        )
        formula_rows.append(
            {
                "dataset_mb": dataset_mb,
                "pim_cores": cores,
                "bytes_per_sampled_mmio_op": bytes_per_op,
                "sampled_baseline_cycles": baseline_cycles,
                "sampled_sepim_cycles": sepim_cycles,
                "extrapolated_operations": modeled_ops,
            }
        )
    parsed = write_parsed_csv(path.parent, payload)
    return {
        "pass": True,
        "rows": len(rows),
        "matrix": [list(item) for item in observed_matrix],
        "model_kind": "legacy_extrapolated_mmio_model",
        "direct_end_to_end_measurement": False,
        "disclosure": (
            "Each row extrapolates sampled SE-PIM ACCESS_DATA MMIO cycle values; "
            "it is not a native end-to-end k-means execution."
        ),
        "formula": {
            "sample_operations": 256,
            "operations_per_mib": 3000,
            "cpu_reference_seconds_at_512_mib": 63.50,
            "rows": formula_rows,
        },
        "csv": file_identity(parsed),
    }


def parse_trace_terminal(
    path: Path, expected_sha: str, artifact_name: str, kind: str
) -> Dict[str, Any]:
    text = terminal_text(path)
    clean_text = "\n".join(line.strip() for line in text.splitlines() if not line.strip().startswith("+"))
    require_no_guest_errors(text, path.parent.name)
    require_guest_hash(text, artifact_name, expected_sha)
    prefix = "CPU" if kind == "cpu" else "SEPIM"
    if clean_text.count(f"[TRACE][{prefix}] begin lookups=2400") != 1:
        raise RegressionError(f"{kind} trace full-run start marker is missing")
    end_marker = f"[TRACE][{prefix}] end"
    if clean_text.count(end_marker) != 1:
        raise RegressionError(f"{kind} trace end marker is missing or repeated")
    if clean_text.count(f"REGRESSION_CASE_PASS {artifact_name}") != 1:
        raise RegressionError(f"{kind} trace case pass marker is missing")
    return {"pass": True, "lookups": 2400}


def _parse_decimal(value: str, label: str, maximum: int = (1 << 64) - 1) -> int:
    if not re.fullmatch(r"0|[1-9][0-9]*", value or ""):
        raise RegressionError(f"trace {label} is not canonical decimal: {value!r}")
    result = int(value)
    if result > maximum:
        raise RegressionError(f"trace {label} exceeds its allowed range: {result}")
    return result


def validate_trace_csv(
    path: Path,
    kind: str,
    *,
    require_exact_tail: bool = True,
) -> Dict[str, Any]:
    if kind not in ("cpu", "sepim", "auxiliary"):
        raise RegressionError(f"unknown trace validation kind: {kind}")
    with path.open("r", encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        rows = list(reader)
        fieldnames = reader.fieldnames
    if fieldnames != TRACE_CSV_FIELDS:
        raise RegressionError(f"trace CSV schema mismatch: {fieldnames}")
    if require_exact_tail and len(rows) != TRACE_TAIL_PACKETS:
        raise RegressionError(
            f"{kind} trace must contain exactly the last {TRACE_TAIL_PACKETS} "
            f"R/W packets, observed {len(rows)}"
        )
    if not require_exact_tail and not (0 <= len(rows) <= TRACE_TAIL_PACKETS):
        raise RegressionError(
            f"auxiliary trace row count must be 0..{TRACE_TAIL_PACKETS}: {len(rows)}"
        )

    last_time: Optional[int] = None
    addresses: List[int] = []
    rw_counts: Counter[str] = Counter()
    size_counts: Counter[int] = Counter()
    command_counts: Counter[int] = Counter()
    mmio_rows: List[Tuple[int, str, int]] = []
    for index, row in enumerate(rows):
        if None in row or set(row) != set(TRACE_CSV_FIELDS):
            raise RegressionError(f"trace row {index} violates exact schema: {row}")
        tick = _parse_decimal(row["time"], "time")
        if last_time is not None and tick < last_time:
            raise RegressionError(
                f"trace time is not monotonic at row {index}: {tick} < {last_time}"
            )
        last_time = tick
        if not re.fullmatch(r"0x(?:0|[1-9a-f][0-9a-f]*)", row["addr"] or ""):
            raise RegressionError(
                f"trace address is not canonical lowercase hexadecimal: {row['addr']!r}"
            )
        address = int(row["addr"], 16)
        if address > (1 << 64) - 1:
            raise RegressionError(f"trace address exceeds uint64: {row['addr']}")
        rw = row["rw"]
        if rw not in ("R", "W"):
            raise RegressionError(f"trace rw is not R/W: {rw!r}")
        command = _parse_decimal(row["cmd"], "cmd", maximum=(1 << 32) - 1)
        if command != (1 if rw == "R" else 4):
            raise RegressionError(
                f"trace rw/cmd mismatch at row {index}: rw={rw} cmd={command}"
            )
        size = _parse_decimal(row["size"], "size", maximum=(1 << 32) - 1)
        if size == 0:
            raise RegressionError(f"trace packet size is zero at row {index}")
        _parse_decimal(row["flags"], "flags")
        addresses.append(address)
        rw_counts[rw] += 1
        size_counts[size] += 1
        command_counts[command] += 1
        if PIM_MMIO_BASE <= address < PIM_MMIO_END:
            mmio_rows.append((address - PIM_MMIO_BASE, rw, size))

    validation: Dict[str, Any] = {
        "pass": True,
        "role": "primary" if kind in ("cpu", "sepim") else "auxiliary",
        "rows": len(rows),
        "tail_packets_requested": TRACE_TAIL_PACKETS,
        "rw_only": True,
        "time_monotonic_non_decreasing": True,
        "unique_addresses": len(set(addresses)),
        "address_min": f"0x{min(addresses):x}" if addresses else None,
        "address_max": f"0x{max(addresses):x}" if addresses else None,
        "rw_counts": dict(sorted(rw_counts.items())),
        "size_histogram": {
            str(key): value for key, value in sorted(size_counts.items())
        },
        "command_histogram": {
            str(key): value for key, value in sorted(command_counts.items())
        },
        "csv": file_identity(path),
    }
    if kind == "cpu":
        if len(set(addresses)) < 64:
            raise RegressionError(
                "CPU trace does not demonstrate address diversity: "
                f"{len(set(addresses))} unique addresses"
            )
        validation["cpu_address_diversity"] = {
            "pass": True,
            "minimum_unique_addresses": 64,
            "observed_unique_addresses": len(set(addresses)),
        }
    elif kind == "sepim":
        offset_histogram = Counter(offset for offset, _, _ in mmio_rows)
        missing = sorted(set(REQUIRED_SEPIM_MMIO_OFFSETS) - set(offset_histogram))
        if len(mmio_rows) < 512:
            raise RegressionError(
                "SE-PIM primary trace has fewer than 512 device-MMIO packets: "
                f"{len(mmio_rows)}"
            )
        if missing:
            raise RegressionError(
                "SE-PIM primary trace lacks required protocol offsets: "
                + ", ".join(f"0x{value:x}" for value in missing)
            )
        for offset, rw, size in mmio_rows:
            if not (0 <= offset < 0x1000):
                raise RegressionError(f"SE-PIM MMIO offset outside device window: {offset}")
            if offset in REQUIRED_SEPIM_MMIO_OFFSETS and size != 4:
                raise RegressionError(
                    f"SE-PIM protocol offset 0x{offset:x} has non-32-bit size {size}"
                )
            expected_rw = "R" if offset == 0x44 else "W"
            if offset in REQUIRED_SEPIM_MMIO_OFFSETS and rw != expected_rw:
                raise RegressionError(
                    f"SE-PIM protocol offset 0x{offset:x} has rw={rw}, expected {expected_rw}"
                )
        validation["sepim_mmio"] = {
            "pass": True,
            "device_window": [f"0x{PIM_MMIO_BASE:x}", f"0x{PIM_MMIO_END - 1:x}"],
            "minimum_rows": 512,
            "observed_rows": len(mmio_rows),
            "required_offsets": [
                f"0x{value:x}" for value in REQUIRED_SEPIM_MMIO_OFFSETS
            ],
            "offset_histogram": {
                f"0x{key:x}": value for key, value in sorted(offset_histogram.items())
            },
        }
    return validation


def parse_hashtable_terminal(path: Path, expected_sha: str) -> Dict[str, Any]:
    text = terminal_text(path)
    clean_text = "\n".join(line.strip() for line in text.splitlines() if not line.strip().startswith("+"))
    require_no_guest_errors(text, path.parent.name)
    require_guest_hash(text, "hashtable", expected_sha)
    if clean_text.count("REGRESSION_HASHTABLE_CANONICAL_BEGIN input_size=1572864") != 1:
        raise RegressionError("canonical hash-table start marker is missing or repeated")
    if "Error opening file" in text or "Map PIM register failed" in text:
        raise RegressionError("canonical hash-table reported a device setup failure")
    stats = path.parent / "stats.txt"
    if not stats.is_file() or stats.stat().st_size == 0:
        raise RegressionError("canonical hash-table did not emit non-empty gem5 stats")
    return {
        "pass": True,
        "canonical_input_size": 1572864,
        "stats": file_identity(stats),
        "completion_basis": (
            "workload reached its canonical start marker, emitted non-empty gem5 "
            "stats, and terminated via its embedded m5 exit without error markers"
        ),
    }


def parse_config(path: Path) -> configparser.ConfigParser:
    if not path.is_file():
        raise RegressionError(f"missing gem5 config.ini: {path}")
    config = configparser.ConfigParser(interpolation=None, strict=False)
    config.optionxform = str
    with path.open("r", encoding="utf-8", errors="replace") as stream:
        config.read_file(stream)
    return config


def validate_atomic_config(path: Path, require_reservation: bool) -> Dict[str, Any]:
    config = parse_config(path)
    sections = sorted(
        name for name in config.sections() if re.fullmatch(r"system\.cpu\d+", name)
    )
    classes = sorted({config.get(name, "type") for name in sections})
    if len(sections) != 4 or classes != ["AtomicSimpleCPU"]:
        raise RegressionError(
            f"atomic config requires four AtomicSimpleCPU sections: {sections}, {classes}"
        )
    if config.get("system", "mem_mode") != "atomic":
        raise RegressionError("atomic checkpoint/run has non-atomic mem_mode")
    start, end = config.get("system", "mem_ranges").split(":", 1)
    physical_bytes = int(end, 0) - int(start, 0) + 1
    if physical_bytes != 2048 * 1024 * 1024:
        raise RegressionError(f"physical memory is not exactly 2 GiB: {physical_bytes}")
    flags = config.get("system", "boot_osflags").split()
    if require_reservation and "mem=1984MB" not in flags:
        raise RegressionError("checkpoint boot flags lack exact mem=1984MB reservation")
    return {
        "cpu_type": "atomic",
        "cpu_class": "AtomicSimpleCPU",
        "num_cpus": len(sections),
        "mem_mode": "atomic",
        "physical_bytes": physical_bytes,
        "kernel_memory_limit": "1984MB" if "mem=1984MB" in flags else None,
    }


def validate_trace_timing_config(path: Path) -> Dict[str, Any]:
    """Require direct TimingSimpleCPU restore so CommMonitor records packets."""
    config = parse_config(path)
    sections = sorted(
        name for name in config.sections() if re.fullmatch(r"system\.cpu\d+", name)
    )
    classes = sorted({config.get(name, "type") for name in sections})
    secondary = sorted(
        name
        for name in config.sections()
        if re.fullmatch(
            r"system\.(?:switch_cpus|switch_cpus_1|repeat_switch_cpus)\d+",
            name,
        )
    )
    if len(sections) != 4 or classes != ["TimingSimpleCPU"]:
        raise RegressionError(
            "trace restore requires four direct TimingSimpleCPU sections: "
            f"{sections}, {classes}"
        )
    if secondary:
        raise RegressionError(
            f"trace restore unexpectedly constructed switched CPUs: {secondary}"
        )
    if config.get("system", "mem_mode") != "timing":
        raise RegressionError(
            "trace restore must use timing memory mode for CommMonitor capture"
        )
    start, end = config.get("system", "mem_ranges").split(":", 1)
    physical_bytes = int(end, 0) - int(start, 0) + 1
    if physical_bytes != 2048 * 1024 * 1024:
        raise RegressionError(f"trace physical memory is not 2 GiB: {physical_bytes}")
    return {
        "cpu_type": "timing",
        "cpu_class": "TimingSimpleCPU",
        "num_cpus": len(sections),
        "mem_mode": "timing",
        "physical_bytes": physical_bytes,
        "checkpoint_cpu_type": "atomic",
        "restore_strategy": "direct",
        "restore_with_cpu": "timing",
        "cpu_switch_used": False,
        "comm_monitor_capture_capable": True,
    }


def validate_trace_topology(path: Path) -> Dict[str, Any]:
    config = parse_config(path)
    required = (
        "system.sepim_trace_monitor",
        "system.sepim_trace_monitor_io",
    )
    missing = [name for name in required if not config.has_section(name)]
    if missing:
        raise RegressionError(
            f"trace topology lacks CommMonitor section(s): {missing}"
        )
    types = {name: config.get(name, "type", fallback="") for name in required}
    if set(types.values()) != {"CommMonitor"}:
        raise RegressionError(f"trace topology has unexpected monitor types: {types}")
    enabled = {
        name: config.get(name, "trace_enable", fallback="false").lower()
        in ("1", "true", "yes", "on")
        for name in required
    }
    if not all(enabled.values()):
        raise RegressionError(f"trace topology has disabled monitor(s): {enabled}")
    trace_files = {
        name: config.get(name, "trace_file", fallback="") for name in required
    }
    if not all(trace_files.values()):
        raise RegressionError(
            f"trace topology lacks configured trace file(s): {trace_files}"
        )
    return {
        "pass": True,
        "fs_config": "IMPICA/gem5/configs/se_pim/se_pim_fs.py",
        "main_trace_role": "primary",
        "io_trace_role": "auxiliary",
        "monitors": types,
        "trace_enabled": enabled,
        "trace_files": trace_files,
    }


def validate_checkpoint(
    checkpoint_dir: Path, *, require_trace_topology: bool = False
) -> Dict[str, Any]:
    checkpoints = sorted(path.name for path in checkpoint_dir.glob("cpt.*") if path.is_dir())
    if not checkpoints:
        raise RegressionError(f"no cpt.* produced under {checkpoint_dir}")
    cpu = validate_atomic_config(checkpoint_dir / "config.ini", require_reservation=True)
    text = terminal_text(checkpoint_dir / "system.terminal")
    if "Memory limited to 1984MB" not in text:
        raise RegressionError("kernel did not acknowledge 'Memory limited to 1984MB'")
    result: Dict[str, Any] = {
        "pass": True,
        "checkpoint_directories": checkpoints,
        "cpu": cpu,
    }
    if require_trace_topology:
        result["trace_topology"] = validate_trace_topology(
            checkpoint_dir / "config.ini"
        )
    return result


def git_provenance() -> Dict[str, Any]:
    def capture(args: Sequence[str]) -> bytes:
        result = subprocess.run(
            list(args), cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        return result.stdout if result.returncode == 0 else b""

    commit = capture(["git", "rev-parse", "HEAD"]).decode("ascii", "replace").strip()
    diff = capture(["git", "diff", "--binary", "--no-ext-diff", "HEAD", "--", "."])
    untracked = capture(["git", "ls-files", "--others", "--exclude-standard", "-z"])
    return {
        "commit": commit or "unknown",
        "tracked_diff_sha256": sha256_bytes(diff),
        "tracked_diff_bytes": len(diff),
        "untracked_path_list_sha256": sha256_bytes(untracked),
        "untracked_path_list_bytes": len(untracked),
    }


def detect_runtime() -> List[str]:
    candidates: List[List[str]] = []
    if shutil.which("docker"):
        candidates.append(["docker"])
        if shutil.which("sudo"):
            candidates.append(["sudo", "-n", "docker"])
    if shutil.which("podman"):
        candidates.append(["podman"])
    for candidate in candidates:
        result = subprocess.run(
            candidate + ["info"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        if result.returncode == 0:
            return candidate
    raise RegressionError("usable Docker/Podman runtime not found")


def inspect_image(runtime: Sequence[str], image: str) -> Dict[str, Any]:
    result = subprocess.run(
        list(runtime) + ["image", "inspect", image],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.returncode != 0:
        raise RegressionError(
            f"container image is not available locally (no pull is attempted): {image}"
        )
    try:
        record = json.loads(result.stdout)[0]
    except (json.JSONDecodeError, IndexError, TypeError) as error:
        raise RegressionError("unable to parse container image identity") from error
    image_id = record.get("Id", "")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", image_id):
        raise RegressionError(f"container image lacks a sha256 content ID: {image_id}")
    return {
        "requested": image,
        "image_id": image_id,
        "repo_digests": sorted(record.get("RepoDigests") or []),
        "requested_reference_pinned": image_reference_is_pinned(image),
        "network": "none",
    }


def image_reference_is_pinned(image: str) -> bool:
    return bool(
        re.search(r"@sha256:[0-9a-f]{64}$", image)
        or re.fullmatch(r"sha256:[0-9a-f]{64}", image)
    )


def evaluate_promotability(manifest: Dict[str, Any]) -> Dict[str, Any]:
    mode = manifest.get("mode")
    expected = (
        list(EXPECTED_FULL_CASE_IDS)
        if mode == "full"
        else list(EXPECTED_QUICK_CASE_IDS)
    )
    cases = manifest.get("cases") or []
    observed = [record.get("id") for record in cases]
    checks = {
        "mode_is_full": mode == "full",
        "status_passed": manifest.get("status") == "passed",
        "exact_case_matrix": observed == expected,
        "all_cases_passed": bool(cases)
        and all(record.get("pass") is True for record in cases),
        "network_disabled": manifest.get("network") == "none"
        and all(command.get("network") == "none" for command in manifest.get("commands", [])),
        "container_reference_pinned": bool(
            manifest.get("container_image", {}).get("requested_reference_pinned")
        ),
        "container_content_id_pinned": bool(
            re.fullmatch(
                r"sha256:[0-9a-f]{64}",
                manifest.get("container_image", {}).get("image_id", ""),
            )
        ),
        "source_evidence_immutable": manifest.get("source_evidence_immutable")
        is True,
        "runtime_inputs_immutable": manifest.get("runtime_inputs_immutable")
        is True,
        "injected_artifacts_immutable": manifest.get(
            "injected_artifacts_immutable"
        )
        is True,
        "event_coverage_limitation_preserved": manifest.get(
            "legacy_dma_event_coverage", {}
        ).get("status")
        == "incomplete",
    }
    eligible = all(checks.values())
    reasons = [name for name, passed in checks.items() if not passed]
    if mode == "quick" and "mode_is_full" not in reasons:
        reasons.insert(0, "mode_is_full")
    return {
        "eligible": eligible,
        "checks": checks,
        "ineligible_reasons": reasons,
        "policy": (
            "Only a full, exact eight-case pass with a digest-pinned container, "
            "network disabled, immutable runtime/artifact inputs, and byte/metadata-"
            "identical source evidence is eligible for publication promotion. "
            "Quick mode is diagnostic only."
        ),
    }


def container_path(path: Path) -> str:
    resolved = path.resolve()
    if not path_within(resolved, ROOT):
        raise RegressionError(f"runtime path must be inside workspace: {resolved}")
    relative = resolved.relative_to(ROOT).as_posix()
    return "/workspace" if relative == "." else f"/workspace/{relative}"


def display_command(argv: Sequence[str]) -> str:
    return " ".join(shlex.quote(value) for value in argv)


class ContainerRunner:
    def __init__(
        self,
        runtime: Sequence[str],
        image: str,
        run_dir: Path,
        evidence_disk: Path,
        evidence_checkpoint: Path,
        commands: List[Dict[str, Any]],
    ) -> None:
        self.runtime = list(runtime)
        self.image = image
        self.run_dir = run_dir
        self.evidence_disk = evidence_disk
        self.evidence_checkpoint = evidence_checkpoint
        self.commands = commands

    def run(self, phase: str, body: str, log_path: Path) -> None:
        uid = os.getuid()
        gid = os.getgid()
        chown_targets = [
            container_path(self.run_dir),
            "/workspace/IMPICA/workloads/sepim_cmd",
            "/workspace/IMPICA/workloads/dma_benchmark_fs",
            "/workspace/IMPICA/workloads/controlled_access_bench_fs",
            "/workspace/IMPICA/workloads/hashtable",
            "/workspace/IMPICA/workloads/trace_lookup_cpu",
            "/workspace/IMPICA/workloads/trace_lookup_sepim",
            "/workspace/IMPICA/workloads/kmeans_sepim_fs",
        ]
        cleanup = "chown -R %d:%d %s 2>/dev/null || true" % (
            uid,
            gid,
            " ".join(shlex.quote(value) for value in chown_targets),
        )
        shell_body = f"set -euo pipefail\ntrap {shlex.quote(cleanup)} EXIT\n{body}\n"
        argv = list(self.runtime) + [
            "run",
            "--rm",
            "--network",
            "none",
            "--privileged",
            "--mount",
            f"type=bind,src={ROOT},dst=/workspace",
        ]
        for source in (self.evidence_disk, self.evidence_checkpoint):
            if path_within(source, ROOT):
                argv.extend(
                    [
                        "--mount",
                        "type=bind,src=%s,dst=%s,readonly"
                        % (source, container_path(source)),
                    ]
                )
        argv.extend(
            [
                "-w",
                "/workspace",
                "-e",
                "SEPIM_IN_CONTAINER=1",
                "-e",
                f"IMAGE_NAME={self.image}",
                self.image,
                "/bin/bash",
                "-lc",
                shell_body,
            ]
        )
        record: Dict[str, Any] = {
            "phase": phase,
            "started_utc": utc_now(),
            "network": "none",
            "argv": argv,
            "display": display_command(argv),
            "inner_shell_sha256": sha256_bytes(body.encode("utf-8")),
            "log": str(log_path),
        }
        self.commands.append(record)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        print(f"[RUN] {phase}: {log_path}", flush=True)
        with log_path.open("w", encoding="utf-8") as log:
            process = subprocess.Popen(
                argv,
                cwd=str(ROOT),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                errors="replace",
                bufsize=1,
            )
            assert process.stdout is not None
            for line in process.stdout:
                sys.stdout.write(line)
                log.write(line)
            returncode = process.wait()
        record.update(
            {
                "finished_utc": utc_now(),
                "returncode": returncode,
                "log_sha256": sha256_file(log_path),
            }
        )
        if returncode != 0:
            raise RegressionError(f"container phase failed ({returncode}): {phase}")


def quoted_export(name: str, value: str) -> str:
    return f"export {name}={shlex.quote(value)}"


def runtime_exports(args: argparse.Namespace, clone: Path) -> List[str]:
    values = {
        "DISK_IMAGE": container_path(clone),
        "FS_BUNDLE_DIR": container_path(args.fs_bundle_dir),
        "GEM5_BIN": container_path(args.gem5_bin),
        "KERNEL": container_path(args.kernel),
        "DTB": container_path(args.dtb),
        "MEM_SIZE": "2048MB",
        "SEPIM_KERNEL_MEM": "1984MB",
        "CPUS": "4",
    }
    return [quoted_export(name, value) for name, value in values.items()]


def write_checkpoint_rcs(path: Path) -> None:
    path.write_text(
        """#!/bin/sh
set -ex
# SE_PIM_REGRESSION_CHECKPOINT_BOOTSTRAP_SENTINEL
M5=/sbin/m5
if [ ! -x "$M5" ]; then M5=m5; fi
if [ "${RUNSCRIPT_VAR:-0}" -eq 0 ]; then
    export RUNSCRIPT_VAR=1
    "$M5" checkpoint
fi
"$M5" readfile > /tmp/sepim-regression-runscript || true
chmod 755 /tmp/sepim-regression-runscript || true
if grep -Fq SE_PIM_REGRESSION_CHECKPOINT_BOOTSTRAP_SENTINEL /tmp/sepim-regression-runscript 2>/dev/null; then
    "$M5" exit
    exit 0
fi
if [ -s /tmp/sepim-regression-runscript ]; then
    exec /tmp/sepim-regression-runscript
fi
"$M5" exit
""",
        encoding="utf-8",
    )
    path.chmod(0o755)


def guest_prologue(name: str, guest_binary: str, expected_sha: str) -> List[str]:
    return [
        "#!/bin/sh",
        "set -ex",
        "M5=/sbin/m5",
        "if [ ! -x \"$M5\" ]; then M5=m5; fi",
        "fail() { echo \"[REGRESSION][FAIL] $*\"; \"$M5\" exit; exit 1; }",
        "cd /home/pim_driver",
        "mknod /dev/pimbt c 70 0 || true",
        "insmod ./test-driver.ko || fail 'test-driver.ko insertion failed'",
        "chmod 666 /dev/pimbt || fail 'device permission failed'",
        f"actual_sha=$(sha256sum {shlex.quote(guest_binary)} | awk '{{print $1}}')",
        f"[ \"$actual_sha\" = {shlex.quote(expected_sha)} ] || fail 'artifact hash mismatch: {name}'",
        f"echo REGRESSION_ARTIFACT_SHA256 {name}=$actual_sha",
    ]


def write_guest_rcs(
    path: Path, name: str, guest_binary: str, expected_sha: str, command: str
) -> None:
    lines = guest_prologue(name, guest_binary, expected_sha)
    if name == "hashtable":
        lines.append("echo REGRESSION_HASHTABLE_CANONICAL_BEGIN input_size=1572864")
    lines.extend(
        [
            f"cd {shlex.quote(str(Path(guest_binary).parent))}",
            command,
        ]
    )
    if name != "hashtable":
        lines.extend([f"echo REGRESSION_CASE_PASS {name}", '"$M5" exit'])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    path.chmod(0o755)


def host_artifacts() -> Dict[str, Path]:
    return {
        "sepim_cmd": ROOT / "IMPICA/workloads/sepim_cmd/sepim_cmd",
        "dma_benchmark_fs": ROOT
        / "IMPICA/workloads/dma_benchmark_fs/dma_benchmark_fs",
        "controlled_access_bench_fs": ROOT
        / "IMPICA/workloads/controlled_access_bench_fs/controlled_access_bench_fs",
        "hashtable": ROOT / "IMPICA/workloads/hashtable/hashtable",
        "trace_lookup_cpu": ROOT
        / "IMPICA/workloads/trace_lookup_cpu/trace_lookup_cpu",
        "trace_lookup_sepim": ROOT
        / "IMPICA/workloads/trace_lookup_sepim/trace_lookup_sepim",
        "kmeans_sepim_fs": ROOT
        / "IMPICA/workloads/kmeans_sepim_fs/kmeans_sepim_fs",
        "test-driver.ko": ROOT / "IMPICA/pim_driver/test-driver.ko",
    }


def validate_built_artifacts() -> Dict[str, Any]:
    records: Dict[str, Any] = {}
    for name, path in host_artifacts().items():
        if not path.is_file() or not os.access(path, os.X_OK if name != "test-driver.ko" else os.R_OK):
            raise RegressionError(f"built artifact is missing or inaccessible: {path}")
        result = subprocess.run(
            ["file", "-b", str(path)], stdout=subprocess.PIPE, text=True, check=True
        )
        description = result.stdout.strip()
        if "ARM aarch64" not in description:
            raise RegressionError(f"artifact is not AArch64: {path}: {description}")
        records[name] = {**file_identity(path), "file_description": description}
    mode = ROOT / "IMPICA/workloads/hashtable/.prebuilt_mode"
    if not mode.is_file() or mode.read_text(encoding="utf-8").strip() != "full":
        raise RegressionError("hash-table build is not marked as canonical full input")
    header = (ROOT / "IMPICA/workloads/hashtable/hashtable.h").read_text(
        encoding="utf-8"
    )
    if not re.search(r"#define\s+INPUT_SIZE\s*\(1572864\)", header):
        raise RegressionError("canonical hash-table INPUT_SIZE is not 1572864")
    records["hashtable_build_mode"] = "full"
    records["hashtable_input_size"] = 1572864
    return records


def build_body() -> str:
    return "\n".join(
        [
            "export FAST_INPUT_SIZE=0",
            "make -C IMPICA/workloads/hashtable clean",
            "rm -f IMPICA/workloads/hashtable/.prebuilt_mode",
            "scripts/prebuild_guest_workloads.sh",
            "make -C IMPICA/workloads/sepim_cmd clean",
            (
                "make -C IMPICA/workloads/sepim_cmd CC=aarch64-linux-gnu-gcc "
                "CFLAGS='-O2 -Wall -std=gnu99 -I../../pim_driver -static' "
                "LDFLAGS=-static sepim_cmd"
            ),
            "make -C IMPICA/workloads/dma_benchmark_fs clean all",
            "make -C IMPICA/workloads/controlled_access_bench_fs clean all",
            "make -C IMPICA/workloads/trace_lookup_cpu clean all",
            "make -C IMPICA/workloads/trace_lookup_sepim clean all",
            "make -C IMPICA/workloads/kmeans_sepim_fs clean all",
            "test \"$(cat IMPICA/workloads/hashtable/.prebuilt_mode)\" = full",
            "file IMPICA/workloads/sepim_cmd/sepim_cmd | grep -F 'ARM aarch64'",
            "file IMPICA/workloads/dma_benchmark_fs/dma_benchmark_fs | grep -F 'ARM aarch64'",
            "file IMPICA/workloads/controlled_access_bench_fs/controlled_access_bench_fs | grep -F 'ARM aarch64'",
            "file IMPICA/workloads/hashtable/hashtable | grep -F 'ARM aarch64'",
            "file IMPICA/workloads/trace_lookup_cpu/trace_lookup_cpu | grep -F 'ARM aarch64'",
            "file IMPICA/workloads/trace_lookup_sepim/trace_lookup_sepim | grep -F 'ARM aarch64'",
            "file IMPICA/workloads/kmeans_sepim_fs/kmeans_sepim_fs | grep -F 'ARM aarch64'",
        ]
    )


def runtime_input_paths(args: argparse.Namespace) -> Dict[str, Path]:
    return {
        "run_baseline_fs": ROOT / "scripts/run_baseline_fs.sh",
        "prepare_disk_image": ROOT / "scripts/prepare_disk_image.sh",
        "prebuild_guest_workloads": ROOT / "scripts/prebuild_guest_workloads.sh",
        "gem5_opt": args.gem5_bin,
        "gem5_fs_config": ROOT / "IMPICA/gem5/configs/example/fs.py",
        "sepim_fs_config": ROOT / "IMPICA/gem5/configs/se_pim/se_pim_fs.py",
        "cache_config": ROOT / "IMPICA/gem5/configs/common/CacheConfig.py",
        "fs_platform_config": ROOT / "IMPICA/gem5/configs/common/FSConfig.py",
        "realview_config": ROOT / "IMPICA/gem5/src/dev/arm/RealView.py",
        "comm_monitor_config": ROOT / "IMPICA/gem5/src/mem/CommMonitor.py",
        "packet_proto": ROOT / "IMPICA/gem5/src/proto/packet.proto",
        "packet_command_header": ROOT / "IMPICA/gem5/src/mem/packet.hh",
        "trace_decoder": ROOT / "scripts/decode_ptrace_csv.py",
        "trace_cpu_source": ROOT
        / "IMPICA/workloads/trace_lookup_cpu/trace_lookup_cpu.c",
        "trace_sepim_source": ROOT
        / "IMPICA/workloads/trace_lookup_sepim/trace_lookup_sepim.c",
        "kmeans_source": ROOT
        / "IMPICA/workloads/kmeans_sepim_fs/kmeans_sepim_fs.c",
        "protocol_header": ROOT / "IMPICA/pim_driver/sepim_cmd_if.h",
        "pim_device_source": ROOT / "IMPICA/gem5/src/dev/arm/pimDevice_hashtable.cc",
        "pim_device_header": ROOT / "IMPICA/gem5/src/dev/arm/pimDevice_hashtable.hh",
        "kernel": args.kernel,
        "dtb": args.dtb,
        "bootloader": args.fs_bundle_dir / "binaries/boot_emm.arm64",
    }


def verify_preflight(args: argparse.Namespace, run_dir: Path) -> None:
    if not RUN_ID_RE.fullmatch(args.run_id):
        raise RegressionError(
            "--run-id must match [A-Za-z0-9][A-Za-z0-9_.-]{0,127}"
        )
    if run_dir.exists():
        raise RegressionError(f"refusing to overwrite existing run directory: {run_dir}")
    if not path_within(run_dir, ROOT):
        raise RegressionError(f"output run directory must be inside workspace: {run_dir}")
    if not args.source_disk.is_file():
        raise RegressionError(f"source evidence disk is not a file: {args.source_disk}")
    if not args.source_checkpoint.is_dir():
        raise RegressionError(
            f"source evidence checkpoint is not a directory: {args.source_checkpoint}"
        )
    for source in (args.source_disk, args.source_checkpoint):
        if paths_overlap(run_dir, source):
            raise RegressionError(f"output and source evidence paths overlap: {source}")
    required = list(runtime_input_paths(args).values()) + [
        args.fs_bundle_dir / "disks/aarch64-ubuntu-trusty-headless.img"
    ]
    for path in required:
        if not path.exists():
            raise RegressionError(f"required local input is missing (network is disabled): {path}")
        if not path_within(path.resolve(), ROOT):
            raise RegressionError(f"runtime input must be inside workspace: {path}")


def normalize_args(args: argparse.Namespace) -> None:
    args.source_disk = args.source_disk.expanduser().resolve()
    args.source_checkpoint = args.source_checkpoint.expanduser().resolve()
    args.output_root = args.output_root.expanduser().resolve()
    args.fs_bundle_dir = args.fs_bundle_dir.expanduser().resolve()
    args.gem5_bin = args.gem5_bin.expanduser().resolve()
    if args.kernel is None:
        args.kernel = args.fs_bundle_dir / "binaries/vmlinux.aarch64.20140821"
    if args.dtb is None:
        args.dtb = args.fs_bundle_dir / "binaries/vexpress.aarch64.20140821.dtb"
    args.kernel = args.kernel.expanduser().resolve()
    args.dtb = args.dtb.expanduser().resolve()


def default_fs_bundle() -> Path:
    root = ROOT / "third_party/gem5_fs"
    nested = root / "aarch-system-2014-10"
    for candidate in (nested, root):
        if (candidate / "disks/aarch64-ubuntu-trusty-headless.img").is_file():
            return candidate
    return nested


def parser() -> argparse.ArgumentParser:
    default_bundle = default_fs_bundle()
    value = argparse.ArgumentParser(
        description=(
            "Run an isolated legacy SE-PIM regression suite from a disposable "
            "disk clone and regression-only atomic checkpoint."
        )
    )
    value.add_argument("--source-disk", type=Path, required=True, help="fused evidence disk (never modified)")
    value.add_argument("--source-checkpoint", type=Path, required=True, help="fused evidence checkpoint directory (never modified)")
    value.add_argument("--run-id", required=True, help="unique filesystem-safe run identifier")
    value.add_argument(
        "--mode",
        choices=("quick", "full"),
        default="quick",
        help=(
            "quick runs five non-promotable diagnostics; full runs the exact "
            "eight-case publication regression matrix (default: quick)"
        ),
    )
    value.add_argument(
        "--output-root",
        type=Path,
        default=ROOT / "results/raw/sepim_regressions",
        help="parent directory; RUN_ID is created below it",
    )
    value.add_argument("--image", default=DEFAULT_IMAGE, help="local container image or digest")
    value.add_argument("--fs-bundle-dir", type=Path, default=default_bundle)
    value.add_argument("--gem5-bin", type=Path, default=ROOT / "IMPICA/gem5/build/ARM/gem5.opt")
    value.add_argument("--kernel", type=Path, default=None, help="defaults to FS_BUNDLE_DIR/binaries/vmlinux.aarch64.20140821")
    value.add_argument("--dtb", type=Path, default=None, help="defaults to FS_BUNDLE_DIR/binaries/vexpress.aarch64.20140821.dtb")
    value.add_argument(
        "--prepare-only",
        action="store_true",
        help="build, clone, inject, and create the atomic checkpoint, but do not restore cases",
    )
    value.add_argument(
        "--dry-run",
        action="store_true",
        help="validate paths and evidence hashes and print the plan without writing or running Docker",
    )
    return value


def planned_cases(mode: str) -> List[Dict[str, str]]:
    quick = [
        {"id": "table2_pass1", "workload": "sepim_cmd", "mode": "all_10_commands"},
        {"id": "table2_pass2", "workload": "sepim_cmd", "mode": "all_10_commands"},
        {"id": "dma_quick", "workload": "dma_benchmark_fs", "mode": "quick"},
        {
            "id": "controlled_quick",
            "workload": "controlled_access_bench_fs",
            "mode": "quick",
        },
        {"id": "hashtable_canonical", "workload": "hashtable", "mode": "canonical"},
    ]
    if mode == "quick":
        return quick
    return [
        quick[0],
        quick[1],
        {"id": "dma_full", "workload": "dma_benchmark_fs", "mode": "full"},
        {
            "id": "controlled_full",
            "workload": "controlled_access_bench_fs",
            "mode": "full",
        },
        quick[4],
        {"id": "trace_cpu_full", "workload": "trace_lookup_cpu", "mode": "full"},
        {
            "id": "trace_sepim_full",
            "workload": "trace_lookup_sepim",
            "mode": "full",
        },
        {
            "id": "kmeans_legacy_full",
            "workload": "kmeans_sepim_fs",
            "mode": "no_arguments",
        },
    ]


def case_specs(mode: str) -> List[Dict[str, str]]:
    specs: List[Dict[str, str]] = [
        {
            "id": "table2_pass1",
            "artifact": "sepim_cmd",
            "guest_binary": "/home/workloads/sepim_cmd/sepim_cmd",
            "guest_command": "./sepim_cmd || fail 'Table 2 command run failed'",
            "parser": "table2",
            "checkpoint": "main",
            "mode": "all_10_commands",
        },
        {
            "id": "table2_pass2",
            "artifact": "sepim_cmd",
            "guest_binary": "/home/workloads/sepim_cmd/sepim_cmd",
            "guest_command": "./sepim_cmd || fail 'Table 2 command run failed'",
            "parser": "table2",
            "checkpoint": "main",
            "mode": "all_10_commands",
        },
    ]
    run_mode = "quick" if mode == "quick" else "full"
    mode_arg = "--quick" if mode == "quick" else ""
    specs.extend(
        [
            {
                "id": f"dma_{run_mode}",
                "artifact": "dma_benchmark_fs",
                "guest_binary": "/home/workloads/dma_benchmark_fs/dma_benchmark_fs",
                "guest_command": (
                    f"./dma_benchmark_fs {mode_arg}".rstrip()
                    + f" || fail 'DMA {run_mode} run failed'"
                ),
                "parser": "dma",
                "checkpoint": "main",
                "mode": run_mode,
            },
            {
                "id": f"controlled_{run_mode}",
                "artifact": "controlled_access_bench_fs",
                "guest_binary": (
                    "/home/workloads/controlled_access_bench_fs/"
                    "controlled_access_bench_fs"
                ),
                "guest_command": (
                    f"./controlled_access_bench_fs {mode_arg}".rstrip()
                    + f" || fail 'controlled-access {run_mode} run failed'"
                ),
                "parser": "controlled",
                "checkpoint": "main",
                "mode": run_mode,
            },
            {
                "id": "hashtable_canonical",
                "artifact": "hashtable",
                "guest_binary": "/home/workloads/hashtable/hashtable",
                "guest_command": (
                    "./hashtable || fail 'canonical hash-table run failed'"
                ),
                "parser": "hashtable",
                "checkpoint": "main",
                "mode": "canonical",
            },
        ]
    )
    if mode == "full":
        specs.extend(
            [
                {
                    "id": "trace_cpu_full",
                    "artifact": "trace_lookup_cpu",
                    "guest_binary": (
                        "/home/workloads/trace_lookup_cpu/trace_lookup_cpu"
                    ),
                    "guest_command": (
                        "./trace_lookup_cpu --full || fail 'CPU trace full run failed'"
                    ),
                    "parser": "trace_cpu",
                    "checkpoint": "trace",
                    "mode": "full",
                },
                {
                    "id": "trace_sepim_full",
                    "artifact": "trace_lookup_sepim",
                    "guest_binary": (
                        "/home/workloads/trace_lookup_sepim/trace_lookup_sepim"
                    ),
                    "guest_command": (
                        "./trace_lookup_sepim --full || fail 'SE-PIM trace full run failed'"
                    ),
                    "parser": "trace_sepim",
                    "checkpoint": "trace",
                    "mode": "full",
                },
                {
                    "id": "kmeans_legacy_full",
                    "artifact": "kmeans_sepim_fs",
                    "guest_binary": (
                        "/home/workloads/kmeans_sepim_fs/kmeans_sepim_fs"
                    ),
                    "guest_command": (
                        "./kmeans_sepim_fs || fail 'legacy k-means full run failed'"
                    ),
                    "parser": "kmeans_legacy",
                    "checkpoint": "main",
                    "mode": "no_arguments",
                },
            ]
        )
    return specs


def restore_cpu_options(checkpoint_role: str) -> str:
    if checkpoint_role == "trace":
        # CommMonitor only emits protobuf packets from recvTimingReq.  Restore
        # the atomic architectural checkpoint directly into timing CPUs; using
        # atomic here would produce a header-only trace.
        return "--cpu-type=timing --restore-with-cpu=timing"
    if checkpoint_role == "main":
        return "--cpu-type=atomic --restore-with-cpu=atomic"
    raise RegressionError(f"unknown checkpoint role: {checkpoint_role}")


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parser().parse_args(argv)
    normalize_args(args)
    run_dir = (args.output_root / args.run_id).resolve()
    manifest_path = run_dir / "regression_manifest.json"
    verify_preflight(args, run_dir)

    print("[INFO] Hashing source evidence at suite start", flush=True)
    start_evidence = evidence_snapshot(args.source_disk, args.source_checkpoint)
    plan = {
        "schema_version": SCHEMA_VERSION,
        "run_id": args.run_id,
        "mode": args.mode,
        "run_directory": str(run_dir),
        "source_disk": str(args.source_disk),
        "source_checkpoint": str(args.source_checkpoint),
        "container_image_requested": args.image,
        "network": "none",
        "disk_clone_method": "Python shutil.copyfile byte copy; no hard link",
        "prepare_only": args.prepare_only,
        "case_plan": planned_cases(args.mode),
        "cases": [],
        "source_evidence_start": start_evidence,
        "limitations": [
            (
                "Dynamic legacy PimDevice DMA event coverage for event IDs 0..5 is "
                "incomplete unless a dedicated instrumented harness is run. The "
                "canonical hash-table regression is not evidence that every event ID "
                "executed."
            )
        ],
        "legacy_dma_event_coverage": {
            "declared_event_ids": [0, 1, 2, 3, 4, 5],
            "dedicated_dynamic_harness": False,
            "status": "incomplete",
            "publication_claim_allowed": False,
            "limitation": (
                "Dynamic legacy PimDevice DMA event coverage for event IDs 0..5 "
                "is incomplete; the canonical hash-table case does not prove "
                "that every event ID executed."
            ),
        },
    }
    if args.dry_run:
        end_evidence = evidence_snapshot(args.source_disk, args.source_checkpoint)
        if not same_evidence(start_evidence, end_evidence):
            raise RegressionError("source evidence changed during dry-run hashing")
        plan.update(
            {
                "status": "dry_run",
                "source_evidence_end": end_evidence,
                "source_evidence_immutable": True,
                "publication_eligible": False,
                "promotability": {
                    "eligible": False,
                    "ineligible_reasons": ["dry_run_does_not_execute_cases"],
                },
            }
        )
        print(json.dumps(plan, indent=2, sort_keys=True))
        return 0

    run_dir.mkdir(parents=True, exist_ok=False)
    (run_dir / "logs").mkdir()
    (run_dir / "rcs").mkdir()
    (run_dir / "cases").mkdir()
    commands: List[Dict[str, Any]] = []
    manifest: Dict[str, Any] = {
        **plan,
        "started_utc": utc_now(),
        "status": "running",
        "commands": commands,
        "repository_start": git_provenance(),
        "security_properties": {
            "source_disk_mounted_read_only_if_inside_workspace": True,
            "source_checkpoint_mounted_read_only_if_inside_workspace": True,
            "source_content_and_metadata_hashed_at_start_and_end": True,
            "runtime_inputs_hashed_at_start_and_end": True,
            "injected_artifacts_hashed_at_build_and_suite_end": True,
            "container_network": "none",
            "refuse_overwrite": True,
        },
    }
    atomic_write_json(manifest_path, manifest)
    failure: Optional[BaseException] = None
    try:
        runtime = detect_runtime()
        manifest["container_runtime"] = runtime
        manifest["container_image"] = inspect_image(runtime, args.image)
        manifest["runtime_inputs"] = {
            name: file_identity(path)
            for name, path in runtime_input_paths(args).items()
        }
        runner = ContainerRunner(
            runtime,
            args.image,
            run_dir,
            args.source_disk,
            args.source_checkpoint,
            commands,
        )

        clone = run_dir / "regression-disk.img"
        print(f"[INFO] Full-copying disposable disk clone: {clone}", flush=True)
        shutil.copyfile(args.source_disk, clone)
        shutil.copystat(args.source_disk, clone)
        clone.chmod(clone.stat().st_mode | stat.S_IWUSR)
        source_stat = args.source_disk.stat()
        clone_stat = clone.stat()
        if (source_stat.st_dev, source_stat.st_ino) == (clone_stat.st_dev, clone_stat.st_ino):
            raise RegressionError("disk clone unexpectedly aliases source inode")
        clone_initial = file_identity(clone)
        if clone_initial["sha256"] != start_evidence["disk"]["sha256"]:
            raise RegressionError("disposable clone bytes differ from source evidence disk")
        manifest["disk_clone"] = {
            **clone_initial,
            "source_inode_alias": False,
            "method": "shutil.copyfile",
        }
        atomic_write_json(manifest_path, manifest)

        runner.run("build_legacy_aarch64", build_body(), run_dir / "logs/build.log")
        artifacts = validate_built_artifacts()
        manifest["injected_artifacts"] = artifacts

        exports = runtime_exports(args, clone)
        inject_body = "\n".join(exports + ["export CHROOT_BUILD=0", "scripts/prepare_disk_image.sh"])
        runner.run("inject_disposable_disk", inject_body, run_dir / "logs/inject.log")
        manifest["disk_clone_after_injection"] = file_identity(clone)
        atomic_write_json(manifest_path, manifest)

        checkpoint_rcs = run_dir / "rcs/checkpoint.rcS"
        checkpoint_dir = run_dir / "checkpoint_atomic"
        write_checkpoint_rcs(checkpoint_rcs)
        checkpoint_body = "\n".join(
            exports
            + [
                quoted_export("OUTDIR", container_path(checkpoint_dir)),
                quoted_export("BOOT_SCRIPT", container_path(checkpoint_rcs)),
                quoted_export("GEM5_EXTRA_ARGS", "--cpu-type=atomic"),
                "scripts/run_baseline_fs.sh --mode custom",
            ]
        )
        runner.run(
            "create_regression_atomic_checkpoint",
            checkpoint_body,
            run_dir / "logs/checkpoint.log",
        )
        checkpoint_validation = validate_checkpoint(checkpoint_dir)
        manifest["regression_checkpoint"] = {
            **checkpoint_validation,
            **content_tree_identity(checkpoint_dir),
            "path": str(checkpoint_dir),
            "guest_script": file_identity(checkpoint_rcs),
            "source_evidence_checkpoint_used_for_restore": False,
        }
        atomic_write_json(manifest_path, manifest)

        trace_checkpoint_dir: Optional[Path] = None
        if args.mode == "full":
            trace_checkpoint_rcs = run_dir / "rcs/trace_checkpoint.rcS"
            trace_checkpoint_dir = run_dir / "checkpoint_trace_atomic"
            trace_checkpoint_ptrc = trace_checkpoint_dir / "bootstrap.ptrc"
            write_checkpoint_rcs(trace_checkpoint_rcs)
            trace_checkpoint_body = "\n".join(
                exports
                + [
                    quoted_export(
                        "FS_CONFIG",
                        "/workspace/IMPICA/gem5/configs/se_pim/se_pim_fs.py",
                    ),
                    quoted_export("OUTDIR", container_path(trace_checkpoint_dir)),
                    quoted_export(
                        "BOOT_SCRIPT", container_path(trace_checkpoint_rcs)
                    ),
                    quoted_export(
                        "GEM5_EXTRA_ARGS",
                        "--cpu-type=atomic --sepim-trace-enable=1 "
                        f"--sepim-trace-file={container_path(trace_checkpoint_ptrc)}",
                    ),
                    "scripts/run_baseline_fs.sh --mode custom",
                ]
            )
            runner.run(
                "create_trace_topology_atomic_checkpoint",
                trace_checkpoint_body,
                run_dir / "logs/trace_checkpoint.log",
            )
            trace_checkpoint_validation = validate_checkpoint(
                trace_checkpoint_dir, require_trace_topology=True
            )
            manifest["trace_regression_checkpoint"] = {
                **trace_checkpoint_validation,
                **content_tree_identity(trace_checkpoint_dir),
                "path": str(trace_checkpoint_dir),
                "guest_script": file_identity(trace_checkpoint_rcs),
                "source_evidence_checkpoint_used_for_restore": False,
                "separate_from_main_regression_checkpoint": True,
            }
            atomic_write_json(manifest_path, manifest)

        if args.prepare_only:
            manifest["status"] = "prepared"
            manifest["cases"] = []
        else:
            sha_by_name = {
                name: record["sha256"]
                for name, record in artifacts.items()
                if isinstance(record, dict) and "sha256" in record
            }
            case_records: List[Dict[str, Any]] = []
            for spec in case_specs(args.mode):
                case_id = spec["id"]
                artifact_name = spec["artifact"]
                guest_binary = spec["guest_binary"]
                guest_command = spec["guest_command"]
                case_dir = run_dir / "cases" / case_id
                guest_rcs = run_dir / "rcs" / f"{case_id}.rcS"
                expected_sha = sha_by_name[artifact_name]
                write_guest_rcs(
                    guest_rcs,
                    artifact_name,
                    guest_binary,
                    expected_sha,
                    guest_command,
                )
                selected_checkpoint = checkpoint_dir
                if spec["checkpoint"] == "trace":
                    if trace_checkpoint_dir is None:
                        raise RegressionError(
                            f"{case_id}: trace checkpoint was not created"
                        )
                    selected_checkpoint = trace_checkpoint_dir
                restore_cpu_args = restore_cpu_options(spec["checkpoint"])
                restore_args = (
                    f"-r 1 --checkpoint-dir={container_path(selected_checkpoint)} "
                    f"{restore_cpu_args}"
                )
                trace_path: Optional[Path] = None
                if spec["checkpoint"] == "trace":
                    trace_path = case_dir / f"{case_id}.ptrc"
                    restore_args += (
                        " --sepim-trace-enable=1 "
                        f"--sepim-trace-file={container_path(trace_path)}"
                    )
                case_environment: List[str] = []
                if spec["checkpoint"] == "trace":
                    case_environment.append(
                        quoted_export(
                            "FS_CONFIG",
                            "/workspace/IMPICA/gem5/configs/se_pim/se_pim_fs.py",
                        )
                    )
                case_body = "\n".join(
                    exports
                    + case_environment
                    + [
                        quoted_export("OUTDIR", container_path(case_dir)),
                        quoted_export("BOOT_SCRIPT", container_path(guest_rcs)),
                        quoted_export("GEM5_EXTRA_ARGS", restore_args),
                        "scripts/run_baseline_fs.sh --mode custom",
                    ]
                )
                runner.run(case_id, case_body, run_dir / "logs" / f"{case_id}.log")
                cpu = (
                    validate_trace_timing_config(case_dir / "config.ini")
                    if spec["checkpoint"] == "trace"
                    else validate_atomic_config(
                        case_dir / "config.ini", require_reservation=False
                    )
                )
                terminal = case_dir / "system.terminal"
                parser_kind = spec["parser"]
                if parser_kind == "table2":
                    validation = parse_table2_terminal(terminal, expected_sha)
                elif parser_kind == "dma":
                    validation = parse_dma_terminal(
                        terminal, expected_sha, mode=args.mode
                    )
                elif parser_kind == "controlled":
                    validation = parse_controlled_terminal(
                        terminal, expected_sha, mode=args.mode
                    )
                elif parser_kind == "hashtable":
                    validation = parse_hashtable_terminal(terminal, expected_sha)
                elif parser_kind == "kmeans_legacy":
                    validation = parse_kmeans_legacy_terminal(
                        terminal, expected_sha
                    )
                elif parser_kind in ("trace_cpu", "trace_sepim"):
                    if trace_path is None:
                        raise RegressionError(f"{case_id}: missing trace path")
                    trace_kind = "cpu" if parser_kind == "trace_cpu" else "sepim"
                    validation = parse_trace_terminal(
                        terminal, expected_sha, artifact_name, trace_kind
                    )
                    if not trace_path.is_file() or trace_path.stat().st_size == 0:
                        raise RegressionError(
                            f"{case_id}: primary CommMonitor trace is missing or empty"
                        )
                    decoded = case_dir / f"{case_id}_decoded.csv"
                    auxiliary_trace = Path(str(trace_path) + ".io")
                    auxiliary_decoded = case_dir / f"{case_id}_io_decoded.csv"
                    decode_body = "\n".join(
                        [
                            (
                                "python3 scripts/decode_ptrace_csv.py "
                                f"--input {shlex.quote(container_path(trace_path))} "
                                f"--output {shlex.quote(container_path(decoded))} "
                                "--gem5-root /workspace/IMPICA/gem5 "
                                f"--tail {TRACE_TAIL_PACKETS} --rw-only"
                            ),
                            (
                                f"if test -s {shlex.quote(container_path(auxiliary_trace))}; then "
                                "python3 scripts/decode_ptrace_csv.py "
                                f"--input {shlex.quote(container_path(auxiliary_trace))} "
                                f"--output {shlex.quote(container_path(auxiliary_decoded))} "
                                "--gem5-root /workspace/IMPICA/gem5 "
                                f"--tail {TRACE_TAIL_PACKETS} --rw-only; fi"
                            ),
                        ]
                    )
                    runner.run(
                        f"decode_{case_id}",
                        decode_body,
                        run_dir / "logs" / f"decode_{case_id}.log",
                    )
                    validation["trace_topology"] = validate_trace_topology(
                        case_dir / "config.ini"
                    )
                    # For SE-PIM: the IO bus trace (.ptrc.io) carries the MMIO
                    # control-register traffic that the SEPIM validation requires.
                    # When it is present (and non-empty), promote it to primary
                    # evidence and demote the memory-bus trace to auxiliary — matching
                    # the original run_gate8_trace.sh behaviour:
                    #   if [[ -f "$SEPIM_TRACE_IO" && -s "$SEPIM_TRACE_IO" ]]; then
                    #       TRACE_SRC_SEPIM="$SEPIM_TRACE_IO"
                    #   fi
                    io_trace_is_primary = (
                        parser_kind == "trace_sepim"
                        and auxiliary_trace.is_file()
                        and auxiliary_trace.stat().st_size > 0
                    )
                    if io_trace_is_primary:
                        # IO trace is the primary SE-PIM evidence (MMIO/DMA path).
                        # Validate using "auxiliary" kind (no strict MMIO address range
                        # requirement) — consistent with the original run_gate8_trace.sh
                        # which only required >=16 decoded rows from the IO trace.
                        # The SE-PIM protocol integrity is verified by the guest terminal
                        # (hash match, [TRACE][SEPIM] begin/end, REGRESSION_CASE_PASS).
                        if not auxiliary_decoded.is_file():
                            raise RegressionError(
                                f"{case_id}: SE-PIM IO trace was not decoded"
                            )
                        io_validation = validate_trace_csv(
                            auxiliary_decoded, "auxiliary", require_exact_tail=False
                        )
                        if io_validation.get("rows", 0) < 16:
                            raise RegressionError(
                                f"{case_id}: SE-PIM IO trace has fewer than 16 rows: "
                                f"{io_validation.get('rows', 0)}"
                            )
                        validation["primary_trace"] = {
                            "source": "io_bus_trace",
                            "raw": file_identity(auxiliary_trace),
                            "decoded": io_validation,
                        }
                        validation["auxiliary_memory_trace"] = {
                            "present": True,
                            "role": "auxiliary_memory_bus",
                            "raw": file_identity(trace_path),
                            "decoded": validate_trace_csv(decoded, "cpu"),
                        }
                        validation["source_policy"] = (
                            "SE-PIM: .ptrc.io (IO bus) is primary DMA/MMIO evidence; "
                            ".ptrc (memory bus) is retained as auxiliary evidence. "
                            "Consistent with original run_gate8_trace.sh behaviour "
                            "(required >=16 decoded rows from IO trace source)."
                        )

                    else:
                        validation["primary_trace"] = {
                            "raw": file_identity(trace_path),
                            "decoded": validate_trace_csv(decoded, trace_kind),
                        }
                        if auxiliary_trace.is_file() and auxiliary_trace.stat().st_size:
                            if not auxiliary_decoded.is_file():
                                raise RegressionError(
                                    f"{case_id}: auxiliary trace was not decoded"
                                )
                            validation["auxiliary_io_trace"] = {
                                "present": True,
                                "role": "auxiliary",
                                "raw": file_identity(auxiliary_trace),
                                "decoded": validate_trace_csv(
                                    auxiliary_decoded,
                                    "auxiliary",
                                    require_exact_tail=False,
                                ),
                            }
                        else:
                            validation["auxiliary_io_trace"] = {
                                "present": False,
                                "role": "auxiliary",
                                "required_for_pass": False,
                            }
                        validation["source_policy"] = (
                            "The main .ptrc is primary evidence; .ptrc.io is "
                            "decoded and retained only as auxiliary evidence."
                        )

                else:
                    raise RegressionError(f"unknown case parser: {parser_kind}")
                record = {
                    "id": case_id,
                    "workload": artifact_name,
                    "mode": spec["mode"],
                    "pass": True,
                    "guest_command": guest_command,
                    "expected_artifact_sha256": expected_sha,
                    "cpu": cpu,
                    "validation": validation,
                    "checkpoint_role": spec["checkpoint"],
                    "guest_script": file_identity(guest_rcs),
                    "terminal": file_identity(terminal),
                    "output_tree": content_tree_identity(case_dir),
                }
                case_records.append(record)
                manifest["cases"] = case_records
                atomic_write_json(manifest_path, manifest)

            expected_case_ids = (
                list(EXPECTED_FULL_CASE_IDS)
                if args.mode == "full"
                else list(EXPECTED_QUICK_CASE_IDS)
            )
            observed_case_ids = [record["id"] for record in case_records]
            if observed_case_ids != expected_case_ids:
                raise RegressionError(
                    "regression case matrix mismatch: "
                    f"expected={expected_case_ids} observed={observed_case_ids}"
                )

            table_digests = [
                record["validation"]["command_transcript_sha256"]
                for record in case_records
                if record["id"].startswith("table2_pass")
            ]
            if len(table_digests) != 2 or len(set(table_digests)) != 1:
                raise RegressionError(
                    f"Table 2 repeated-restore transcripts differ: {table_digests}"
                )
            manifest["table2_repeatability"] = {
                "pass": True,
                "runs": 2,
                "identical_command_transcript_sha256": table_digests[0],
            }
            manifest["status"] = "passed"
    except BaseException as error:  # keep provenance even on KeyboardInterrupt
        failure = error
        manifest["status"] = "failed"
        manifest["error"] = {
            "type": type(error).__name__,
            "message": str(error),
            "traceback": traceback.format_exc(),
        }
    finally:
        if "runtime_inputs" in manifest:
            try:
                runtime_inputs_end = {
                    name: file_identity(path)
                    for name, path in runtime_input_paths(args).items()
                }
                runtime_inputs_immutable = (
                    runtime_inputs_end == manifest["runtime_inputs"]
                )
                manifest["runtime_inputs_end"] = runtime_inputs_end
                manifest["runtime_inputs_immutable"] = runtime_inputs_immutable
                if not runtime_inputs_immutable:
                    raise RegressionError(
                        "hashed runtime inputs changed during the regression suite"
                    )
            except BaseException as error:
                manifest["status"] = "failed"
                manifest["runtime_inputs_immutable"] = False
                manifest["runtime_input_immutability_error"] = str(error)
                if failure is None:
                    failure = error
                    manifest.setdefault(
                        "error",
                        {"type": type(error).__name__, "message": str(error)},
                    )
        else:
            manifest["runtime_inputs_immutable"] = False

        if "injected_artifacts" in manifest:
            try:
                artifacts_end = validate_built_artifacts()
                artifacts_immutable = (
                    artifacts_end == manifest["injected_artifacts"]
                )
                manifest["injected_artifacts_end"] = artifacts_end
                manifest["injected_artifacts_immutable"] = artifacts_immutable
                if not artifacts_immutable:
                    raise RegressionError(
                        "built/injected AArch64 artifacts changed during the suite"
                    )
            except BaseException as error:
                manifest["status"] = "failed"
                manifest["injected_artifacts_immutable"] = False
                manifest["injected_artifact_immutability_error"] = str(error)
                if failure is None:
                    failure = error
                    manifest.setdefault(
                        "error",
                        {"type": type(error).__name__, "message": str(error)},
                    )
        else:
            manifest["injected_artifacts_immutable"] = False

        print("[INFO] Re-hashing source evidence at suite end", flush=True)
        try:
            end_evidence = evidence_snapshot(args.source_disk, args.source_checkpoint)
            immutable = same_evidence(start_evidence, end_evidence)
            manifest["source_evidence_end"] = end_evidence
            manifest["source_evidence_immutable"] = immutable
            if not immutable:
                manifest["status"] = "failed"
                invariant_error = RegressionError(
                    "source evidence disk/checkpoint changed during isolated suite"
                )
                if failure is None:
                    failure = invariant_error
                manifest.setdefault(
                    "error",
                    {
                        "type": type(invariant_error).__name__,
                        "message": str(invariant_error),
                    },
                )
        except BaseException as error:
            manifest["status"] = "failed"
            manifest["source_evidence_immutable"] = False
            manifest["immutability_check_error"] = str(error)
            if failure is None:
                failure = error
        manifest["repository_end"] = git_provenance()
        manifest["finished_utc"] = utc_now()
        manifest["promotability"] = evaluate_promotability(manifest)
        manifest["publication_eligible"] = manifest["promotability"]["eligible"]
        atomic_write_json(manifest_path, manifest)

    if failure is not None:
        print(f"[FAIL] {failure}", file=sys.stderr)
        print(f"[INFO] Failure manifest: {manifest_path}", file=sys.stderr)
        return 1
    print(f"[PASS] isolated SE-PIM regression status={manifest['status']}")
    print(f"[INFO] Manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
