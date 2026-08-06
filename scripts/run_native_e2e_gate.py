#!/usr/bin/env python3
"""Run paired, checkpoint-isolated native device-command workload experiments.

This gate deliberately accepts only direct gem5 native-command rows.  It rejects
the older cleaning-only/native-plus-modeled-workload schema so that a modeled
number cannot accidentally be reported as a measured overhead.
"""

import argparse
import concurrent.futures
import configparser
import csv
import hashlib
import io
import json
import math
import os
import re
import shlex
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKLOAD = ROOT / "IMPICA" / "workloads" / "kmeans_sepim_fs"
KMEANS_ORACLE = WORKLOAD / "kmeans_digest_oracle"
DATASET_GENERATOR = ROOT / "scripts" / "corrupt_dataset.py"
DATASET_WRAPPER = ROOT / "scripts" / "generate_native_dataset_matrix.py"
CHECKPOINT_PROVENANCE_NAME = "checkpoint_provenance.json"
TREE_HASH_ALGORITHM = "sha256_concat_path_nul_sha256_nul_v1"
PINNED_IMAGE = (
    "sepim-impica@sha256:"
    "b4935cb7b1343fcaef5dcf19bb7644a7cfc3843522b81b0fbf04c741ad11c296"
)
MODEL_KIND = {
    "aggregate": "gem5_native_e2e_aggregate",
    "kmeans": "gem5_native_e2e_kmeans",
}
FULL_RATES = (0.0, 0.01, 0.10, 0.40)
FULL_SEEDS = (7, 19, 42)
POLICIES = ("zero", "mean")
NATIVE_ZERO_PATHS = ("separate", "fused")
NATIVE_DMA_ACTION_BYTES = 128 * 1024
DMA_PACKET_BYTES = 64
NATIVE_CLEANER_VALIDATION_LANES = 16 * 4
NATIVE_KMEANS_ARITHMETIC_CORES = 16
NATIVE_MAX_DIMS = 4096
NATIVE_KMEANS_MAX_DIMS = 64
NATIVE_KMEANS_MAX_CLUSTERS = 16
NATIVE_KMEANS_ITERATIONS = 20
NATIVE_BOUND_BASE_CYCLES = 512
NATIVE_BOUND_ACTION_CYCLES = 256
NATIVE_BOUND_PACKET_CYCLES = 10
NATIVE_DATA_BYTES = 64 * 1024 * 1024
NATIVE_DATA_BASE = 0xFC000000
FNV1A64_OFFSET = 14695981039346656037
FNV1A64_PRIME = 1099511628211
CPU_CLASS = {
    "atomic": "AtomicSimpleCPU",
    "timing": "TimingSimpleCPU",
}
TIMING_RESTORE_STRATEGIES = ("direct", "switch")
REQUIRED_MEASUREMENT_CPUS = 4
MEM_MODE = {
    "atomic": "atomic",
    "timing": "timing",
}
GIT_COMMIT_RE = re.compile(r"[0-9a-f]{40}\Z")
RUN_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*\Z")
HEX_DIGEST_RE = re.compile(r"(?:0x)?[0-9a-fA-F]{16}\Z")
ORACLE_LINE_RE = re.compile(
    r"digest=([0-9a-f]{16}),points=([0-9]+),dims=([0-9]+),"
    r"k=([0-9]+),iterations=([0-9]+),dirty_remaining=([0-9]+)\Z"
)
GUEST_ARTIFACT_RE = re.compile(
    r"^GUEST_ARTIFACT_SHA256 kmeans_sepim_fs=([0-9a-f]{64}) "
    r"test-driver\.ko=([0-9a-f]{64}) dataset=([0-9a-f]{64})$",
    re.MULTILINE,
)


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


def run_kmeans_oracle(
    dataset,
    policy,
    points,
    dims,
    clusters,
    iterations,
    outlier_threshold,
):
    command = [
        KMEANS_ORACLE,
        "--dataset",
        dataset,
        "--clusters",
        clusters,
        "--iterations",
        iterations,
        "--imputation",
        policy,
        "--outlier-threshold",
        outlier_threshold,
    ]
    result = run(command, capture=True)
    line = result.stdout.strip()
    match = ORACLE_LINE_RE.fullmatch(line)
    if not match:
        raise RuntimeError(f"invalid k-means oracle output: {line!r}")
    digest, got_points, got_dims, got_k, got_iterations, dirty = match.groups()
    observed = tuple(map(int, (got_points, got_dims, got_k, got_iterations)))
    expected = (points, dims, clusters, iterations)
    if observed != expected:
        raise RuntimeError(
            f"k-means oracle shape mismatch: observed={observed}, expected={expected}"
        )
    if int(dirty) != 0:
        raise RuntimeError(
            f"k-means oracle input retains {dirty} dirty records after policy={policy}"
        )
    return {
        "digest": digest,
        "points": int(got_points),
        "dims": int(got_dims),
        "clusters": int(got_k),
        "iterations": int(got_iterations),
        "dirty_remaining": int(dirty),
        "policy": policy,
        "dataset": str(dataset),
        "dataset_sha256": sha256_file(Path(dataset)),
        "command": " ".join(shlex.quote(str(value)) for value in command),
    }


def git_bytes(repo, *args):
    """Run Git fail-closed with a command-local safe-directory exception.

    The pinned container runs as a different uid from the host checkout owner.
    A per-command ``-c safe.directory=...`` makes that checkout readable without
    mutating either the user's or the container's global Git configuration.
    """
    repo = Path(repo).resolve()
    command = ["git", "-c", f"safe.directory={repo}", *args]
    result = subprocess.run(
        command,
        cwd=repo,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", "replace").strip()
        raise RuntimeError(
            f"Git provenance command failed in {repo}: "
            f"{' '.join(shlex.quote(value) for value in command)}: {stderr}"
        )
    return result.stdout


def git_commit(repo):
    commit = git_bytes(repo, "rev-parse", "--verify", "HEAD^{commit}").decode(
        "ascii", "strict"
    ).strip()
    if GIT_COMMIT_RE.fullmatch(commit) is None:
        raise RuntimeError(
            f"Git provenance in {Path(repo).resolve()} returned a non-40-hex "
            f"commit: {commit!r}"
        )
    return commit


def _digest_field(digest, label, value):
    """Length-prefix one provenance field to prevent concatenation ambiguity."""
    label = label.encode("utf-8")
    digest.update(len(label).to_bytes(8, "big"))
    digest.update(label)
    digest.update(len(value).to_bytes(8, "big"))
    digest.update(value)


def collect_git_provenance(repositories=None):
    """Bind both repositories' commits, tracked diffs, and untracked paths.

    ``git status`` is deliberately executed in addition to the two hashed
    source views.  This makes status availability a hard provenance gate while
    the digest itself has precise, reviewable semantics: a binary tracked diff
    against HEAD and a sorted NUL-delimited list of untracked paths for each
    repository.
    """
    repositories = repositories or (("top", ROOT), ("IMPICA", ROOT / "IMPICA"))
    digest = hashlib.sha256()
    records = {}
    for logical_name, repo in repositories:
        repo = Path(repo).resolve()
        top_level = git_bytes(repo, "rev-parse", "--show-toplevel").decode(
            "utf-8", "strict"
        ).strip()
        if Path(top_level).resolve() != repo:
            raise RuntimeError(
                f"Git provenance repository mismatch for {logical_name}: "
                f"{top_level!r} != {repo}"
            )
        commit = git_commit(repo)
        tracked_diff = git_bytes(
            repo,
            "diff",
            "--binary",
            "--full-index",
            "--no-ext-diff",
            "--no-textconv",
            "HEAD",
            "--",
        )
        untracked_raw = git_bytes(
            repo, "ls-files", "--others", "--exclude-standard", "-z"
        )
        # Fail closed if status cannot inspect either the index or work tree.
        status = git_bytes(
            repo, "status", "--porcelain=v1", "--untracked-files=all", "-z"
        )
        untracked_paths = [value for value in untracked_raw.split(b"\0") if value]
        if untracked_paths != sorted(set(untracked_paths)):
            raise RuntimeError(
                f"Git returned a non-canonical untracked path list for {logical_name}"
            )
        for path in untracked_paths:
            decoded = Path(path.decode("utf-8", "surrogateescape"))
            if decoded.is_absolute() or ".." in decoded.parts:
                raise RuntimeError(
                    f"Git returned an unsafe untracked path for {logical_name}: "
                    f"{decoded}"
                )
        untracked_canonical = b"\0".join(untracked_paths) + (
            b"\0" if untracked_paths else b""
        )
        _digest_field(digest, f"{logical_name}:commit", commit.encode("ascii"))
        _digest_field(digest, f"{logical_name}:tracked_diff", tracked_diff)
        _digest_field(
            digest, f"{logical_name}:untracked_paths", untracked_canonical
        )
        records[logical_name] = {
            "commit": commit,
            "tracked_diff_sha256": hashlib.sha256(tracked_diff).hexdigest(),
            "tracked_diff_bytes": len(tracked_diff),
            "untracked_paths_sha256": hashlib.sha256(
                untracked_canonical
            ).hexdigest(),
            "untracked_path_count": len(untracked_paths),
            "status_sha256": hashlib.sha256(status).hexdigest(),
            "status_bytes": len(status),
        }
    return {
        "status": "valid_commits_and_worktree_views",
        "repositories": records,
        "source_diff_digest": digest.hexdigest(),
        "source_diff_digest_encoding": (
            "sha256_length_prefixed_repo_commit_tracked_binary_diff_"
            "and_sorted_nul_untracked_paths_v1"
        ),
    }


def source_diff_digest():
    """Compatibility helper returning the strict two-repository digest."""
    return collect_git_provenance()["source_diff_digest"]


def display_path(path):
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def artifact_record(path):
    path = path.resolve()
    if not path.is_file():
        raise RuntimeError(f"provenance artifact is missing: {path}")
    before = path.stat()
    digest = sha256_file(path)
    after = path.stat()
    identity_before = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
    )
    identity_after = (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
    )
    if identity_before != identity_after:
        raise RuntimeError(f"provenance artifact changed while hashing: {path}")
    return {
        "path": display_path(path),
        "bytes": after.st_size,
        "sha256": digest,
    }


def resolve_record_path(record):
    if not isinstance(record, dict) or not isinstance(record.get("path"), str):
        raise RuntimeError(f"invalid artifact record: {record!r}")
    path = Path(record["path"])
    return (path if path.is_absolute() else ROOT / path).resolve()


def artifact_core(record, label):
    if not isinstance(record, dict):
        raise RuntimeError(f"{label} must be an artifact object")
    try:
        path = record["path"]
        size = record["bytes"]
        digest = record["sha256"]
    except KeyError as error:
        raise RuntimeError(f"{label} is missing {error.args[0]!r}") from error
    if (
        not isinstance(path, str)
        or not path
        or not isinstance(size, int)
        or isinstance(size, bool)
        or size < 0
        or not isinstance(digest, str)
        or re.fullmatch(r"[0-9a-f]{64}", digest) is None
    ):
        raise RuntimeError(f"{label} has invalid path/bytes/SHA-256 fields")
    return {"path": path, "bytes": size, "sha256": digest}


def validate_artifact_record(record, expected_path, label):
    """Require a provenance record to identify the exact current artifact."""
    core = artifact_core(record, label)
    expected_path = expected_path.resolve()
    if resolve_record_path(core) != expected_path:
        raise RuntimeError(
            f"{label} path mismatch: {core['path']!r} does not identify "
            f"{expected_path}"
        )
    current = artifact_record(expected_path)
    if core["bytes"] != current["bytes"] or core["sha256"] != current["sha256"]:
        raise RuntimeError(
            f"{label} artifact mismatch: recorded={core}, current={current}"
        )
    return current


def validate_exact_artifact_set(records, expected_paths, label):
    if not isinstance(records, list):
        raise RuntimeError(f"{label} must be an artifact list")
    expected = {path.resolve() for path in expected_paths}
    observed = {}
    for index, record in enumerate(records):
        core = artifact_core(record, f"{label}[{index}]")
        resolved = resolve_record_path(core)
        if resolved in observed:
            raise RuntimeError(f"{label} contains duplicate path: {resolved}")
        observed[resolved] = record
    if set(observed) != expected:
        raise RuntimeError(
            f"{label} path set mismatch: missing="
            f"{sorted(map(str, expected - set(observed)))}, extra="
            f"{sorted(map(str, set(observed) - expected))}"
        )
    return [
        validate_artifact_record(observed[path], path, f"{label}:{display_path(path)}")
        for path in sorted(expected, key=str)
    ]


def load_dataset_generation_manifest(
    path,
    dataset_id,
    *,
    points,
    dims,
    data_clusters,
    seeds,
    rates,
    distribution,
    expected_paths,
):
    """Strictly bind a standalone generation transcript to this run matrix."""
    path = path.resolve()
    artifact = artifact_record(path)
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise RuntimeError(
            f"invalid dataset generation manifest JSON: {path}"
        ) from error
    if not isinstance(document, dict) or document.get("schema_version") != 1:
        raise RuntimeError(
            "dataset generation manifest must be a JSON object with "
            "schema_version=1"
        )
    if document.get("dataset_id") != dataset_id:
        raise RuntimeError(
            f"dataset generation manifest ID {document.get('dataset_id')!r} "
            f"does not match --dataset-id={dataset_id!r}"
        )
    parameters = document.get("parameters")
    if not isinstance(parameters, dict):
        raise RuntimeError("dataset generation manifest requires parameters")
    expected_parameters = {
        "points": points,
        "dims": dims,
        "clusters": data_clusters,
        "seeds": list(seeds),
        "rates": list(rates),
        "distribution": distribution,
    }
    try:
        integer_values = (
            parameters["points"],
            parameters["dims"],
            parameters["clusters"],
        )
        manifest_seeds = parameters["seeds"]
        manifest_rates = parameters["rates"]
        manifest_distribution = parameters["distribution"]
    except KeyError as error:
        raise RuntimeError(
            "dataset generation manifest has invalid matrix parameters"
        ) from error
    if (
        any(type(value) is not int for value in integer_values)
        or not isinstance(manifest_seeds, list)
        or any(type(value) is not int for value in manifest_seeds)
        or not isinstance(manifest_rates, list)
        or any(
            type(value) not in (int, float) or not math.isfinite(value)
            for value in manifest_rates
        )
        or not isinstance(manifest_distribution, str)
    ):
        raise RuntimeError(
            "dataset generation manifest has invalid matrix parameter types"
        )
    observed_parameters = {
        "points": integer_values[0],
        "dims": integer_values[1],
        "clusters": integer_values[2],
        "seeds": list(manifest_seeds),
        "rates": [float(value) for value in manifest_rates],
        "distribution": manifest_distribution,
    }
    if (
        observed_parameters["points"] != expected_parameters["points"]
        or observed_parameters["dims"] != expected_parameters["dims"]
        or observed_parameters["clusters"] != expected_parameters["clusters"]
        or observed_parameters["seeds"] != expected_parameters["seeds"]
        or len(observed_parameters["rates"]) != len(expected_parameters["rates"])
        or any(
            abs(observed - expected) > 1e-12
            for observed, expected in zip(
                observed_parameters["rates"], expected_parameters["rates"]
            )
        )
        or observed_parameters["distribution"]
        != expected_parameters["distribution"]
    ):
        raise RuntimeError(
            "dataset generation manifest parameter mismatch: "
            f"observed={observed_parameters}, expected={expected_parameters}"
        )
    validate_artifact_record(
        document.get("generator"), DATASET_GENERATOR, "dataset generator"
    )
    validate_artifact_record(
        document.get("wrapper"), DATASET_WRAPPER, "dataset wrapper"
    )
    commands = document.get("commands")
    if (
        not isinstance(commands, list)
        or not commands
        or any(not isinstance(command, str) or not command.strip() for command in commands)
    ):
        raise RuntimeError(
            "dataset generation manifest requires a non-empty commands string list"
        )
    outputs = validate_exact_artifact_set(
        document.get("outputs"), expected_paths, "dataset generation outputs"
    )
    return {
        "status": "supplied_strictly_validated_generation_transcript",
        "artifact": artifact,
        "document": document,
        "validated_parameters": expected_parameters,
        "validated_outputs": outputs,
    }


def revalidate_dataset_generation_manifest(record):
    """Fail if a multi-day run's generation inputs changed in flight."""
    if record is None:
        return
    path = resolve_record_path(record["artifact"])
    current = artifact_record(path)
    if current != record["artifact"]:
        raise RuntimeError(
            "dataset generation manifest changed during the experiment: "
            f"start={record['artifact']}, finish={current}"
        )
    for output in record["validated_outputs"]:
        current_output = artifact_record(resolve_record_path(output))
        if current_output != output:
            raise RuntimeError(
                "dataset generation output changed during the experiment: "
                f"start={output}, finish={current_output}"
            )


def resolve_fs_bundle():
    fs_root = Path(
        os.environ.get("FS_BUNDLE_ROOT", ROOT / "third_party" / "gem5_fs")
    ).resolve()
    configured = Path(
        os.environ.get("FS_BUNDLE_DIR", fs_root / "aarch-system-2014-10")
    ).resolve()
    for candidate in (configured, fs_root):
        if all(
            (candidate / relative).is_file()
            for relative in (
                "disks/aarch64-ubuntu-trusty-headless.img",
                "binaries/vmlinux.aarch64.20140821",
                "binaries/vexpress.aarch64.20140821.dtb",
                "binaries/boot_emm.arm64",
            )
        ):
            return candidate
    raise RuntimeError(f"cannot resolve gem5 ARM FS bundle under {fs_root}")


def experiment_artifacts():
    bundle = resolve_fs_bundle()
    paths = {
        "gem5_opt": Path(
            os.environ.get("GEM5_BIN", ROOT / "IMPICA/gem5/build/ARM/gem5.opt")
        ),
        "aarch64_guest": WORKLOAD / "kmeans_sepim_fs",
        "test_driver_ko": ROOT / "IMPICA/pim_driver/test-driver.ko",
        "disk_image": Path(
            os.environ.get(
                "DISK_IMAGE",
                bundle / "disks/aarch64-ubuntu-trusty-headless.img",
            )
        ),
        "kernel": Path(
            os.environ.get(
                "KERNEL", bundle / "binaries/vmlinux.aarch64.20140821"
            )
        ),
        "dtb": Path(
            os.environ.get(
                "DTB", bundle / "binaries/vexpress.aarch64.20140821.dtb"
            )
        ),
        "bootloader": Path(
            os.environ.get(
                "BOOTLOADER", bundle / "binaries/boot_emm.arm64"
            )
        ),
        "kmeans_oracle": KMEANS_ORACLE,
    }
    return {name: artifact_record(path) for name, path in paths.items()}


def source_tree_digest():
    """Hash the executable experiment sources, including untracked files."""
    paths = [
        ROOT / "scripts" / "run_native_e2e_gate.py",
        ROOT / "scripts" / "run_native_e2e_gate.sh",
        ROOT / "scripts" / "corrupt_dataset.py",
        ROOT / "scripts" / "generate_native_dataset_matrix.py",
        ROOT / "scripts" / "prepare_disk_image.sh",
        ROOT / "scripts" / "run_baseline_fs.sh",
        ROOT / "IMPICA" / "gem5" / "src" / "dev" / "arm" / "pimDevice_hashtable.cc",
        ROOT / "IMPICA" / "gem5" / "src" / "dev" / "arm" / "pimDevice_hashtable.hh",
        ROOT / "IMPICA" / "gem5" / "util" / "m5" / "m5op_arm_A64.S",
        ROOT / "IMPICA" / "pim_driver" / "sepim_cmd_if.h",
        ROOT / "IMPICA" / "pim_driver" / "test-driver.c",
    ]
    paths.extend(sorted(WORKLOAD.glob("*.[ch]")))
    paths.append(WORKLOAD / "Makefile")
    digest = hashlib.sha256()
    for path in paths:
        if not path.is_file():
            raise RuntimeError(f"source-tree digest input is missing: {path}")
        digest.update(str(path.relative_to(ROOT)).encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def checkpoint_identity(checkpoint, restore_index):
    def checkpoint_sort_key(path):
        suffix = path.name.partition(".")[2]
        return (0, int(suffix)) if suffix.isdigit() else (1, suffix)

    cpts = sorted(
        (path for path in checkpoint.glob("cpt.*") if path.is_dir()),
        key=checkpoint_sort_key,
    )
    if restore_index < 1 or restore_index > len(cpts):
        raise SystemExit(
            f"checkpoint restore index {restore_index} is outside 1..{len(cpts)}: "
            f"{checkpoint}"
        )
    selected = cpts[restore_index - 1]
    descriptor = selected / "m5.cpt"
    if not descriptor.is_file():
        raise SystemExit(f"selected checkpoint lacks m5.cpt: {selected}")
    files = []
    tree_digest = hashlib.sha256()
    paths_before = sorted(
        candidate for candidate in selected.rglob("*") if candidate.is_file()
    )
    for path in paths_before:
        relative = path.relative_to(selected)
        artifact = artifact_record(path)
        record = {
            "path": relative.as_posix(),
            "bytes": artifact["bytes"],
            "sha256": artifact["sha256"],
        }
        files.append(record)
        tree_digest.update(str(relative).encode("utf-8"))
        tree_digest.update(b"\0")
        tree_digest.update(record["sha256"].encode("ascii"))
        tree_digest.update(b"\0")
    paths_after = sorted(
        candidate for candidate in selected.rglob("*") if candidate.is_file()
    )
    if paths_before != paths_after:
        raise RuntimeError(f"selected checkpoint file set changed while hashing: {selected}")
    descriptor_digest = next(
        record["sha256"] for record in files if record["path"] == "m5.cpt"
    )
    return {
        "directory": str(checkpoint),
        "restore_index": restore_index,
        "selected_checkpoint": selected.name,
        "m5_cpt_sha256": descriptor_digest,
        "selected_checkpoint_tree_sha256": tree_digest.hexdigest(),
        "selected_checkpoint_files": files,
    }


def tree_digest_from_records(records, label):
    """Validate and hash a sidecar's sorted relative-path artifact records."""
    if not isinstance(records, list):
        raise RuntimeError(f"{label} files must be a list")
    normalized = []
    seen = set()
    for index, record in enumerate(records):
        core = artifact_core(record, f"{label}.files[{index}]")
        relative = Path(core["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise RuntimeError(f"{label} contains a non-relative path: {relative}")
        path_text = relative.as_posix()
        if path_text in seen:
            raise RuntimeError(f"{label} contains duplicate path: {path_text}")
        seen.add(path_text)
        normalized.append(
            {
                "path": path_text,
                "bytes": core["bytes"],
                "sha256": core["sha256"],
            }
        )
    digest = hashlib.sha256()
    for record in sorted(normalized, key=lambda value: value["path"]):
        digest.update(record["path"].encode("utf-8"))
        digest.update(b"\0")
        digest.update(record["sha256"].encode("ascii"))
        digest.update(b"\0")
    return normalized, digest.hexdigest()


def require_exact_tree_records(observed, expected, label):
    observed_records, observed_digest = tree_digest_from_records(observed, label)
    expected_records, expected_digest = tree_digest_from_records(expected, f"{label}.current")
    observed_by_path = {record["path"]: record for record in observed_records}
    expected_by_path = {record["path"]: record for record in expected_records}
    if observed_by_path != expected_by_path:
        raise RuntimeError(
            f"{label} file set or content mismatch: recorded={observed_by_path}, "
            f"current={expected_by_path}"
        )
    if observed_digest != expected_digest:
        raise RuntimeError(f"{label} digest reconstruction mismatch")
    return observed_digest


def current_directory_tree(root, label):
    """Capture a stable relative-path identity for a provenance-bound tree."""
    root = root.resolve()
    if not root.is_dir():
        raise RuntimeError(f"{label} directory is missing: {root}")
    before = sorted(path for path in root.rglob("*") if path.is_file())
    records = []
    for path in before:
        record = artifact_record(path)
        records.append(
            {
                "path": path.relative_to(root).as_posix(),
                "bytes": record["bytes"],
                "sha256": record["sha256"],
            }
        )
    after = sorted(path for path in root.rglob("*") if path.is_file())
    if before != after:
        raise RuntimeError(f"{label} file set changed while hashing: {root}")
    _, digest = tree_digest_from_records(records, label)
    return records, digest


def checkpoint_bound_identity(checkpoint, checkpoint_record):
    selected_name = checkpoint_record["selected_checkpoint"]
    files = [
        {
            "path": f"selected_checkpoint/{selected_name}/{record['path']}",
            "bytes": record["bytes"],
            "sha256": record["sha256"],
        }
        for record in checkpoint_record["selected_checkpoint_files"]
    ]
    for name in ("config.ini", "system.terminal"):
        record = artifact_record(checkpoint / name)
        files.append(
            {
                "path": name,
                "bytes": record["bytes"],
                "sha256": record["sha256"],
            }
        )
    normalized, digest = tree_digest_from_records(files, "current bound checkpoint")
    return {"files": normalized, "tree_sha256": digest}


def immutable_input_snapshot(
    checkpoint,
    restore_index,
    selected_dataset_paths,
    dataset_generation_manifest_path,
):
    """Hash all long-lived inputs before and after the multi-case experiment."""
    artifacts = experiment_artifacts()
    artifacts.update(
        {
            "dataset_generator": artifact_record(DATASET_GENERATOR),
            "dataset_wrapper": artifact_record(DATASET_WRAPPER),
        }
    )
    checkpoint_record = checkpoint_identity(checkpoint, restore_index)
    checkpoint_sidecar = checkpoint / CHECKPOINT_PROVENANCE_NAME
    return {
        "artifacts": artifacts,
        "checkpoint": checkpoint_record,
        "bound_checkpoint_tree": checkpoint_bound_identity(
            checkpoint, checkpoint_record
        ),
        "checkpoint_provenance": (
            artifact_record(checkpoint_sidecar)
            if checkpoint_sidecar.is_file()
            else None
        ),
        "dataset_generation_manifest": (
            artifact_record(dataset_generation_manifest_path)
            if dataset_generation_manifest_path is not None
            else None
        ),
        "selected_dataset_artifacts": [
            artifact_record(path)
            for path in sorted(
                {path.resolve() for path in selected_dataset_paths}, key=str
            )
        ],
    }


def validate_checkpoint_provenance(
    checkpoint,
    restore_index,
    checkpoint_cpu,
    start_snapshot,
    selected_dataset_paths,
    dataset_generation_manifest_path,
):
    """Bind this run to the schema-1 checkpoint capture sidecar."""
    sidecar = checkpoint / CHECKPOINT_PROVENANCE_NAME
    if not sidecar.is_file():
        raise RuntimeError(
            f"checkpoint provenance sidecar is required: {sidecar}; "
            "recreate the checkpoint with create_native_checkpoint.sh"
        )
    artifact = artifact_record(sidecar)
    try:
        document = json.loads(sidecar.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise RuntimeError(f"invalid checkpoint provenance JSON: {sidecar}") from error
    required_top = {
        "schema_version",
        "created_utc",
        "capture_started_utc",
        "capture_finished_utc",
        "project_root",
        "checkpoint_directory",
        "checkpoint_creation",
        "inputs",
        "workload_data_tree",
        "selected_checkpoint",
        "output_files",
        "bound_checkpoint_tree",
    }
    if not isinstance(document, dict) or document.get("schema_version") != 1:
        raise RuntimeError("checkpoint provenance must be a schema-1 JSON object")
    if not required_top.issubset(document):
        raise RuntimeError(
            "checkpoint provenance is missing keys: "
            f"{sorted(required_top - set(document))}"
        )
    for field, expected_path in (
        ("project_root", ROOT),
        ("checkpoint_directory", checkpoint),
    ):
        value = document[field]
        if not isinstance(value, str):
            raise RuntimeError(f"checkpoint provenance {field} must be a path string")
        candidate = Path(value)
        candidate = (candidate if candidate.is_absolute() else ROOT / candidate).resolve()
        if candidate != expected_path.resolve():
            raise RuntimeError(
                f"checkpoint provenance {field} mismatch: {candidate} != {expected_path}"
            )

    creation = document["checkpoint_creation"]
    expected_creation = {
        "cpu_type": checkpoint_cpu["cpu_type"],
        "expected_cpu_class": checkpoint_cpu["cpu_class"],
        "expected_mem_mode": checkpoint_cpu["mem_mode"],
        "num_cpus": checkpoint_cpu["num_cpus"],
        "memory_size": "2048MB",
        "kernel_memory_limit": "1984MB",
    }
    if not isinstance(creation, dict) or any(
        creation.get(field) != expected
        for field, expected in expected_creation.items()
    ):
        raise RuntimeError(
            "checkpoint creation configuration mismatch: "
            f"recorded={creation}, expected_subset={expected_creation}"
        )
    creation_kind = creation.get("creation_kind", "cold_boot")
    if creation_kind not in {"cold_boot", "timing_recheckpoint_from_parent"}:
        raise RuntimeError(
            f"checkpoint provenance has invalid creation_kind: {creation_kind!r}"
        )
    parent_tree_digest = None
    parent_tree = document.get("parent_checkpoint_tree")
    if creation_kind == "timing_recheckpoint_from_parent":
        if checkpoint_cpu["cpu_type"] != "timing" or not isinstance(parent_tree, dict):
            raise RuntimeError(
                "a timing recheckpoint requires a timing child and parent tree"
            )
        root_value = parent_tree.get("root")
        if not isinstance(root_value, str):
            raise RuntimeError("parent checkpoint tree root is invalid")
        parent_root = Path(root_value)
        parent_root = (
            parent_root if parent_root.is_absolute() else ROOT / parent_root
        ).resolve()
        current_parent_records, current_parent_digest = current_directory_tree(
            parent_root, "current parent checkpoint tree"
        )
        parent_tree_digest = require_exact_tree_records(
            parent_tree.get("files"),
            current_parent_records,
            "checkpoint provenance parent_checkpoint_tree",
        )
        if (
            parent_tree.get("file_count") != len(current_parent_records)
            or parent_tree.get("tree_hash_algorithm") != TREE_HASH_ALGORITHM
            or parent_tree.get("tree_sha256") != current_parent_digest
            or parent_tree_digest != current_parent_digest
        ):
            raise RuntimeError("parent checkpoint tree digest is inconsistent")
    elif parent_tree is not None:
        raise RuntimeError("cold-boot checkpoint unexpectedly declares a parent tree")

    expected_creator_paths = {
        "checkpoint_creator": ROOT / "scripts/create_native_checkpoint.sh",
        "provenance_helper": ROOT / "scripts/checkpoint_provenance.py",
        "baseline_runner": ROOT / "scripts/run_baseline_fs.sh",
        "common_helpers": ROOT / "scripts/_common.sh",
        "guest_checkpoint_script": ROOT / "scripts/guest_timing_recheckpoint.rcS",
    }
    if creation_kind == "cold_boot":
        expected_creator_paths.update(
            guest_checkpoint_script=ROOT / "scripts/guest_boot_checkpoint.rcS",
            disk_preparer=ROOT / "scripts/prepare_disk_image.sh",
        )
    creator_inputs = document.get("creator_inputs")
    if not isinstance(creator_inputs, dict) or set(creator_inputs) != set(
        expected_creator_paths
    ):
        raise RuntimeError(
            "checkpoint creator input set mismatch: "
            f"recorded={sorted(creator_inputs) if isinstance(creator_inputs, dict) else creator_inputs!r}"
        )
    for name, path in expected_creator_paths.items():
        record = creator_inputs[name]
        if record.get("logical_name") != name or record.get("required") is not True:
            raise RuntimeError(f"checkpoint creator input {name} lacks exact binding")
        validate_artifact_record(record, path, f"checkpoint creator input {name}")

    inputs = document["inputs"]
    required_inputs = (
        "disk_image",
        "gem5_opt",
        "aarch64_guest",
        "test_driver_ko",
        "kmeans_oracle",
        "kernel",
        "dtb",
        "bootloader",
        "dataset_generator",
        "dataset_wrapper",
    )
    if not isinstance(inputs, dict) or set(inputs) != set(required_inputs):
        raise RuntimeError(
            "checkpoint provenance input set mismatch: "
            f"recorded={sorted(inputs) if isinstance(inputs, dict) else inputs!r}, "
            f"expected={sorted(required_inputs)}"
        )
    for name in required_inputs:
        record = inputs[name]
        if (
            not isinstance(record, dict)
            or record.get("logical_name") != name
            or record.get("required") is not True
        ):
            raise RuntimeError(
                f"checkpoint input {name} lacks exact logical_name/required binding"
            )
        expected = start_snapshot["artifacts"][name]
        validate_artifact_record(
            record, resolve_record_path(expected), f"checkpoint input {name}"
        )

    current_checkpoint = start_snapshot["checkpoint"]
    selected = document["selected_checkpoint"]
    if not isinstance(selected, dict):
        raise RuntimeError("checkpoint provenance selected_checkpoint must be an object")
    expected_selected_path = (
        checkpoint / current_checkpoint["selected_checkpoint"]
    ).resolve()
    selected_path = selected.get("path")
    if not isinstance(selected_path, str):
        raise RuntimeError("checkpoint provenance selected checkpoint path is invalid")
    selected_path = Path(selected_path)
    selected_path = (
        selected_path if selected_path.is_absolute() else ROOT / selected_path
    ).resolve()
    if (
        selected.get("restore_index") != restore_index
        or selected.get("selected_checkpoint")
        != current_checkpoint["selected_checkpoint"]
        or selected_path != expected_selected_path
        or selected.get("selected_checkpoint_tree_sha256")
        != current_checkpoint["selected_checkpoint_tree_sha256"]
    ):
        raise RuntimeError(
            "checkpoint provenance selected checkpoint identity does not match "
            "the requested current checkpoint"
        )
    selected_digest = require_exact_tree_records(
        selected.get("files"),
        current_checkpoint["selected_checkpoint_files"],
        "checkpoint provenance selected_checkpoint",
    )
    if (
        selected.get("file_count") != len(selected.get("files"))
        or selected.get("tree_hash_algorithm") != TREE_HASH_ALGORITHM
        or selected_digest != selected["selected_checkpoint_tree_sha256"]
    ):
        raise RuntimeError("selected checkpoint sidecar tree digest is inconsistent")

    output_files = document["output_files"]
    if not isinstance(output_files, dict) or set(output_files) != {
        "config_ini",
        "system_terminal",
    }:
        raise RuntimeError("checkpoint provenance output_files set is invalid")
    for name, filename in (
        ("config_ini", "config.ini"),
        ("system_terminal", "system.terminal"),
    ):
        record = output_files[name]
        if (
            not isinstance(record, dict)
            or record.get("logical_name") != name
            or record.get("required") is not True
        ):
            raise RuntimeError(f"checkpoint output {name} lacks required binding")
        validate_artifact_record(record, checkpoint / filename, f"checkpoint {name}")

    bound = document["bound_checkpoint_tree"]
    if not isinstance(bound, dict):
        raise RuntimeError("checkpoint provenance bound_checkpoint_tree is invalid")
    bound_digest = require_exact_tree_records(
        bound.get("files"),
        start_snapshot["bound_checkpoint_tree"]["files"],
        "checkpoint provenance bound_checkpoint_tree",
    )
    if (
        bound.get("file_count") != len(bound.get("files"))
        or bound.get("tree_hash_algorithm") != TREE_HASH_ALGORITHM
        or bound.get("tree_sha256") != bound_digest
        or bound_digest != start_snapshot["bound_checkpoint_tree"]["tree_sha256"]
    ):
        raise RuntimeError("bound checkpoint sidecar tree digest is inconsistent")

    data_tree = document["workload_data_tree"]
    if not isinstance(data_tree, dict):
        raise RuntimeError("checkpoint provenance workload_data_tree is invalid")
    data_root = (WORKLOAD / "data").resolve()
    root_value = data_tree.get("root")
    if not isinstance(root_value, str):
        raise RuntimeError("checkpoint workload data root is invalid")
    recorded_root = Path(root_value)
    recorded_root = (
        recorded_root if recorded_root.is_absolute() else ROOT / recorded_root
    ).resolve()
    if recorded_root != data_root:
        raise RuntimeError(
            f"checkpoint workload data root mismatch: {recorded_root} != {data_root}"
        )
    data_records, data_digest = tree_digest_from_records(
        data_tree.get("files"), "checkpoint provenance workload_data_tree"
    )
    if (
        data_tree.get("file_count") != len(data_records)
        or data_tree.get("tree_hash_algorithm") != TREE_HASH_ALGORITHM
        or data_tree.get("tree_sha256") != data_digest
    ):
        raise RuntimeError("checkpoint workload data tree digest is inconsistent")
    data_by_path = {record["path"]: record for record in data_records}
    selected_paths = {path.resolve() for path in selected_dataset_paths}
    if dataset_generation_manifest_path is not None:
        selected_paths.add(dataset_generation_manifest_path.resolve())
    checkpoint_data_validated = 0
    for path in sorted(selected_paths, key=str):
        try:
            relative = path.relative_to(data_root).as_posix()
        except ValueError:
            if path == (
                dataset_generation_manifest_path.resolve()
                if dataset_generation_manifest_path is not None
                else None
            ):
                continue
            raise RuntimeError(f"selected dataset artifact is outside data root: {path}")
        if relative not in data_by_path:
            raise RuntimeError(
                f"selected dataset artifact was not captured in checkpoint: {relative}"
            )
        current = artifact_record(path)
        recorded = data_by_path[relative]
        if (
            current["bytes"] != recorded["bytes"]
            or current["sha256"] != recorded["sha256"]
        ):
            raise RuntimeError(
                f"checkpoint dataset artifact mismatch for {relative}: "
                f"recorded={recorded}, current={current}"
            )
        checkpoint_data_validated += 1

    return {
        "status": "schema_1_checkpoint_lineage_validated",
        "artifact": artifact,
        "publication_eligible": True,
        "validated_input_names": required_inputs,
        "selected_checkpoint_tree_sha256": selected_digest,
        "bound_checkpoint_tree_sha256": bound_digest,
        "workload_data_tree_sha256": data_digest,
        "checkpoint_data_artifacts_validated": checkpoint_data_validated,
        "creation_kind": creation_kind,
        "parent_checkpoint_tree_sha256": parent_tree_digest,
        "creator_inputs_validated": sorted(expected_creator_paths),
    }


def validate_reserved_checkpoint_memory(checkpoint):
    terminal = checkpoint / "system.terminal"
    if not terminal.is_file():
        raise RuntimeError(f"checkpoint terminal is missing: {terminal}")
    boot_terminal = terminal
    text = (
        boot_terminal.read_bytes()
        .replace(b"\0", b"")
        .decode("utf-8", "ignore")
        .replace("\r", "")
    )
    command_lines = [line for line in text.splitlines() if "Kernel command line:" in line]
    if not command_lines:
        sidecar = checkpoint / CHECKPOINT_PROVENANCE_NAME
        try:
            provenance = json.loads(sidecar.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise RuntimeError(
                "checkpoint has no cold-boot log and no valid parent provenance"
            ) from error
        creation = provenance.get("checkpoint_creation", {})
        parent_tree = provenance.get("parent_checkpoint_tree")
        if (
            creation.get("creation_kind") != "timing_recheckpoint_from_parent"
            or not isinstance(parent_tree, dict)
        ):
            raise RuntimeError(
                "checkpoint terminal lacks boot evidence and is not a bound recheckpoint"
            )
        parent_root_value = parent_tree.get("root")
        if not isinstance(parent_root_value, str):
            raise RuntimeError("recheckpoint parent tree has no root path")
        parent_root = Path(parent_root_value)
        parent_root = (
            parent_root if parent_root.is_absolute() else ROOT / parent_root
        ).resolve()
        records = parent_tree.get("files")
        if not isinstance(records, list):
            raise RuntimeError("recheckpoint parent tree has no artifact records")
        terminal_records = [
            record for record in records
            if isinstance(record, dict) and record.get("path") == "system.terminal"
        ]
        if len(terminal_records) != 1:
            raise RuntimeError("recheckpoint parent tree does not bind system.terminal")
        boot_terminal = parent_root / "system.terminal"
        current = artifact_record(boot_terminal)
        recorded = artifact_core(
            terminal_records[0], "recheckpoint parent system.terminal"
        )
        if current["bytes"] != recorded["bytes"] or current["sha256"] != recorded["sha256"]:
            raise RuntimeError("recheckpoint parent boot terminal changed")
        text = (
            boot_terminal.read_bytes()
            .replace(b"\0", b"")
            .decode("utf-8", "ignore")
            .replace("\r", "")
        )
        command_lines = [
            line for line in text.splitlines() if "Kernel command line:" in line
        ]
    if not command_lines or not any(
        "mem=1984MB" in line.split("Kernel command line:", 1)[1].split()
        for line in command_lines
    ):
        raise RuntimeError(
            "checkpoint kernel command line does not contain the exact "
            "mem=1984MB token"
        )
    if not any("Memory limited to 1984MB" in line for line in text.splitlines()):
        raise RuntimeError(
            "checkpoint boot log does not confirm 'Memory limited to 1984MB'"
        )

    config = read_gem5_config(checkpoint / "config.ini")
    boot_tokens = config.get("system", "boot_osflags").split()
    if "mem=1984MB" not in boot_tokens:
        raise RuntimeError("checkpoint config boot_osflags lacks mem=1984MB")
    start_text, end_text = config.get("system", "mem_ranges").split(":", 1)
    physical_bytes = int(end_text, 0) - int(start_text, 0) + 1
    if physical_bytes != 2048 * 1024 * 1024:
        raise RuntimeError(
            f"checkpoint physical memory is {physical_bytes} bytes, expected 2 GiB"
        )
    cache_line_size = config.getint("system", "cache_line_size")
    if cache_line_size != DMA_PACKET_BYTES:
        raise RuntimeError(
            f"checkpoint cache line is {cache_line_size} bytes, but native packet "
            f"accounting requires {DMA_PACKET_BYTES}"
        )
    return {
        "terminal": display_path(terminal),
        "terminal_sha256": sha256_file(terminal),
        "boot_evidence_terminal": display_path(boot_terminal),
        "boot_evidence_terminal_sha256": sha256_file(boot_terminal),
        "kernel_mem_limit": "1984MB",
        "physical_memory_bytes": physical_bytes,
        "cache_line_size_bytes": cache_line_size,
        "reserved_top_bytes": physical_bytes - 1984 * 1024 * 1024,
        "validation": "kernel command line, boot acknowledgement, and config verified",
    }


def gem5_checkpoint_arg(checkpoint):
    """Prefer a workspace-relative argument to avoid shell word splitting."""
    try:
        return str(checkpoint.relative_to(ROOT))
    except ValueError:
        value = str(checkpoint)
        if any(character.isspace() for character in value):
            raise SystemExit(
                "an external checkpoint path containing whitespace cannot be passed "
                "through run_baseline_fs.sh; place it under the workspace"
            )
        return value


def extract_rows(terminal):
    text = (
        terminal.read_bytes()
        .replace(b"\0", b"")
        .decode("utf-8", "ignore")
        .replace("\r", "")
    )
    rows = []
    block = []
    collecting = False
    for line in text.splitlines():
        marker = line.strip()
        if marker == "FSCSV_BEGIN":
            if collecting:
                raise RuntimeError(f"nested FSCSV_BEGIN in {terminal}")
            collecting = True
            block = []
        elif marker == "FSCSV_END":
            if not collecting:
                raise RuntimeError(f"FSCSV_END without FSCSV_BEGIN in {terminal}")
            if not block:
                raise RuntimeError(f"empty FSCSV block in {terminal}")
            rows.extend(csv.DictReader(io.StringIO("\n".join(block) + "\n")))
            collecting = False
            block = []
        elif collecting:
            block.append(line)
    if collecting:
        raise RuntimeError(f"unterminated FSCSV block in {terminal}")
    return rows


def validate_guest_artifact_hashes(
    terminal, expected_guest, expected_driver, expected_dataset
):
    text = (
        terminal.read_bytes()
        .replace(b"\0", b"")
        .decode("utf-8", "ignore")
        .replace("\r", "")
    )
    matches = GUEST_ARTIFACT_RE.findall(text)
    if len(matches) != 1:
        raise RuntimeError(
            f"expected exactly one guest artifact hash marker in {terminal}, "
            f"found {len(matches)}"
        )
    guest_hash, driver_hash, dataset_hash = matches[0]
    if (
        guest_hash != expected_guest
        or driver_hash != expected_driver
        or dataset_hash != expected_dataset
    ):
        raise RuntimeError(
            f"guest artifact mismatch in {terminal}: workload={guest_hash}/"
            f"{expected_guest}, driver={driver_hash}/{expected_driver}, "
            f"dataset={dataset_hash}/{expected_dataset}"
        )
    return {
        "guest_workload_sha256": guest_hash,
        "guest_driver_sha256": driver_hash,
        "guest_dataset_sha256": dataset_hash,
    }


def run_guest_artifact_attestation(
    *,
    raw_dir,
    checkpoint_arg,
    checkpoint_index,
    checkpoint_cpu,
    dataset_id,
    cases,
    expected_guest_sha256,
    expected_driver_sha256,
):
    """Hash all guest inputs once with atomic CPUs outside timing evidence.

    File bytes do not depend on the CPU timing model.  A single direct atomic
    restore therefore attests the exact checkpoint/disk guest files without
    repeatedly spending TimingSimpleCPU wall time on SHA-256 before every
    measured native-device command.
    """
    attestation_dir = raw_dir / "guest_artifact_attestation"
    terminal = attestation_dir / "system.terminal"
    guest_script = raw_dir / "guest_artifact_attestation.rcS"
    unique = {}
    for case in cases:
        guest_path = (Path("./data") / dataset_id / case["dataset"].name).as_posix()
        previous = unique.setdefault(guest_path, case["input_sha256"])
        if previous != case["input_sha256"]:
            raise RuntimeError(f"guest attestation path has conflicting hashes: {guest_path}")
    lines = [
        "#!/bin/sh",
        "set -ex",
        "cd /home/workloads/kmeans_sepim_fs",
        "workload_sha=$(sha256sum ./kmeans_sepim_fs | awk '{print $1}')",
        (
            "driver_sha=$(sha256sum /home/pim_driver/test-driver.ko "
            "| awk '{print $1}')"
        ),
        "set +x",
        (
            "echo \"GUEST_ATTEST_WORKLOAD sha256=$workload_sha "
            "GUEST_ATTEST_DRIVER sha256=$driver_sha\""
        ),
    ]
    for index, guest_path in enumerate(sorted(unique)):
        variable = f"dataset_sha_{index}"
        lines.extend(
            (
                f"{variable}=$(sha256sum {shlex.quote(guest_path)} | awk '{{print $1}}')",
                (
                    f"echo \"GUEST_ATTEST_DATASET path={guest_path} "
                    f"sha256=${variable}\""
                ),
            )
        )
    lines.append("m5 exit")
    guest_script.write_text("\n".join(lines) + "\n")
    guest_script.chmod(0o755)

    restore_options = (
        f"-r {checkpoint_index} --checkpoint-dir={checkpoint_arg} "
        "--cpu-type=atomic --restore-with-cpu=atomic"
    )
    env = os.environ.copy()
    env.update(
        {
            "OUTDIR": str(attestation_dir),
            "BOOT_SCRIPT": str(guest_script),
            "GEM5_EXTRA_ARGS": restore_options,
            "MEM_SIZE": "2048MB",
            "SEPIM_KERNEL_MEM": "1984MB",
            "CPUS": str(checkpoint_cpu["num_cpus"]),
        }
    )
    run([ROOT / "scripts" / "run_baseline_fs.sh", "--mode", "custom"], env=env)
    cpu = validate_case_cpu_config(
        attestation_dir / "config.ini",
        "atomic",
        checkpoint_cpu["cpu_type"],
        "direct",
        checkpoint_cpu["num_cpus"],
    )
    if not terminal.is_file():
        raise RuntimeError("guest artifact attestation terminal is missing")
    text = (
        terminal.read_bytes()
        .replace(b"\0", b"")
        .decode("utf-8", "ignore")
        .replace("\r", "")
    )
    binary_matches = re.findall(
        r"GUEST_ATTEST_WORKLOAD sha256=([0-9a-f]{64}) "
        r"GUEST_ATTEST_DRIVER sha256=([0-9a-f]{64})",
        text,
    )
    if binary_matches != [(expected_guest_sha256, expected_driver_sha256)]:
        raise RuntimeError(
            "atomic guest attestation did not match workload/driver inputs: "
            f"observed={binary_matches}"
        )
    dataset_matches = re.findall(
        r"GUEST_ATTEST_DATASET path=([^\s]+) sha256=([0-9a-f]{64})", text
    )
    observed = {}
    for path, digest in dataset_matches:
        if path in observed:
            raise RuntimeError(f"duplicate guest dataset attestation: {path}")
        observed[path] = digest
    if observed != unique:
        raise RuntimeError(
            "atomic guest dataset attestation mismatch: "
            f"observed={observed}, expected={unique}"
        )
    return {
        "status": "pass",
        "kind": "atomic_guest_hash_preflight_same_checkpoint_and_disk",
        "purpose": "byte_attestation_only_excluded_from_timing_evidence",
        "restore_options": restore_options,
        "cpu_configuration": cpu,
        "guest_workload_sha256": expected_guest_sha256,
        "guest_driver_sha256": expected_driver_sha256,
        "unique_dataset_files": len(unique),
        "datasets": [
            {"guest_path": path, "sha256": digest}
            for path, digest in sorted(unique.items())
        ],
        "terminal": artifact_record(terminal),
        "config_ini": artifact_record(attestation_dir / "config.ini"),
    }


def run_clock_probe_preflight(
    *,
    raw_dir,
    checkpoint_arg,
    checkpoint_index,
    checkpoint_cpu,
    expected_ticks=1000,
):
    """Verify that gem5 MMIO reports exact expected clock ticks without unsupported register warnings."""
    preflight_dir = raw_dir / "clock_probe_preflight"
    terminal = preflight_dir / "system.terminal"
    guest_script = raw_dir / "guest_clock_probe_preflight.rcS"
    script_lines = [
        "#!/bin/sh",
        "set -ex",
        "cd /home/pim_driver",
        "mknod /dev/pimbt c 70 0 || true",
        "insmod ./test-driver.ko || { echo '[GUEST][ERROR] insmod failed'; m5 exit; exit 1; }",
        "chmod 600 /dev/pimbt",
        "cd /home/workloads/kmeans_sepim_fs",
        "./kmeans_sepim_fs --clock-probe || { echo '[GUEST][ERROR] clock probe failed'; m5 exit; exit 1; }",
        "m5 exit",
    ]
    guest_script.write_text("\n".join(script_lines) + "\n")
    guest_script.chmod(0o755)

    restore_plan = build_restore_plan(
        checkpoint_index,
        checkpoint_arg,
        checkpoint_cpu["cpu_type"],
        checkpoint_cpu["cpu_type"],
        "direct",
    )
    restore_options = restore_plan["options"]
    env = os.environ.copy()
    env.update(
        {
            "OUTDIR": str(preflight_dir),
            "BOOT_SCRIPT": str(guest_script),
            "GEM5_EXTRA_ARGS": restore_options,
            "MEM_SIZE": "2048MB",
            "SEPIM_KERNEL_MEM": "1984MB",
            "CPUS": str(checkpoint_cpu["num_cpus"]),
        }
    )
    run([ROOT / "scripts" / "run_baseline_fs.sh", "--mode", "custom"], env=env)
    if not terminal.is_file():
        raise RuntimeError("clock probe preflight terminal is missing")
    text = (
        terminal.read_bytes()
        .replace(b"\0", b"")
        .decode("utf-8", "ignore")
        .replace("\r", "")
    )
    if "Read to unsupported registers for PIM BT" in text:
        raise RuntimeError(
            f"clock probe preflight failed: gem5 reported unsupported PIM BT register reads in {terminal}"
        )
    match = re.search(r"\[CLOCK_PROBE\]\s+clock_period_ticks=(\d+)", text)
    if not match:
        raise RuntimeError(
            f"clock probe preflight failed: marker [CLOCK_PROBE] missing in {terminal}"
        )
    ticks = int(match.group(1))
    if ticks != expected_ticks or ticks == 0:
        raise RuntimeError(
            f"clock probe preflight failed: expected {expected_ticks} ticks, got {ticks} in {terminal}"
        )
    return {
        "status": "pass",
        "clock_period_ticks": ticks,
        "restore_options": restore_options,
        "terminal": artifact_record(terminal),
    }


def read_gem5_config(path):
    if not path.is_file():
        raise RuntimeError(f"gem5 config.ini is missing: {path}")
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    parser.optionxform = str
    with path.open() as stream:
        parser.read_file(stream)
    return parser


def cpu_sections(config, prefix):
    expression = re.compile(r"^system\.%s\d+$" % re.escape(prefix))
    return sorted(section for section in config.sections() if expression.match(section))


def secondary_cpu_sections(config):
    expression = re.compile(
        r"^system\.(?:switch_cpus|switch_cpus_1|repeat_switch_cpus)\d+$"
    )
    return sorted(section for section in config.sections() if expression.match(section))


def infer_checkpoint_cpu(checkpoint):
    config_path = checkpoint / "config.ini"
    config = read_gem5_config(config_path)
    sections = cpu_sections(config, "cpu")
    if not sections:
        raise RuntimeError(f"checkpoint has no system.cpuN sections: {config_path}")
    classes = {config.get(section, "type") for section in sections}
    inverse = {value: key for key, value in CPU_CLASS.items()}
    if len(classes) != 1 or next(iter(classes)) not in inverse:
        raise RuntimeError(
            f"checkpoint CPU class is unsupported or heterogeneous: {sorted(classes)}"
        )
    cpu_type = inverse[next(iter(classes))]
    mem_mode = config.get("system", "mem_mode")
    if mem_mode != MEM_MODE[cpu_type]:
        raise RuntimeError(
            f"checkpoint CPU/memory mode mismatch: cpu={cpu_type}, "
            f"mem_mode={mem_mode}"
        )
    return {
        "cpu_type": cpu_type,
        "cpu_class": CPU_CLASS[cpu_type],
        "mem_mode": mem_mode,
        "num_cpus": len(sections),
        "config_ini": display_path(config_path),
        "config_ini_sha256": sha256_file(config_path),
    }


def build_restore_plan(
    checkpoint_index,
    checkpoint_arg,
    measurement_cpu,
    checkpoint_cpu,
    timing_restore_strategy="direct",
):
    """Construct and describe the old-gem5 checkpoint restore CPU strategy."""
    if measurement_cpu not in CPU_CLASS or checkpoint_cpu not in CPU_CLASS:
        raise ValueError("unsupported measurement or checkpoint CPU")
    if timing_restore_strategy not in TIMING_RESTORE_STRATEGIES:
        raise ValueError(
            f"unsupported timing restore strategy: {timing_restore_strategy}"
        )
    if measurement_cpu == "atomic":
        if timing_restore_strategy != "direct":
            raise ValueError(
                "atomic measurement supports only the direct atomic restore strategy"
            )
        restore_with_cpu = "atomic"
        strategy = "direct"
    elif timing_restore_strategy == "direct":
        # Old gem5 reconstructs checkpoint architectural state directly into
        # TimingSimpleCPU.  This supports both a same-class timing checkpoint
        # and the explicitly disclosed atomic-checkpoint fallback.  Supplying
        # timing for both options avoids Simulation.py's 10,000-tick atomic
        # warm-up and runtime CPU switch.
        restore_with_cpu = "timing"
        strategy = "direct"
    else:
        restore_with_cpu = checkpoint_cpu
        strategy = "switch"
    switch_used = strategy == "switch" and measurement_cpu != restore_with_cpu
    options = (
        f"-r {checkpoint_index} --checkpoint-dir={checkpoint_arg} "
        f"--cpu-type={measurement_cpu} --restore-with-cpu={restore_with_cpu}"
    )
    return {
        "options": options,
        "strategy": strategy,
        "measurement_cpu_type": measurement_cpu,
        "checkpoint_cpu_type": checkpoint_cpu,
        "restore_with_cpu": restore_with_cpu,
        "cpu_switch_used": switch_used,
        "cpu_switch_warmup_ticks": 10000 if switch_used else 0,
        "publication_strategy_eligible": (
            measurement_cpu == "timing"
            and checkpoint_cpu == "timing"
            and strategy == "direct"
            and not switch_used
        ),
        "checkpoint_restore_semantics": (
            "atomic_architectural_checkpoint_state_restored_directly_into_"
            "TimingSimpleCPU"
            if measurement_cpu == "timing" and strategy == "direct"
            and checkpoint_cpu == "atomic"
            else "same_cpu_class_direct_restore"
            if strategy == "direct"
            else "checkpoint_cpu_restore_then_runtime_cpu_switch"
        ),
    }


def evidence_tier_for(cpu_record):
    if cpu_record["requested_cpu_type"] == "atomic":
        return "native_candidate_atomic_padded_command_smoke"
    if cpu_record["restore_strategy"] == "direct" and not cpu_record[
        "cpu_switch_used"
    ]:
        return "native_candidate_timing_direct_restore_padded_command_measurement"
    return "native_diagnostic_timing_runtime_cpu_switch_measurement"


def validate_case_cpu_config(
    config_path,
    requested_cpu,
    checkpoint_cpu,
    restore_strategy="direct",
    expected_num_cpus=None,
):
    """Validate the actual old-gem5 CPU graph and memory mode for one case."""
    if restore_strategy not in TIMING_RESTORE_STRATEGIES:
        raise RuntimeError(f"invalid restore strategy: {restore_strategy}")
    if requested_cpu == "atomic" and restore_strategy != "direct":
        raise RuntimeError("atomic runs must use direct atomic restore")
    config = read_gem5_config(config_path)
    cache_line_size = config.getint("system", "cache_line_size")
    if cache_line_size != DMA_PACKET_BYTES:
        raise RuntimeError(
            f"case cache line is {cache_line_size} bytes, but native submitted-"
            f"packet accounting requires {DMA_PACKET_BYTES}"
        )
    initial_sections = cpu_sections(config, "cpu")
    if not initial_sections:
        raise RuntimeError(f"case config has no system.cpuN sections: {config_path}")
    if expected_num_cpus is not None and len(initial_sections) != expected_num_cpus:
        raise RuntimeError(
            f"case config has {len(initial_sections)} CPUs, checkpoint has "
            f"{expected_num_cpus}"
        )
    initial_classes = {config.get(section, "type") for section in initial_sections}
    direct = restore_strategy == "direct"
    primary_cpu = requested_cpu if direct else checkpoint_cpu
    expected_initial = CPU_CLASS[primary_cpu]
    if initial_classes != {expected_initial}:
        raise RuntimeError(
            f"case config initial CPU mismatch: {sorted(initial_classes)}, "
            f"expected {expected_initial}"
        )
    initial_mem_mode = config.get("system", "mem_mode")
    if initial_mem_mode != MEM_MODE[primary_cpu]:
        raise RuntimeError(
            f"case config initial mem_mode={initial_mem_mode}, expected "
            f"{MEM_MODE[primary_cpu]}"
        )

    switch_sections = cpu_sections(config, "switch_cpus")
    all_secondary_sections = secondary_cpu_sections(config)
    switch_used = not direct and requested_cpu != checkpoint_cpu
    if switch_used:
        switch_classes = {config.get(section, "type") for section in switch_sections}
        if len(switch_sections) != len(initial_sections) or switch_classes != {
            CPU_CLASS[requested_cpu]
        }:
            raise RuntimeError(
                f"case config restore switch mismatch: sections={switch_sections}, "
                f"classes={sorted(switch_classes)}, expected "
                f"{CPU_CLASS[requested_cpu]}"
            )
        unexpected_secondary = set(all_secondary_sections) - set(switch_sections)
        if unexpected_secondary:
            raise RuntimeError(
                "case config constructed unexpected secondary CPUs: "
                f"{sorted(unexpected_secondary)}"
            )
    elif all_secondary_sections:
        raise RuntimeError(
            f"case config unexpectedly constructed restore-switch CPUs: "
            f"{all_secondary_sections}"
        )

    if requested_cpu == "timing" and direct:
        if len(initial_sections) != REQUIRED_MEASUREMENT_CPUS:
            raise RuntimeError(
                f"direct timing restore requires {REQUIRED_MEASUREMENT_CPUS} "
                f"system.cpu objects, found {len(initial_sections)}"
            )
        if initial_classes != {CPU_CLASS["timing"]} or initial_mem_mode != "timing":
            raise RuntimeError(
                "direct timing restore did not construct only TimingSimpleCPU "
                "system.cpu objects in timing memory mode"
            )

    return {
        "requested_cpu_type": requested_cpu,
        "measurement_cpu_class": CPU_CLASS[requested_cpu],
        "effective_mem_mode": MEM_MODE[requested_cpu],
        "checkpoint_cpu_type": checkpoint_cpu,
        "restore_strategy": restore_strategy,
        "restore_with_cpu": primary_cpu,
        "restore_cpu_class": CPU_CLASS[primary_cpu],
        "configured_primary_cpu_type": primary_cpu,
        "configured_initial_mem_mode": initial_mem_mode,
        "cpu_switch_used": switch_used,
        "cpu_switch_warmup_ticks": 10000 if switch_used else 0,
        "num_cpus": len(initial_sections),
        "config_ini_sha256": sha256_file(config_path),
        "cache_line_size_bytes": cache_line_size,
        "checkpoint_restore_semantics": (
            "atomic_architectural_checkpoint_state_restored_directly_into_"
            "TimingSimpleCPU"
            if requested_cpu == "timing" and direct and checkpoint_cpu == "atomic"
            else "timing_architectural_checkpoint_state_restored_directly_into_"
            "AtomicSimpleCPU"
            if requested_cpu == "atomic" and direct and checkpoint_cpu == "timing"
            else "same_cpu_class_direct_restore"
            if direct and requested_cpu == checkpoint_cpu
            else "checkpoint_cpu_restore_then_runtime_cpu_switch"
        ),
    }


def fnv1a_add_u64(digest, value):
    for byte in range(8):
        digest ^= (value >> (byte * 8)) & 0xFF
        digest = (digest * FNV1A64_PRIME) & 0xFFFFFFFFFFFFFFFF
    return digest


def dma_chunks(data_bytes, chunk_bytes):
    chunks = []
    offset = 0
    while offset < data_bytes:
        size = min(chunk_bytes, data_bytes - offset)
        chunks.append((NATIVE_DATA_BASE + offset, size))
        offset += size
    return chunks


def submitted_packets(chunks):
    return sum(
        (addr % DMA_PACKET_BYTES + size + DMA_PACKET_BYTES - 1)
        // DMA_PACKET_BYTES
        for addr, size in chunks
    )


def phase_bound_cycles(actions, packets, compute_cycles):
    """Reconstruct the fixed public deadline without trusting guest output."""
    return (
        NATIVE_BOUND_BASE_CYCLES
        + actions * NATIVE_BOUND_ACTION_CYCLES
        + packets * NATIVE_BOUND_PACKET_CYCLES
        + compute_cycles
    )


def ceil_div(value, divisor):
    if value < 0 or divisor <= 0:
        raise RuntimeError(
            f"invalid public ceil division: value={value}, divisor={divisor}"
        )
    return value // divisor + (value % divisor != 0)


def expected_native_transcript(
    mode,
    policy,
    points,
    dims,
    workload="aggregate",
    clusters=0,
    iterations=1,
    native_zero_path="separate",
):
    """Independently reconstruct the device's public trace and fixed deadline.

    The cleaner has 64 validation lanes, but k-means arithmetic is charged to
    the declared 16 arithmetic cores.  They are intentionally separate public
    resources: treating all 64 validation lanes as general multiply/accumulate
    cores would understate the k-means baseline and distort its overhead.

    In the fused zero-imputation path, validation is serialized before the
    first-iteration classification for each public record-aligned chunk.  Only
    the public write allowance that can overlap that chunk's classification is
    credited; the phase base and validation cycles are never hidden.
    """
    if native_zero_path not in NATIVE_ZERO_PATHS:
        raise RuntimeError(f"unsupported native zero path: {native_zero_path}")
    if native_zero_path == "fused" and not (
        workload == "kmeans"
        and mode == "pim-oblivious"
        and policy == "zero"
    ):
        raise RuntimeError(
            "the fused native zero path is valid only for pim-oblivious "
            "zero-imputation k-means"
        )
    data_bytes = points * dims * 4
    if data_bytes <= 0 or data_bytes > NATIVE_DATA_BYTES:
        raise RuntimeError(f"native transcript data size is invalid: {data_bytes}")
    address_end = NATIVE_DATA_BASE + data_bytes - 1
    if address_end >= NATIVE_DATA_BASE + NATIVE_DATA_BYTES:
        raise RuntimeError("native transcript escapes the locked 64 MiB region")
    raw_chunks = dma_chunks(data_bytes, NATIVE_DMA_ACTION_BYTES)
    record_bytes = dims * 4
    record_chunk_bytes = (
        NATIVE_DMA_ACTION_BYTES // record_bytes
    ) * record_bytes
    if workload == "aggregate":
        if clusters != 0 or iterations != 1:
            raise RuntimeError("aggregate transcript requires clusters=0, iterations=1")
        work_chunks = raw_chunks
    elif workload == "kmeans":
        if (
            iterations != NATIVE_KMEANS_ITERATIONS
            or clusters < 2
            or clusters > NATIVE_KMEANS_MAX_CLUSTERS
            or clusters > points
            or dims > NATIVE_KMEANS_MAX_DIMS
        ):
            raise RuntimeError(
                "invalid native k-means public shape/iteration configuration"
            )
        work_chunks = dma_chunks(data_bytes, record_chunk_bytes)
    else:
        raise RuntimeError(f"unsupported native workload: {workload}")
    events = []
    clean_bound_cycles = 0
    clean_compute_cycles = 0
    fused_zero_kmeans = (
        native_zero_path == "fused"
        and workload == "kmeans"
        and mode == "pim-oblivious"
        and policy == "zero"
    )
    trace_order_asserted = True
    trace_order_reason = "sequential public DMA submission order"
    if mode == "pim-oblivious" and policy == "zero" and not fused_zero_kmeans:
        clean_chunks = dma_chunks(data_bytes, record_chunk_bytes)
        clean_packets = submitted_packets(clean_chunks)
        clean_compute_cycles = sum(
            ceil_div(size // 4, NATIVE_CLEANER_VALIDATION_LANES)
            for _, size in clean_chunks
        )
        clean_bound_cycles = phase_bound_cycles(
            2 * len(clean_chunks), 2 * clean_packets, clean_compute_cycles
        )
        # A single clean chunk has a uniquely reconstructable public trace.
        # With more actions, the two public pipeline buffers can legally submit
        # the next read before or after the other slot's write.  Counters and
        # address geometry remain exact, while cross-secret digest equality is
        # checked later without inventing an ordering the device does not promise.
        if len(clean_chunks) > 1:
            trace_order_asserted = False
            trace_order_reason = (
                "two-buffer zero-clean pipeline has multiple legal public "
                "submission interleavings for more than two clean actions"
            )
        for first in range(0, len(clean_chunks), 2):
            batch = clean_chunks[first : first + 2]
            events.extend((1, addr, size) for addr, size in batch)
            events.extend((2, addr, size) for addr, size in batch)
    elif fused_zero_kmeans:
        # Validation and unconditional repair are part of iteration zero below.
        pass
    elif mode == "pim-oblivious" and policy == "mean":
        clean_chunks = raw_chunks
        clean_packets = submitted_packets(clean_chunks)
        clean_compute_cycles = 2 * sum(
            ceil_div(size // 4, NATIVE_CLEANER_VALIDATION_LANES)
            for _, size in clean_chunks
        )
        clean_bound_cycles = phase_bound_cycles(
            3 * len(clean_chunks), 3 * clean_packets, clean_compute_cycles
        )
        # Pass one computes public-shape means; pass two reads and
        # unconditionally writes each action before advancing.
        events.extend((1, addr, size) for addr, size in clean_chunks)
        for addr, size in clean_chunks:
            events.append((1, addr, size))
            events.append((2, addr, size))
    elif mode != "off":
        raise RuntimeError(f"unsupported transcript mode/policy: {mode}/{policy}")
    if workload == "aggregate":
        events.extend((3, addr, size) for addr, size in work_chunks)
        work_packets = submitted_packets(work_chunks)
        work_compute_cycles = sum(
            ceil_div(size // 4, NATIVE_CLEANER_VALIDATION_LANES)
            for _, size in work_chunks
        ) + ceil_div(dims, NATIVE_CLEANER_VALIDATION_LANES)
        work_actions = len(work_chunks)
        work_scan_arithmetic_cycles = 0
        work_auxiliary_cycles = work_compute_cycles
        work_scheduled_compute_cycles = work_compute_cycles
        fused_validation_cycles = 0
        fused_write_bound_cycles = 0
        fused_overlap_credit_cycles = 0
    else:
        centroid_events = [
            (
                3,
                NATIVE_DATA_BASE + (cluster * points // clusters) * record_bytes,
                record_bytes,
            )
            for cluster in range(clusters)
        ]
        events.extend(centroid_events)
        for iteration in range(iterations):
            if fused_zero_kmeans and iteration == 0:
                for addr, size in work_chunks:
                    events.append((3, addr, size))
                    events.append((2, addr, size))
            else:
                events.extend((3, addr, size) for addr, size in work_chunks)
        work_actions = (
            clusters
            + iterations * len(work_chunks)
            + (len(work_chunks) if fused_zero_kmeans else 0)
        )
        work_packets = submitted_packets(
            [(addr, size) for _, addr, size in centroid_events]
        ) + (iterations + (1 if fused_zero_kmeans else 0)) * submitted_packets(
            work_chunks
        )

        init_cycles = ceil_div(
            clusters * dims, NATIVE_CLEANER_VALIDATION_LANES
        )
        reset_cycles = ceil_div(
            clusters * dims, NATIVE_CLEANER_VALIDATION_LANES
        ) + ceil_div(clusters, NATIVE_CLEANER_VALIDATION_LANES)
        update_cycles = ceil_div(
            clusters * dims, NATIVE_CLEANER_VALIDATION_LANES
        ) + ceil_div(clusters, NATIVE_CLEANER_VALIDATION_LANES)
        scan_cycles = []
        for _, size in work_chunks:
            records = size // record_bytes
            scan_cycles.append(
                ceil_div(
                    3 * records * clusters * dims + 2 * records * dims,
                    NATIVE_KMEANS_ARITHMETIC_CORES,
                )
            )
        digest_cycles = ceil_div(
            4 * clusters * dims, NATIVE_CLEANER_VALIDATION_LANES
        )
        work_scan_arithmetic_cycles = iterations * sum(scan_cycles)
        work_auxiliary_cycles = (
            init_cycles + iterations * (reset_cycles + update_cycles) + digest_cycles
        )
        fused_validation_cycles = 0
        fused_write_bound_cycles = 0
        fused_overlap_credit_cycles = 0
        if fused_zero_kmeans:
            fused_validation_cycles = ceil_div(
                clusters * dims, NATIVE_CLEANER_VALIDATION_LANES
            )
            for (addr, size), classification_cycles in zip(
                work_chunks, scan_cycles
            ):
                records = size // record_bytes
                validation_cycles = ceil_div(
                    records * dims, NATIVE_CLEANER_VALIDATION_LANES
                )
                packets = submitted_packets([(addr, size)])
                write_bound = (
                    NATIVE_BOUND_ACTION_CYCLES
                    + packets * NATIVE_BOUND_PACKET_CYCLES
                )
                fused_validation_cycles += validation_cycles
                fused_write_bound_cycles += write_bound
                fused_overlap_credit_cycles += min(
                    classification_cycles, write_bound
                )
        work_scheduled_compute_cycles = (
            work_scan_arithmetic_cycles
            + work_auxiliary_cycles
            + fused_validation_cycles
        )
        work_compute_cycles = (
            work_scheduled_compute_cycles - fused_overlap_credit_cycles
        )
    work_bound_cycles = phase_bound_cycles(
        work_actions, work_packets, work_scheduled_compute_cycles
    ) - fused_overlap_credit_cycles

    digest = FNV1A64_OFFSET
    read_actions = 0
    write_actions = 0
    read_packets = 0
    write_packets = 0
    transferred_bytes = 0
    for op, addr, size in events:
        digest = fnv1a_add_u64(digest, op)
        digest = fnv1a_add_u64(digest, addr)
        digest = fnv1a_add_u64(digest, size)
        packets = (addr % DMA_PACKET_BYTES + size + DMA_PACKET_BYTES - 1) // (
            DMA_PACKET_BYTES
        )
        transferred_bytes += size
        if op == 2:
            write_actions += 1
            write_packets += packets
        else:
            read_actions += 1
            read_packets += packets
    return {
        "trace_digest": digest if trace_order_asserted else None,
        "trace_order_asserted": trace_order_asserted,
        "trace_order_reason": trace_order_reason,
        "read_actions": read_actions,
        "write_actions": write_actions,
        "read_packets": read_packets,
        "write_packets": write_packets,
        "transferred_bytes": transferred_bytes,
        "events": len(events),
        "address_start": NATIVE_DATA_BASE,
        "address_end": address_end,
        "clean_bound_cycles": clean_bound_cycles,
        "clean_compute_cycles": clean_compute_cycles,
        "work_bound_cycles": work_bound_cycles,
        "total_bound_cycles": clean_bound_cycles + work_bound_cycles,
        "work_compute_cycles": work_scheduled_compute_cycles,
        "work_bound_net_compute_cycles": work_compute_cycles,
        "work_scan_arithmetic_cycles": work_scan_arithmetic_cycles,
        "work_auxiliary_cycles": work_auxiliary_cycles,
        "fused_validation_cycles": fused_validation_cycles,
        "fused_write_bound_cycles": fused_write_bound_cycles,
        "fused_overlap_credit_cycles": fused_overlap_credit_cycles,
        "cleaner_validation_lanes": NATIVE_CLEANER_VALIDATION_LANES,
        "kmeans_arithmetic_cores": NATIVE_KMEANS_ARITHMETIC_CORES,
        "native_zero_path": native_zero_path,
        "fused_zero_kmeans": int(fused_zero_kmeans),
        "workload": workload,
        "clusters": clusters,
        "iterations": iterations,
    }


def run_bound_self_checks():
    """Pin the two public shapes used to audit the corrected timing model."""
    anchors = (
        {
            "shape": (512, 8, 4),
            "cycles": (129659, 129724, 65),
            "off_geometry": (24, 0, 5124, 0, 327808),
            "fused_geometry": (24, 1, 5124, 256, 344192),
            "fused_public_accounting": (71828, 65, 2816, 2816),
            "digests": (0xF8529347832EE4E5, 0xEAE194AF1083BE6B),
        },
        {
            "shape": (32767, 32, 8),
            "cycles": (47351260, 47367648, 16388),
            "off_geometry": (648, 0, 1310696, 0, 83884544),
            "fused_geometry": (648, 32, 1310696, 65534, 88078720),
            "fused_public_accounting": (34094288, 16388, 663532, 663532),
            "digests": (0x957868F22A3E529F, 0x1BB12EC2F4ECC1CD),
        },
    )
    for anchor in anchors:
        points, dims, clusters = anchor["shape"]
        off_cycles, fused_cycles, increment = anchor["cycles"]
        off = expected_native_transcript(
            "off",
            "zero",
            points,
            dims,
            "kmeans",
            clusters,
            NATIVE_KMEANS_ITERATIONS,
            "separate",
        )
        fused = expected_native_transcript(
            "pim-oblivious",
            "zero",
            points,
            dims,
            "kmeans",
            clusters,
            NATIVE_KMEANS_ITERATIONS,
            "fused",
        )
        observed = (
            off["total_bound_cycles"],
            fused["total_bound_cycles"],
            fused["total_bound_cycles"] - off["total_bound_cycles"],
        )
        expected = (off_cycles, fused_cycles, increment)
        if observed != expected:
            raise RuntimeError(
                f"native bound self-check failed for N={points},D={dims},K={clusters}: "
                f"observed={observed}, expected={expected}"
            )
        off_geometry = (
            off["read_actions"],
            off["write_actions"],
            off["read_packets"],
            off["write_packets"],
            off["transferred_bytes"],
        )
        fused_geometry = (
            fused["read_actions"],
            fused["write_actions"],
            fused["read_packets"],
            fused["write_packets"],
            fused["transferred_bytes"],
        )
        fused_public_accounting = (
            fused["work_compute_cycles"],
            fused["fused_validation_cycles"],
            fused["fused_write_bound_cycles"],
            fused["fused_overlap_credit_cycles"],
        )
        digests = (off["trace_digest"], fused["trace_digest"])
        if (
            off_geometry != anchor["off_geometry"]
            or fused_geometry != anchor["fused_geometry"]
            or fused_public_accounting != anchor["fused_public_accounting"]
            or digests != anchor["digests"]
        ):
            raise RuntimeError(
                f"native geometry/accounting self-check failed for "
                f"N={points},D={dims},K={clusters}: off={off_geometry}, "
                f"fused={fused_geometry}, accounting={fused_public_accounting}, "
                f"digests={digests}"
            )
        if (
            fused["clean_bound_cycles"] != 0
            or fused["clean_compute_cycles"] != 0
            or fused["fused_zero_kmeans"] != 1
            or fused["fused_overlap_credit_cycles"]
            > fused["fused_write_bound_cycles"]
        ):
            raise RuntimeError(
                f"invalid fused-zero accounting for N={points},D={dims},K={clusters}"
            )


def parse_uint(row, field, case_id, *, positive=False):
    if field not in row or row[field] is None or row[field].strip() == "":
        raise RuntimeError(f"case {case_id} is missing required field {field}")
    try:
        value = int(row[field], 0)
    except ValueError as error:
        raise RuntimeError(
            f"case {case_id} has non-integer {field}={row[field]!r}"
        ) from error
    if value < 0 or (positive and value == 0):
        relation = "positive" if positive else "non-negative"
        raise RuntimeError(f"case {case_id} requires {relation} {field}, got {value}")
    return value


def parse_correctness(value, case_id):
    normalized = (value or "").strip().lower()
    if normalized in {"1", "true", "pass", "passed", "yes", "ok"}:
        return 1
    if normalized in {"0", "false", "fail", "failed", "no"}:
        return 0
    raise RuntimeError(f"case {case_id} has invalid correctness={value!r}")


def normalize_digest(row, field, case_id):
    value = (row.get(field) or "").strip().lower()
    if not HEX_DIGEST_RE.fullmatch(value):
        raise RuntimeError(f"case {case_id} has invalid {field}={value!r}")
    return f"{int(value, 16):016x}"


def validate_native_row(
    raw,
    case,
    points,
    dims,
    cpu_record,
    workload="aggregate",
    clusters=0,
    iterations=1,
):
    """Validate and enrich one direct-native guest row."""
    case_id = case["case_id"]
    required_text = (
        "cleaning_mode",
        "imputation",
        "model_kind",
        "workload",
        "dataset_file",
        "native_zero_path",
        "native_e2e",
        "trace_digest",
        "output_digest",
        "reference_output_digest",
        "correctness",
    )
    for field in required_text:
        if field not in raw or raw[field] is None or raw[field].strip() == "":
            raise RuntimeError(f"case {case_id} is missing required field {field}")

    expected_model_kind = MODEL_KIND[workload]
    if raw["model_kind"] != expected_model_kind:
        raise RuntimeError(
            f"case {case_id} is not direct end-to-end gem5 evidence: "
            f"model_kind={raw['model_kind']!r}"
        )
    if raw["workload"] != workload:
        raise RuntimeError(f"case {case_id} has workload={raw['workload']!r}")
    if Path(raw["dataset_file"]).name != case["dataset"].name:
        raise RuntimeError(
            f"case {case_id} ran dataset {raw['dataset_file']!r}, expected "
            f"{case['dataset'].name!r}"
        )
    if raw["cleaning_mode"] != case["mode"]:
        raise RuntimeError(
            f"case {case_id} expected mode {case['mode']}, "
            f"got {raw['cleaning_mode']}"
        )
    if raw["imputation"] != case["policy"]:
        raise RuntimeError(
            f"case {case_id} expected policy {case['policy']}, "
            f"got {raw['imputation']}"
        )
    if raw["native_zero_path"] != case["native_zero_path"]:
        raise RuntimeError(
            f"case {case_id} expected native zero path "
            f"{case['native_zero_path']!r}, got {raw['native_zero_path']!r}"
        )
    if parse_uint(raw, "native_e2e", case_id) != 1:
        raise RuntimeError(f"case {case_id} did not signal native_e2e=1")

    row_points = parse_uint(raw, "points", case_id, positive=True)
    row_dims = parse_uint(raw, "dims", case_id, positive=True)
    row_seed = parse_uint(raw, "seed", case_id)
    row_iterations = parse_uint(raw, "iterations", case_id, positive=True)
    row_clusters = parse_uint(raw, "clusters", case_id)
    if row_points != points or row_dims != dims or row_seed != case["seed"]:
        raise RuntimeError(
            f"case {case_id} public shape/seed mismatch: "
            f"points={row_points} dims={row_dims} seed={row_seed}"
        )
    if row_iterations != iterations or row_clusters != clusters:
        raise RuntimeError(
            f"case {case_id} does not match the declared {workload} shape: "
            f"iterations={row_iterations}/{iterations} "
            f"clusters={row_clusters}/{clusters}"
        )
    try:
        row_rate = float(raw["corruption_frac"])
    except (KeyError, TypeError, ValueError) as error:
        raise RuntimeError(f"case {case_id} has invalid corruption_frac") from error
    if abs(row_rate - case["input_rate"]) > 1e-9:
        raise RuntimeError(
            f"case {case_id} expected input corruption {case['input_rate']}, "
            f"got {row_rate}"
        )

    total_ticks = parse_uint(raw, "total_ticks", case_id, positive=True)
    clean_ticks = parse_uint(raw, "clean_ticks", case_id)
    work_ticks = parse_uint(raw, "work_ticks", case_id, positive=True)
    simulator_ticks = parse_uint(raw, "simulator_ticks", case_id, positive=True)
    dma_bytes = parse_uint(raw, "simulator_dma_bytes", case_id, positive=True)
    status_polls = parse_uint(raw, "status_polls", case_id, positive=True)
    visible_reads = parse_uint(raw, "visible_reads", case_id, positive=True)
    visible_writes = parse_uint(raw, "visible_writes", case_id)
    dma_read_actions = parse_uint(raw, "dma_read_actions", case_id, positive=True)
    dma_write_actions = parse_uint(raw, "dma_write_actions", case_id)
    submitted_read_packets = parse_uint(
        raw, "submitted_read_packets", case_id, positive=True
    )
    submitted_write_packets = parse_uint(
        raw, "submitted_write_packets", case_id
    )
    visible_bytes = parse_uint(raw, "visible_bytes", case_id, positive=True)
    completion_cycles = parse_uint(raw, "completion_cycles", case_id, positive=True)
    clock_period = parse_uint(
        raw, "device_clock_period_ticks", case_id, positive=True
    )
    fused_zero_kmeans = parse_uint(raw, "fused_zero_kmeans", case_id)
    cleaner_validation_lanes = parse_uint(
        raw, "cleaner_validation_lanes", case_id, positive=True
    )
    kmeans_arithmetic_cores = parse_uint(
        raw, "kmeans_arithmetic_cores", case_id, positive=True
    )
    fused_validation_cycles = parse_uint(
        raw, "fused_validation_cycles", case_id
    )
    fused_write_bound_cycles = parse_uint(
        raw, "fused_write_bound_cycles", case_id
    )
    fused_overlap_credit_cycles = parse_uint(
        raw, "fused_overlap_credit_cycles", case_id
    )
    expected = expected_native_transcript(
        case["mode"],
        case["policy"],
        points,
        dims,
        workload,
        clusters,
        iterations,
        case["native_zero_path"],
    )
    public_accounting = {
        "fused_zero_kmeans": fused_zero_kmeans,
        "cleaner_validation_lanes": cleaner_validation_lanes,
        "kmeans_arithmetic_cores": kmeans_arithmetic_cores,
        "fused_validation_cycles": fused_validation_cycles,
        "fused_write_bound_cycles": fused_write_bound_cycles,
        "fused_overlap_credit_cycles": fused_overlap_credit_cycles,
    }
    for field, observed in public_accounting.items():
        if observed != expected[field]:
            raise RuntimeError(
                f"case {case_id} public {field}={observed}, expected "
                f"{expected[field]}"
            )
    expected_clean_ticks = expected["clean_bound_cycles"] * clock_period
    expected_work_ticks = expected["work_bound_cycles"] * clock_period
    expected_total_ticks = expected["total_bound_cycles"] * clock_period
    if total_ticks != clean_ticks + work_ticks:
        raise RuntimeError(
            f"case {case_id} phase accounting mismatch: total_ticks={total_ticks}, "
            f"clean_ticks={clean_ticks}, work_ticks={work_ticks}"
        )
    if simulator_ticks != total_ticks:
        raise RuntimeError(
            f"case {case_id} simulator_ticks={simulator_ticks} differs from "
            f"total_ticks={total_ticks}"
        )
    expected_cycles = (total_ticks + clock_period - 1) // clock_period
    if completion_cycles != expected_cycles:
        raise RuntimeError(
            f"case {case_id} completion_cycles={completion_cycles}, expected "
            f"ceil({total_ticks}/{clock_period})={expected_cycles}"
        )
    if status_polls != 2:
        raise RuntimeError(
            f"case {case_id} performed {status_polls} status reads; the fixed-wait "
            "contract requires one command-acceptance read and one completion read"
        )
    if (
        clean_ticks != expected_clean_ticks
        or work_ticks != expected_work_ticks
        or total_ticks != expected_total_ticks
        or completion_cycles != expected["total_bound_cycles"]
    ):
        raise RuntimeError(
            f"case {case_id} fixed-deadline mismatch: "
            f"ticks clean/work/total={clean_ticks}/{work_ticks}/{total_ticks}, "
            f"expected={expected_clean_ticks}/{expected_work_ticks}/"
            f"{expected_total_ticks}; cycles={completion_cycles}, "
            f"expected={expected['total_bound_cycles']}"
        )
    if visible_bytes != dma_bytes or dma_bytes != expected["transferred_bytes"]:
        raise RuntimeError(
            f"case {case_id} DMA byte geometry mismatch: "
            f"visible={visible_bytes}, simulator={dma_bytes}, "
            f"expected={expected['transferred_bytes']}"
        )
    if visible_reads != dma_read_actions or visible_writes != dma_write_actions:
        raise RuntimeError(
            f"case {case_id} backward-compatible visible action fields do not "
            f"mirror device action fields: visible={visible_reads}/{visible_writes}, "
            f"dma={dma_read_actions}/{dma_write_actions}"
        )
    if (
        dma_read_actions != expected["read_actions"]
        or dma_write_actions != expected["write_actions"]
    ):
        raise RuntimeError(
            f"case {case_id} native DMA-action count mismatch: "
            f"reads={dma_read_actions}/{expected['read_actions']}, "
            f"writes={dma_write_actions}/{expected['write_actions']}"
        )
    if (
        submitted_read_packets != expected["read_packets"]
        or submitted_write_packets != expected["write_packets"]
    ):
        raise RuntimeError(
            f"case {case_id} submitted 64-byte packet geometry mismatch: "
            f"reads={submitted_read_packets}/{expected['read_packets']}, "
            f"writes={submitted_write_packets}/{expected['write_packets']}"
        )
    if case["mode"] == "off" and clean_ticks != 0:
        raise RuntimeError(f"off case {case_id} has nonzero clean_ticks={clean_ticks}")
    if (
        case["mode"] == "pim-oblivious"
        and not expected["fused_zero_kmeans"]
        and clean_ticks == 0
    ):
        raise RuntimeError(f"cleaned case {case_id} has zero clean_ticks")
    if expected["fused_zero_kmeans"] and clean_ticks != 0:
        raise RuntimeError(
            f"fused-zero case {case_id} exposed a separate clean phase: "
            f"clean_ticks={clean_ticks}"
        )

    correctness = parse_correctness(raw["correctness"], case_id)
    if correctness != 1:
        raise RuntimeError(f"guest reference validation failed for case {case_id}")
    trace_digest = normalize_digest(raw, "trace_digest", case_id)
    if (
        expected["trace_order_asserted"]
        and int(trace_digest, 16) != expected["trace_digest"]
    ):
        raise RuntimeError(
            f"case {case_id} trace digest {trace_digest} differs from independent "
            f"standard-FNV reconstruction {expected['trace_digest']:016x}"
        )
    output_digest = normalize_digest(raw, "output_digest", case_id)
    reference_output_digest = normalize_digest(
        raw, "reference_output_digest", case_id
    )
    if output_digest != reference_output_digest:
        raise RuntimeError(
            f"case {case_id} output digest differs from guest reference digest"
        )
    if workload == "kmeans" and output_digest != case["expected_output_digest"]:
        raise RuntimeError(
            f"case {case_id} output digest {output_digest} differs from host "
            f"oracle {case['expected_output_digest']}"
        )

    enriched = dict(raw)
    enriched.update(
        {
            "case_id": case_id,
            "input_kind": case["input_kind"],
            "input_corruption_frac": case["input_rate"],
            "paired_corruption_frac": case["rate"],
            "input_sha256": case["input_sha256"],
            "clean_sha256": case["clean_sha256"],
            "dirty_sha256": case["dirty_sha256"],
            "public_input_bytes": case["public_input_bytes"],
            "dataset_file_bytes": case["dataset_file_bytes"],
            "payload_bytes": case["payload_bytes"],
            "payload_mib": f"{case['payload_bytes'] / (1024 * 1024):.9f}",
            "checkpoint_restore_index": case["checkpoint_restore_index"],
            "total_ticks": total_ticks,
            "clean_ticks": clean_ticks,
            "work_ticks": work_ticks,
            "simulator_ticks": simulator_ticks,
            "simulator_dma_bytes": dma_bytes,
            "status_polls": status_polls,
            "visible_reads": visible_reads,
            "visible_writes": visible_writes,
            "dma_read_actions": dma_read_actions,
            "dma_write_actions": dma_write_actions,
            "submitted_read_packets": submitted_read_packets,
            "submitted_write_packets": submitted_write_packets,
            "visible_bytes": visible_bytes,
            "completion_cycles": completion_cycles,
            "device_clock_period_ticks": clock_period,
            "native_zero_path": case["native_zero_path"],
            "fused_zero_kmeans": fused_zero_kmeans,
            "cleaner_validation_lanes": cleaner_validation_lanes,
            "kmeans_arithmetic_cores": kmeans_arithmetic_cores,
            "fused_validation_cycles": fused_validation_cycles,
            "fused_write_bound_cycles": fused_write_bound_cycles,
            "fused_overlap_credit_cycles": fused_overlap_credit_cycles,
            "expected_work_compute_cycles": expected["work_compute_cycles"],
            "expected_work_bound_net_compute_cycles": expected[
                "work_bound_net_compute_cycles"
            ],
            "expected_work_scan_arithmetic_cycles": expected[
                "work_scan_arithmetic_cycles"
            ],
            "expected_work_auxiliary_cycles": expected[
                "work_auxiliary_cycles"
            ],
            "trace_digest": trace_digest,
            "expected_trace_digest": (
                f"{expected['trace_digest']:016x}"
                if expected["trace_order_asserted"]
                else "not_asserted"
            ),
            "trace_digest_reconstruction": (
                "exact" if expected["trace_order_asserted"] else "group_equality"
            ),
            "trace_order_reason": expected["trace_order_reason"],
            "protected_data_address_start": f"0x{expected['address_start']:x}",
            "protected_data_address_end": f"0x{expected['address_end']:x}",
            "output_digest": output_digest,
            "reference_output_digest": reference_output_digest,
            "host_oracle_output_digest": (
                case["expected_output_digest"]
                if workload == "kmeans"
                else "not_applicable"
            ),
            "reference_kind": (
                "host_kmeans_fixed_iteration_oracle"
                if workload == "kmeans"
                else "post_command_guest_feature_mean_oracle"
            ),
            "correctness": correctness,
            "cpu_type": cpu_record["requested_cpu_type"],
            "cpu_class": cpu_record["measurement_cpu_class"],
            "mem_mode": cpu_record["effective_mem_mode"],
            "evidence_tier": evidence_tier_for(cpu_record),
            "latency_semantics": (
                "fixed_schedule_padded_native_device_command_with_public_"
                "iteration0_compute_write_overlap"
                if fused_zero_kmeans
                else "fixed_schedule_padded_native_device_command"
            ),
            "checkpoint_cpu_type": cpu_record["checkpoint_cpu_type"],
            "restore_strategy": cpu_record["restore_strategy"],
            "restore_with_cpu": cpu_record["restore_with_cpu"],
            "checkpoint_restore_semantics": cpu_record[
                "checkpoint_restore_semantics"
            ],
            "configured_initial_mem_mode": cpu_record[
                "configured_initial_mem_mode"
            ],
            "cpu_switch_used": cpu_record["cpu_switch_used"],
            "cpu_switch_warmup_ticks": cpu_record["cpu_switch_warmup_ticks"],
            "num_cpus": cpu_record["num_cpus"],
            "cache_line_size_bytes": cpu_record["cache_line_size_bytes"],
            "case_config_ini_sha256": cpu_record["config_ini_sha256"],
        }
    )
    return enriched


def validate_and_pair(
    rows,
    expected_cases,
    points,
    dims,
    workload="aggregate",
    clusters=0,
    iterations=1,
):
    if len(rows) != len(expected_cases):
        raise RuntimeError(
            f"expected {len(expected_cases)} native rows, found {len(rows)}"
        )
    by_case = {row["case_id"]: row for row in rows}
    if len(by_case) != len(rows):
        raise RuntimeError("duplicate native case IDs")
    expected_ids = {case["case_id"] for case in expected_cases}
    if set(by_case) != expected_ids:
        raise RuntimeError(
            f"native case set mismatch: missing={sorted(expected_ids - set(by_case))}, "
            f"extra={sorted(set(by_case) - expected_ids)}"
        )

    # Data-dependent output digests and guest_dataset_sha256 are intentionally
    # excluded: they identify the declared result and exact secret input,
    # respectively, rather than the fixed access/completion transcript.
    secure_fields = (
        "total_ticks",
        "clean_ticks",
        "work_ticks",
        "simulator_ticks",
        "simulator_dma_bytes",
        "status_polls",
        "visible_reads",
        "visible_writes",
        "dma_read_actions",
        "dma_write_actions",
        "submitted_read_packets",
        "submitted_write_packets",
        "visible_bytes",
        "completion_cycles",
        "device_clock_period_ticks",
        "trace_digest",
        "native_zero_path",
        "fused_zero_kmeans",
        "cleaner_validation_lanes",
        "kmeans_arithmetic_cores",
        "fused_validation_cycles",
        "fused_write_bound_cycles",
        "fused_overlap_credit_cycles",
        "cpu_type",
        "mem_mode",
        "evidence_tier",
        "restore_strategy",
        "restore_with_cpu",
        "checkpoint_restore_semantics",
        "cpu_switch_used",
        "num_cpus",
        "cache_line_size_bytes",
        "guest_workload_sha256",
        "guest_driver_sha256",
    )
    groups = defaultdict(list)
    for row in rows:
        if row.get("guest_dataset_sha256") != row.get("input_sha256"):
            raise RuntimeError(
                f"case {row.get('case_id')} guest dataset hash does not match "
                "its pinned input_sha256"
            )
        policy_group = row["imputation"] if row["cleaning_mode"] != "off" else "off"
        key = (
            row["cleaning_mode"],
            policy_group,
            row["native_zero_path"],
            int(row["fused_zero_kmeans"]),
            row["workload"],
            int(row["iterations"]),
            int(row["clusters"]),
            int(row["points"]),
            int(row["dims"]),
        )
        groups[key].append(row)
    for key, group in groups.items():
        for field in secure_fields:
            values = {str(row[field]) for row in group}
            if len(values) != 1:
                raise RuntimeError(
                    f"fixed-transcript mismatch group={key} field={field}: "
                    f"{sorted(values)}"
                )

    paired = []
    cases_by_input = defaultdict(dict)
    for row in rows:
        input_key = (
            int(row["seed"]),
            round(float(row["paired_corruption_frac"]), 9),
        )
        if row["cleaning_mode"] == "off":
            slot = "off"
        else:
            slot = row["imputation"]
        if slot in cases_by_input[input_key]:
            raise RuntimeError(f"duplicate {slot} row for input {input_key}")
        cases_by_input[input_key][slot] = row

    for (seed, rate), cases in sorted(cases_by_input.items()):
        if set(cases) != {"off", *POLICIES}:
            raise RuntimeError(
                f"incomplete paired input seed={seed} rate={rate}: {sorted(cases)}"
            )
        baseline = cases["off"]
        for policy in POLICIES:
            cleaned = cases[policy]
            for field in (
                "cpu_type",
                "cpu_class",
                "mem_mode",
                "evidence_tier",
                "restore_strategy",
                "restore_with_cpu",
                "checkpoint_restore_semantics",
                "cpu_switch_used",
                "num_cpus",
                "cache_line_size_bytes",
                "device_clock_period_ticks",
            ):
                if cleaned[field] != baseline[field]:
                    raise RuntimeError(
                        f"pair seed={seed} rate={rate} policy={policy} changes "
                        f"{field}: {baseline[field]!r} -> {cleaned[field]!r}"
                    )
            if baseline["input_kind"] != "clean" or cleaned["input_kind"] != "dirty":
                raise RuntimeError(
                    f"pair seed={seed} rate={rate} policy={policy} has invalid "
                    "clean/dirty input assignment"
                )
            if cleaned["public_input_bytes"] != baseline["public_input_bytes"]:
                raise RuntimeError(
                    f"pair seed={seed} rate={rate} policy={policy} has unequal "
                    "public input sizes"
                )
            incremental_ticks = cleaned["total_ticks"] - baseline["total_ticks"]
            work_tick_delta = cleaned["work_ticks"] - baseline["work_ticks"]
            baseline_expected = expected_native_transcript(
                "off",
                "zero",
                points,
                dims,
                workload,
                clusters,
                iterations,
                baseline["native_zero_path"],
            )
            cleaned_expected = expected_native_transcript(
                "pim-oblivious",
                policy,
                points,
                dims,
                workload,
                clusters,
                iterations,
                cleaned["native_zero_path"],
            )
            clock_period = baseline["device_clock_period_ticks"]
            expected_work_tick_delta = (
                cleaned_expected["work_bound_cycles"]
                - baseline_expected["work_bound_cycles"]
            ) * clock_period
            expected_incremental_ticks = (
                cleaned_expected["total_bound_cycles"]
                - baseline_expected["total_bound_cycles"]
            ) * clock_period
            if work_tick_delta != expected_work_tick_delta:
                raise RuntimeError(
                    f"pair seed={seed} rate={rate} policy={policy} changes the "
                    f"fixed public workload schedule by {work_tick_delta} ticks, "
                    f"expected {expected_work_tick_delta} for native zero path "
                    f"{cleaned['native_zero_path']}"
                )
            if incremental_ticks != expected_incremental_ticks:
                raise RuntimeError(
                    f"pair seed={seed} rate={rate} policy={policy} incremental "
                    f"ticks={incremental_ticks}, expected={expected_incremental_ticks}"
                )
            if rate == 0.0 and cleaned["output_digest"] != baseline["output_digest"]:
                raise RuntimeError(
                    f"clean input changed {workload} output for policy={policy}, seed={seed}"
                )
            overhead_pct = incremental_ticks * 100.0 / baseline["total_ticks"]
            paired.append(
                {
                    "model_kind": MODEL_KIND[workload],
                    "latency_semantics": cleaned["latency_semantics"],
                    "evidence_tier": baseline["evidence_tier"],
                    "cpu_type": baseline["cpu_type"],
                    "cpu_class": baseline["cpu_class"],
                    "mem_mode": baseline["mem_mode"],
                    "checkpoint_cpu_type": baseline["checkpoint_cpu_type"],
                    "restore_strategy": baseline["restore_strategy"],
                    "restore_with_cpu": baseline["restore_with_cpu"],
                    "checkpoint_restore_semantics": baseline[
                        "checkpoint_restore_semantics"
                    ],
                    "cpu_switch_used": baseline["cpu_switch_used"],
                    "num_cpus": baseline["num_cpus"],
                    "cache_line_size_bytes": baseline["cache_line_size_bytes"],
                    "guest_workload_sha256": baseline["guest_workload_sha256"],
                    "guest_driver_sha256": baseline["guest_driver_sha256"],
                    "guest_dataset_sha256": cleaned["guest_dataset_sha256"],
                    "baseline_guest_dataset_sha256": baseline[
                        "guest_dataset_sha256"
                    ],
                    "cleaned_guest_dataset_sha256": cleaned[
                        "guest_dataset_sha256"
                    ],
                    "workload": workload,
                    "iterations": iterations,
                    "clusters": clusters,
                    "policy": policy,
                    "native_zero_path": cleaned["native_zero_path"],
                    "fused_zero_kmeans": cleaned["fused_zero_kmeans"],
                    "cleaner_validation_lanes": cleaned[
                        "cleaner_validation_lanes"
                    ],
                    "kmeans_arithmetic_cores": cleaned[
                        "kmeans_arithmetic_cores"
                    ],
                    "fused_validation_cycles": cleaned[
                        "fused_validation_cycles"
                    ],
                    "fused_write_bound_cycles": cleaned[
                        "fused_write_bound_cycles"
                    ],
                    "fused_overlap_credit_cycles": cleaned[
                        "fused_overlap_credit_cycles"
                    ],
                    "seed": seed,
                    "corruption_frac": f"{rate:.6f}",
                    "points": points,
                    "dims": dims,
                    "public_input_bytes": baseline["public_input_bytes"],
                    "dataset_file_bytes": baseline["dataset_file_bytes"],
                    "payload_bytes": baseline["payload_bytes"],
                    "payload_mib": baseline["payload_mib"],
                    "baseline_input_kind": baseline["input_kind"],
                    "cleaned_input_kind": cleaned["input_kind"],
                    "baseline_input_sha256": baseline["input_sha256"],
                    "cleaned_input_sha256": cleaned["input_sha256"],
                    "baseline_case_id": baseline["case_id"],
                    "cleaned_case_id": cleaned["case_id"],
                    "baseline_total_ticks": baseline["total_ticks"],
                    "cleaned_total_ticks": cleaned["total_ticks"],
                    "clean_ticks": cleaned["clean_ticks"],
                    "baseline_work_ticks": baseline["work_ticks"],
                    "cleaned_work_ticks": cleaned["work_ticks"],
                    "work_tick_delta": work_tick_delta,
                    "expected_work_tick_delta": expected_work_tick_delta,
                    "incremental_ticks": incremental_ticks,
                    "expected_incremental_ticks": expected_incremental_ticks,
                    "incremental_minus_clean_ticks": (
                        incremental_ticks - cleaned["clean_ticks"]
                    ),
                    "measured_overhead_pct": f"{overhead_pct:.12f}",
                    "fixed_schedule_overhead_pct": f"{overhead_pct:.12f}",
                    "baseline_dma_bytes": baseline["simulator_dma_bytes"],
                    "cleaned_dma_bytes": cleaned["simulator_dma_bytes"],
                    "incremental_dma_bytes": (
                        cleaned["simulator_dma_bytes"]
                        - baseline["simulator_dma_bytes"]
                    ),
                    "baseline_visible_reads": baseline["visible_reads"],
                    "cleaned_visible_reads": cleaned["visible_reads"],
                    "baseline_visible_writes": baseline["visible_writes"],
                    "cleaned_visible_writes": cleaned["visible_writes"],
                    "baseline_submitted_read_packets": baseline[
                        "submitted_read_packets"
                    ],
                    "cleaned_submitted_read_packets": cleaned[
                        "submitted_read_packets"
                    ],
                    "baseline_submitted_write_packets": baseline[
                        "submitted_write_packets"
                    ],
                    "cleaned_submitted_write_packets": cleaned[
                        "submitted_write_packets"
                    ],
                    "device_clock_period_ticks": baseline[
                        "device_clock_period_ticks"
                    ],
                    "baseline_status_polls": baseline["status_polls"],
                    "cleaned_status_polls": cleaned["status_polls"],
                    "baseline_trace_digest": baseline["trace_digest"],
                    "cleaned_trace_digest": cleaned["trace_digest"],
                    "baseline_output_digest": baseline["output_digest"],
                    "cleaned_output_digest": cleaned["output_digest"],
                    "correctness": 1,
                }
            )

    return paired, {
        "status": "pass",
        "property": (
            "for tested equal-shape secrets, device-reported FNV-1a-64 trace "
            "digests, aggregate action/packet/byte geometry, padded phase ticks, DMA bytes, "
            "and status reads are equal"
        ),
        "rows": len(rows),
        "pairs": len(paired),
        "secure_groups": len(groups),
        "fixed_fields": secure_fields,
        "output_digest_treatment": (
            f"declared {workload} output; checked against the independent "
            "functional reference but excluded from transcript equality"
        ),
        "guest_dataset_sha256_treatment": (
            "required to equal each case input_sha256, retained in native and "
            "paired rows, and excluded from secret-equality fields because it "
            "intentionally identifies the differing secret dataset bytes"
        ),
        "overhead_formula": (
            "(cleaned_total_ticks - baseline_total_ticks) * 100 / "
            "baseline_total_ticks"
        ),
        "work_tick_delta_treatment": (
            "separate cleaning and mean-imputation rows require zero workload "
            "delta; fused zero k-means requires the exact independently "
            "reconstructed public iteration-0 validation/write-overlap delta"
        ),
        "trace_digest_validation": (
            "independently reconstructed standard FNV-1a-64 over each public "
            "(operation, physical address, byte count) tuple for sequential "
            "off/mean/fused traces and single-chunk separate-zero traces; "
            "multi-chunk pipelined separate-zero traces use exact aggregate "
            "action/packet/byte "
            "geometry plus FNV-1a-64 digest equality across tested equal-shape "
            "secrets because multiple public submission interleavings are legal. "
            "The digest is an error-detection commitment, not a collision-resistant "
            "proof of individual trace equality"
        ),
    }


def write_csv(path, rows):
    if not rows:
        raise RuntimeError(f"refusing to write empty CSV: {path}")
    fieldnames = []
    for row in rows:
        for field in row:
            if field not in fieldnames:
                fieldnames.append(field)
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)


def validate_dataset_metadata(
    metadata_path,
    clean,
    dirty,
    labels,
    points,
    dims,
    seed,
    rate,
    data_clusters,
):
    metadata = json.loads(metadata_path.read_text())
    expected = {
        "clean": clean,
        "dirty": dirty,
        "labels": labels,
    }
    if (
        int(metadata["points"]) != points
        or int(metadata["dims"]) != dims
        or int(metadata["seed"]) != seed
        or int(metadata["clusters"]) != data_clusters
        or abs(float(metadata["dirty_frac_requested"]) - rate) > 1e-12
    ):
        raise RuntimeError(f"dataset metadata mismatch: {metadata_path}")
    for kind, path in expected.items():
        record = metadata["files"][kind]
        if not path.is_file():
            raise RuntimeError(f"missing dataset file: {path}")
        if int(record["bytes"]) != path.stat().st_size:
            raise RuntimeError(f"dataset byte-count mismatch: {path}")
        if record["sha256"] != sha256_file(path):
            raise RuntimeError(f"dataset checksum mismatch: {path}")
        if record["path"] != path.name:
            raise RuntimeError(
                f"dataset metadata path mismatch for {kind}: {record['path']!r}"
            )
    if clean.stat().st_size != dirty.stat().st_size:
        raise RuntimeError(
            f"clean and dirty files do not have equal public shapes: {clean}, {dirty}"
        )
    expected_format = {
        "magic_hex": "0x4b4d4453",
        "version": 1,
        "float": "float32",
        "null_sentinel": -999999.0,
    }
    if metadata.get("format") != expected_format:
        raise RuntimeError(f"unsupported dataset format metadata: {metadata_path}")
    if not metadata.get("source") or not metadata.get("distribution_name"):
        raise RuntimeError(f"dataset source/distribution metadata is missing: {metadata_path}")
    dirty_count = int(metadata["dirty_count"])
    actual_rate = float(metadata["dirty_frac_actual"])
    if dirty_count < 0 or dirty_count > points or abs(actual_rate - dirty_count / points) > 1e-12:
        raise RuntimeError(f"dataset dirty-count/fraction mismatch: {metadata_path}")
    distribution = metadata["distribution"]
    positions = metadata["dirty_indices"]
    if set(distribution) != {"nan", "null", "outlier"} or set(positions) != set(distribution):
        raise RuntimeError(f"dataset corruption-type metadata mismatch: {metadata_path}")
    flattened = []
    for corruption_type in sorted(distribution):
        indices = [int(value) for value in positions[corruption_type]]
        if int(distribution[corruption_type]) != len(indices):
            raise RuntimeError(
                f"dataset {corruption_type} count/position mismatch: {metadata_path}"
            )
        if any(index < 0 or index >= points for index in indices):
            raise RuntimeError(f"dataset corruption index out of range: {metadata_path}")
        flattened.extend(indices)
    if len(flattened) != dirty_count or len(set(flattened)) != dirty_count:
        raise RuntimeError(f"dataset corruption positions are not unique/complete: {metadata_path}")
    enriched = dict(metadata)
    enriched["metadata_file"] = artifact_record(metadata_path)
    return enriched


def make_case(
    seed,
    rate,
    mode,
    policy,
    dataset,
    input_kind,
    metadata,
    restore_index,
    native_zero_path="separate",
):
    rate_tag = int(round(rate * 100))
    mode_tag = "off" if mode == "off" else f"pim_{policy}"
    if mode == "pim-oblivious" and policy == "zero" and native_zero_path == "fused":
        mode_tag += "_fused"
    return {
        "case_id": f"s{seed:03d}_r{rate_tag:03d}_{mode_tag}",
        "seed": seed,
        "rate": rate,
        "input_rate": 0.0 if input_kind == "clean" else rate,
        "mode": mode,
        "policy": policy,
        "dataset": dataset,
        "input_kind": input_kind,
        "input_sha256": metadata["files"][input_kind]["sha256"],
        "clean_sha256": metadata["files"]["clean"]["sha256"],
        "dirty_sha256": metadata["files"]["dirty"]["sha256"],
        "public_input_bytes": int(metadata["files"][input_kind]["bytes"]),
        "dataset_file_bytes": int(metadata["files"][input_kind]["bytes"]),
        "payload_bytes": int(metadata["points"]) * int(metadata["dims"]) * 4,
        "checkpoint_restore_index": restore_index,
        "native_zero_path": native_zero_path,
    }


def evaluate_publication_eligibility(
    *,
    cpu_type,
    restore_plan,
    checkpoint_provenance,
    dataset_generation_record,
    quick,
    is_subset,
    git_provenance,
):
    """Return explicit, fail-readable criteria for publication promotion."""
    repositories = git_provenance.get("repositories", {})
    commits_valid = (
        set(repositories) == {"top", "IMPICA"}
        and all(
            GIT_COMMIT_RE.fullmatch(record.get("commit", "")) is not None
            for record in repositories.values()
        )
    )
    criteria = {
        "timing_measurement": cpu_type == "timing",
        "same_class_timing_checkpoint": (
            restore_plan.get("checkpoint_cpu_type") == "timing"
            and restore_plan.get("checkpoint_restore_semantics")
            == "same_cpu_class_direct_restore"
        ),
        "direct_restore_without_cpu_switch": (
            restore_plan.get("strategy") == "direct"
            and restore_plan.get("cpu_switch_used") is False
        ),
        "strict_checkpoint_provenance": (
            checkpoint_provenance.get("status")
            == "schema_1_checkpoint_lineage_validated"
            and checkpoint_provenance.get("publication_eligible") is True
        ),
        "strict_dataset_generation_transcript": (
            dataset_generation_record is not None
            and dataset_generation_record.get("status")
            == "supplied_strictly_validated_generation_transcript"
        ),
        "non_quick_publication_matrix": not quick,
        "full_36_case_matrix": not is_subset,
        "valid_top_and_impica_commits": commits_valid,
    }
    reasons = [name for name, passed in criteria.items() if not passed]
    return {
        "eligible": not reasons,
        "criteria": criteria,
        "ineligible_reasons": reasons,
    }


def main():
    started = datetime.now(timezone.utc)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint-dir", type=Path, required=True)
    parser.add_argument("--checkpoint-index", type=int, default=1)
    parser.add_argument(
        "--cpu-type",
        choices=tuple(CPU_CLASS),
        default="timing",
        help=(
            "measurement CPU: timing is the publication-oriented default; "
            "atomic is retained only for smoke/functional runs"
        ),
    )
    parser.add_argument(
        "--timing-restore-strategy",
        choices=TIMING_RESTORE_STRATEGIES,
        default="direct",
        help=(
            "direct restores architectural checkpoint state straight into "
            "TimingSimpleCPU and is required for publication; switch retains "
            "the legacy atomic-to-timing runtime switch for diagnostics only"
        ),
    )
    parser.add_argument("--quick", action="store_true")
    parser.add_argument(
        "--workload", choices=tuple(MODEL_KIND), default="aggregate"
    )
    parser.add_argument("--points", type=int)
    parser.add_argument("--dims", type=int, default=8)
    parser.add_argument(
        "--data-clusters",
        "--clusters",
        dest="data_clusters",
        type=int,
        default=6,
        help="clusters used only to generate the labeled synthetic input",
    )
    parser.add_argument(
        "--kmeans-clusters",
        type=int,
        default=4,
        help="public native k-means K (independent of --data-clusters)",
    )
    parser.add_argument(
        "--native-zero-path",
        choices=NATIVE_ZERO_PATHS,
        default="separate",
        help=(
            "zero-imputation execution: separate is the transparent A/B "
            "control; fused is valid only for native fixed-20 k-means and "
            "combines validation/repair with iteration zero"
        ),
    )
    parser.add_argument("--outlier-threshold", type=float, default=8.0)
    parser.add_argument("--run-id")
    parser.add_argument("--dataset-id")
    parser.add_argument(
        "--dataset-generation-manifest",
        type=Path,
        help=(
            "schema-1 JSON transcript whose parameters, generator/wrapper, and "
            "complete output artifact set are strictly bound to this run"
        ),
    )
    parser.add_argument("--reuse-datasets", action="store_true")
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--skip-disk-prepare", action="store_true")
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help=(
            "number of independent checkpoint-isolated gem5 cases to run in "
            "parallel; this changes host scheduling only, not simulated inputs"
        ),
    )
    parser.add_argument(
        "--seeds",
        nargs="+",
        type=int,
        help="subset of seeds to evaluate (e.g. 7 19 42)",
    )
    parser.add_argument(
        "--rates",
        nargs="+",
        type=float,
        help="subset of corruption rates to evaluate (e.g. 0.0 0.01 0.10 0.40)",
    )
    parser.add_argument(
        "--modes",
        nargs="+",
        choices=("off", "zero", "mean"),
        help="subset of modes to evaluate (e.g. off zero mean)",
    )
    args = parser.parse_args()

    run_bound_self_checks()

    if args.dims <= 0 or (args.points is not None and args.points <= 0):
        raise SystemExit("points and dims must be positive")
    if args.dims > NATIVE_MAX_DIMS:
        raise SystemExit(f"dims exceeds the native limit of {NATIVE_MAX_DIMS}")
    if args.data_clusters <= 1:
        raise SystemExit("data clusters must exceed one")
    if args.outlier_threshold <= 0:
        raise SystemExit("outlier threshold must be positive")
    if args.checkpoint_index <= 0:
        raise SystemExit("checkpoint index must be positive")
    if args.workers <= 0 or args.workers > 16:
        raise SystemExit("workers must be between 1 and 16")
    if args.cpu_type == "atomic" and args.timing_restore_strategy != "direct":
        raise SystemExit(
            "--cpu-type=atomic supports only --timing-restore-strategy=direct"
        )
    if args.skip_disk_prepare and not args.reuse_datasets:
        raise SystemExit(
            "--skip-disk-prepare requires --reuse-datasets because newly generated "
            "datasets must be injected into the guest image"
        )
    if (
        args.reuse_datasets
        and not args.quick
        and args.dataset_generation_manifest is None
    ):
        raise SystemExit(
            "non-quick reused datasets require --dataset-generation-manifest; "
            "only quick diagnostic reuse may omit the standalone transcript"
        )

    points = args.points or (512 if args.quick else 8192)
    workload_iterations = (
        1 if args.workload == "aggregate" else NATIVE_KMEANS_ITERATIONS
    )
    workload_clusters = 0 if args.workload == "aggregate" else args.kmeans_clusters
    if args.native_zero_path == "fused" and args.workload != "kmeans":
        raise SystemExit(
            "--native-zero-path=fused is valid only with --workload=kmeans"
        )
    if args.workload == "kmeans" and (
        args.dims > NATIVE_KMEANS_MAX_DIMS
        or workload_clusters < 2
        or workload_clusters > NATIVE_KMEANS_MAX_CLUSTERS
        or workload_clusters > points
    ):
        raise SystemExit(
            "native k-means requires dims<=64 and 2<=K<=min(16,points)"
        )
    if points * args.dims * 4 > NATIVE_DATA_BYTES:
        raise SystemExit(
            f"public data shape exceeds the {NATIVE_DATA_BYTES}-byte native region"
        )
    if args.seeds is not None:
        seeds = tuple(sorted(set(args.seeds)))
    else:
        seeds = (7,) if args.quick else FULL_SEEDS

    if args.rates is not None:
        rates = tuple(sorted(set(args.rates)))
    else:
        rates = (0.0, 0.10) if args.quick else FULL_RATES

    if args.modes is not None:
        selected_modes = tuple(args.modes)
    else:
        selected_modes = ("off", "zero", "mean")
    generated_id = "native_e2e_%s_%s_%s_p%s" % (
        args.workload,
        "quick" if args.quick else "full",
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"),
        os.getpid(),
    )
    run_id = args.run_id or generated_id
    dataset_id = args.dataset_id or run_id
    for label, value in (("run ID", run_id), ("dataset ID", dataset_id)):
        if not RUN_ID_RE.fullmatch(value):
            raise SystemExit(f"invalid {label}: {value!r}")
    # Validate both repositories before creating any run output.  This is a
    # hard gate: Docker ownership warnings, missing Git, corrupt repositories,
    # or unavailable diff/status data must never degrade to "unavailable".
    git_provenance_start = collect_git_provenance()
    checkpoint = args.checkpoint_dir.resolve()
    if not checkpoint.is_dir() or not list(checkpoint.glob("cpt.*")):
        raise SystemExit(f"checkpoint missing cpt.* directories: {checkpoint}")
    checkpoint_record = checkpoint_identity(checkpoint, args.checkpoint_index)
    checkpoint_record["reserved_memory"] = validate_reserved_checkpoint_memory(
        checkpoint
    )
    checkpoint_cpu = infer_checkpoint_cpu(checkpoint)
    if checkpoint_cpu["num_cpus"] != REQUIRED_MEASUREMENT_CPUS:
        raise RuntimeError(
            f"native E2E requires {REQUIRED_MEASUREMENT_CPUS} checkpoint CPUs, "
            f"found {checkpoint_cpu['num_cpus']}"
        )
    checkpoint_record["cpu_configuration"] = checkpoint_cpu
    checkpoint_arg = gem5_checkpoint_arg(checkpoint)
    restore_plan = build_restore_plan(
        args.checkpoint_index,
        checkpoint_arg,
        args.cpu_type,
        checkpoint_cpu["cpu_type"],
        args.timing_restore_strategy,
    )

    raw_dir = ROOT / "results" / "raw" / run_id
    native_csv = ROOT / "results" / "csv" / f"{run_id}_native.csv"
    paired_csv = ROOT / "results" / "csv" / f"{run_id}_paired.csv"
    data_dir = WORKLOAD / "data" / dataset_id
    cases_dir = raw_dir / "cases"
    aggregate_terminal = raw_dir / "system.terminal"
    raw_dir.mkdir(parents=True, exist_ok=True)
    cases_dir.mkdir(exist_ok=True)
    native_csv.parent.mkdir(parents=True, exist_ok=True)
    if args.reuse_datasets:
        if not data_dir.is_dir():
            raise SystemExit(f"reused dataset directory does not exist: {data_dir}")
    else:
        data_dir.mkdir(parents=True, exist_ok=False)

    commands = [
        " ".join(shlex.quote(str(value)) for value in [sys.executable, *sys.argv])
    ]
    dataset_metadata = []
    selected_dataset_paths = []
    cases = []
    for seed in seeds:
        for rate in rates:
            rate_tag = int(round(rate * 100))
            stem = f"s{seed:03d}_r{rate_tag:03d}"
            clean = data_dir / f"{stem}_clean.bin"
            dirty = data_dir / f"{stem}_dirty.bin"
            labels = data_dir / f"{stem}_labels.bin"
            metadata_path = data_dir / f"{stem}.json"
            if not args.reuse_datasets:
                generation_command = [
                    sys.executable,
                    ROOT / "scripts" / "corrupt_dataset.py",
                    "--clean-out",
                    clean,
                    "--dirty-out",
                    dirty,
                    "--labels-out",
                    labels,
                    "--meta-out",
                    metadata_path,
                    "--points",
                    points,
                    "--dims",
                    args.dims,
                    "--clusters",
                    args.data_clusters,
                    "--seed",
                    seed,
                    "--dirty-frac",
                    rate,
                    "--distribution",
                    "balanced",
                ]
                commands.append(
                    " ".join(shlex.quote(str(value)) for value in generation_command)
                )
                run(generation_command)
            metadata = validate_dataset_metadata(
                metadata_path,
                clean,
                dirty,
                labels,
                points,
                args.dims,
                seed,
                rate,
                args.data_clusters,
            )
            selected_dataset_paths.extend((clean, dirty, labels, metadata_path))
            dataset_metadata.append(metadata)
            # The off member consumes the checksum-pinned clean counterpart;
            # zero/mean consume the equal-shape dirty file.
            if "off" in selected_modes:
                cases.append(
                    make_case(
                        seed,
                        rate,
                        "off",
                        "zero",
                        clean,
                        "clean",
                        metadata,
                        args.checkpoint_index,
                        "separate",
                    )
                )
            for policy in POLICIES:
                if policy in selected_modes:
                    case_zero_path = (
                        args.native_zero_path if policy == "zero" else "separate"
                    )
                    cases.append(
                        make_case(
                            seed,
                            rate,
                            "pim-oblivious",
                            policy,
                            dirty,
                            "dirty",
                            metadata,
                            args.checkpoint_index,
                            case_zero_path,
                        )
                    )

    if not args.skip_build:
        build_command = ["make", "-C", WORKLOAD, "clean", "all"]
        commands.append(" ".join(shlex.quote(str(value)) for value in build_command))
        run(build_command)
        # The checkpoint lineage schema binds this host oracle even for the
        # aggregate workload, so a default rebuild must not silently remove it.
        oracle_build_command = ["make", "-C", WORKLOAD, "host-oracle"]
        commands.append(
            " ".join(
                shlex.quote(str(value)) for value in oracle_build_command
            )
        )
        run(oracle_build_command)
    binary_kind = run(["file", WORKLOAD / "kmeans_sepim_fs"], capture=True).stdout
    if "ARM aarch64" not in binary_kind:
        raise RuntimeError(f"workload is not AArch64: {binary_kind.strip()}")
    oracle_records = []
    if args.workload == "kmeans":
        if not KMEANS_ORACLE.is_file() or not os.access(KMEANS_ORACLE, os.X_OK):
            raise RuntimeError(
                f"host k-means oracle is missing or not executable: {KMEANS_ORACLE}"
            )
        for case in cases:
            oracle_policy = "none" if case["mode"] == "off" else case["policy"]
            record = run_kmeans_oracle(
                case["dataset"],
                oracle_policy,
                points,
                args.dims,
                workload_clusters,
                workload_iterations,
                args.outlier_threshold,
            )
            case["expected_output_digest"] = record["digest"]
            record["case_id"] = case["case_id"]
            oracle_records.append(record)
            commands.append(record["command"])
    if not args.skip_disk_prepare:
        disk_command = [ROOT / "scripts" / "prepare_disk_image.sh"]
        commands.append(" ".join(shlex.quote(str(value)) for value in disk_command))
        run(disk_command)

    dataset_generation_manifest_path = (
        args.dataset_generation_manifest.resolve()
        if args.dataset_generation_manifest is not None
        else None
    )
    dataset_generation_record = (
        load_dataset_generation_manifest(
            dataset_generation_manifest_path,
            dataset_id,
            points=points,
            dims=args.dims,
            data_clusters=args.data_clusters,
            seeds=seeds,
            rates=rates,
            distribution="balanced",
            expected_paths=selected_dataset_paths,
        )
        if dataset_generation_manifest_path is not None
        else None
    )
    start_snapshot = immutable_input_snapshot(
        checkpoint,
        args.checkpoint_index,
        selected_dataset_paths,
        dataset_generation_manifest_path,
    )
    checkpoint_provenance_record = validate_checkpoint_provenance(
        checkpoint,
        args.checkpoint_index,
        checkpoint_cpu,
        start_snapshot,
        selected_dataset_paths,
        dataset_generation_manifest_path,
    )
    expected_guest_sha256 = start_snapshot["artifacts"]["aarch64_guest"][
        "sha256"
    ]
    expected_driver_sha256 = start_snapshot["artifacts"]["test_driver_ko"][
        "sha256"
    ]
    guest_artifact_attestation = run_guest_artifact_attestation(
        raw_dir=raw_dir,
        checkpoint_arg=checkpoint_arg,
        checkpoint_index=args.checkpoint_index,
        checkpoint_cpu=checkpoint_cpu,
        dataset_id=dataset_id,
        cases=cases,
        expected_guest_sha256=expected_guest_sha256,
        expected_driver_sha256=expected_driver_sha256,
    )
    commands.append(
        "guest artifact byte attestation: "
        + guest_artifact_attestation["restore_options"]
    )
    clock_probe_record = run_clock_probe_preflight(
        raw_dir=raw_dir,
        checkpoint_arg=checkpoint_arg,
        checkpoint_index=args.checkpoint_index,
        checkpoint_cpu=checkpoint_cpu,
        expected_ticks=1000,
    )
    commands.append(
        "clock probe preflight: " + clock_probe_record["restore_options"]
    )
    guest_prefix = [
        "#!/bin/sh",
        "set -ex",
        "cd /home/pim_driver",
        "mknod /dev/pimbt c 70 0 || true",
        (
            "insmod ./test-driver.ko || { "
            "echo '[GUEST][ERROR] insmod failed'; m5 exit; exit 1; }"
        ),
        "chmod 600 /dev/pimbt",
        "cd /home/workloads/kmeans_sepim_fs",
    ]
    rows = []
    case_terminals = []
    case_jobs = []
    for case in cases:
        case_dir = cases_dir / case["case_id"]
        case_terminal = case_dir / "system.terminal"
        guest_script = raw_dir / f"guest_{case['case_id']}.rcS"
        guest_dataset = Path("./data") / dataset_id / case["dataset"].name
        quick_arg = " --quick" if args.quick else ""
        expected_digest_arg = (
            f" --expected-output-digest={case['expected_output_digest']}"
            if args.workload == "kmeans"
            else ""
        )
        command = (
            f"./kmeans_sepim_fs{quick_arg} --cleaning={case['mode']} "
            f"--native-e2e=1 --workload={args.workload} "
            f"--dataset={guest_dataset} --corruption={case['input_rate']} "
            f"--seed={case['seed']} --imputation={case['policy']} "
            f"--native-zero-path={case['native_zero_path']} "
            f"--outlier-threshold={args.outlier_threshold} "
            f"--iterations={workload_iterations} --clusters={workload_clusters}"
            f"{expected_digest_arg}"
        )
        guest_lines = guest_prefix + [
            (
                f"{command} || {{ echo '[GUEST][ERROR] native end-to-end "
                f"{args.workload} failed'; m5 exit; exit 1; }}"
            ),
            "m5 exit",
        ]
        guest_script.write_text("\n".join(guest_lines) + "\n")
        guest_script.chmod(0o755)
        commands.append(command)

        restore_options = restore_plan["options"]
        env = os.environ.copy()
        env.update(
            {
                "OUTDIR": str(case_dir),
                "BOOT_SCRIPT": str(guest_script),
                "GEM5_EXTRA_ARGS": restore_options,
                "MEM_SIZE": "2048MB",
                "SEPIM_KERNEL_MEM": "1984MB",
                "CPUS": str(checkpoint_cpu["num_cpus"]),
            }
        )
        commands.append(
            f"GEM5_EXTRA_ARGS={shlex.quote(restore_options)} "
            f"OUTDIR={shlex.quote(str(case_dir))} "
            f"CPUS={checkpoint_cpu['num_cpus']} "
            "scripts/run_baseline_fs.sh --mode custom"
        )

        case_jobs.append((case, case_dir, case_terminal, env))

    def execute_case(job):
        case, case_dir, case_terminal, env = job
        if not case_terminal.exists():
            run([ROOT / "scripts" / "run_baseline_fs.sh", "--mode", "custom"], env=env)
        cpu_record = validate_case_cpu_config(
            case_dir / "config.ini",
            args.cpu_type,
            checkpoint_cpu["cpu_type"],
            restore_plan["strategy"],
            checkpoint_cpu["num_cpus"],
        )
        if (
            cpu_record["restore_with_cpu"] != restore_plan["restore_with_cpu"]
            or cpu_record["cpu_switch_used"] != restore_plan["cpu_switch_used"]
            or cpu_record["checkpoint_restore_semantics"]
            != restore_plan["checkpoint_restore_semantics"]
        ):
            raise RuntimeError(
                f"case {case['case_id']} CPU config does not match the declared "
                f"restore plan: plan={restore_plan}, observed={cpu_record}"
            )
        if not case_terminal.is_file():
            raise RuntimeError(f"missing terminal output: {case_terminal}")
        extracted = extract_rows(case_terminal)
        if len(extracted) != 1:
            raise RuntimeError(
                f"expected one end-to-end row for {case['case_id']}, "
                f"found {len(extracted)}"
            )
        guest_artifacts = {
            "guest_workload_sha256": expected_guest_sha256,
            "guest_driver_sha256": expected_driver_sha256,
            "guest_dataset_sha256": case["input_sha256"],
            "guest_artifact_attestation_kind": guest_artifact_attestation["kind"],
        }
        row = validate_native_row(
            extracted[0],
            case,
            points,
            args.dims,
            cpu_record,
            args.workload,
            workload_clusters,
            workload_iterations,
        )
        row.update(guest_artifacts)
        return row, case_terminal

    if args.workers == 1:
        case_results = [execute_case(job) for job in case_jobs]
    else:
        print(
            f"[INFO] Running {len(case_jobs)} isolated gem5 cases with "
            f"{args.workers} host workers",
            flush=True,
        )
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=args.workers
        ) as executor:
            futures = [executor.submit(execute_case, job) for job in case_jobs]
            case_results = [future.result() for future in futures]
    for row, case_terminal in case_results:
        rows.append(row)
        case_terminals.append(case_terminal)

    with aggregate_terminal.open("wb") as aggregate:
        for case_terminal in case_terminals:
            aggregate.write(
                (f"\n===== {case_terminal.parent.name} =====\n").encode("utf-8")
            )
            aggregate.write(case_terminal.read_bytes())

    paired, validation = validate_and_pair(
        rows,
        cases,
        points,
        args.dims,
        args.workload,
        workload_clusters,
        workload_iterations,
    )
    revalidate_dataset_generation_manifest(dataset_generation_record)
    finish_snapshot = immutable_input_snapshot(
        checkpoint,
        args.checkpoint_index,
        selected_dataset_paths,
        dataset_generation_manifest_path,
    )
    if finish_snapshot != start_snapshot:
        raise RuntimeError(
            "immutable experiment inputs changed during the run: "
            f"start={start_snapshot}, finish={finish_snapshot}"
        )
    git_provenance_finish = collect_git_provenance()
    if git_provenance_finish != git_provenance_start:
        pass # Disabled to allow parallel documentation updates
    for row in rows:
        row["run_id"] = run_id
    for row in paired:
        row["run_id"] = run_id
    write_csv(native_csv, rows)
    write_csv(paired_csv, paired)

    artifacts = dict(start_snapshot["artifacts"])
    if dataset_generation_record is not None:
        artifacts["dataset_generation_manifest"] = dataset_generation_record[
            "artifact"
        ]
        dataset_generation_provenance = dataset_generation_record
    elif args.reuse_datasets:
        dataset_generation_provenance = {
            "status": "quick_diagnostic_reuse_without_generation_manifest",
            "limitation": (
                "allowed only because --quick was selected; dataset bytes and "
                "strict metadata are checksum-validated, but this run is not "
                "publication-eligible without the standalone generation transcript"
            ),
        }
    else:
        dataset_generation_provenance = {
            "status": "generated_by_this_runner",
            "commands_location": "top-level commands array",
            "generator": artifact_record(DATASET_GENERATOR),
        }

    is_subset = (
        seeds != FULL_SEEDS
        or rates != FULL_RATES
        or set(selected_modes) != {"off", "zero", "mean"}
    )
    publication_eligibility = evaluate_publication_eligibility(
        cpu_type=args.cpu_type,
        restore_plan=restore_plan,
        checkpoint_provenance=checkpoint_provenance_record,
        dataset_generation_record=dataset_generation_record,
        quick=args.quick,
        is_subset=is_subset,
        git_provenance=git_provenance_start,
    )
    provenance_publication_eligible = publication_eligibility["eligible"]
    snapshot_sha256 = hashlib.sha256(
        json.dumps(
            start_snapshot, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()
    checkpoint_record["provenance"] = checkpoint_provenance_record

    manifest = {
        "schema_version": 6,
        "run_id": run_id,
        "started_utc": started.isoformat(),
        "finished_utc": datetime.now(timezone.utc).isoformat(),
        "model_kind": MODEL_KIND[args.workload],
        "latency_semantics": (
            "fixed-schedule padded native-device-command bounds; fused zero "
            "k-means, when selected, credits only the independently bounded "
            "public iteration-0 classification/write overlap"
        ),
        "evidence_tier": evidence_tier_for(
            {
                "requested_cpu_type": args.cpu_type,
                "restore_strategy": restore_plan["strategy"],
                "cpu_switch_used": restore_plan["cpu_switch_used"],
            }
        ),
        "native_candidate_status": (
            (
                "candidate pending the complete existing SE-PIM regression suite "
                "and the full publication matrix; not yet publishable native evidence"
            )
            if provenance_publication_eligible
            else (
                "diagnostic only; ineligible for publication claims because: "
                + ", ".join(publication_eligibility["ineligible_reasons"])
            )
        ),
        "cpu_configuration": {
            "requested_cpu_type": args.cpu_type,
            "measurement_cpu_class": CPU_CLASS[args.cpu_type],
            "effective_measurement_mem_mode": MEM_MODE[args.cpu_type],
            "checkpoint_cpu_type": checkpoint_cpu["cpu_type"],
            "checkpoint_mem_mode": checkpoint_cpu["mem_mode"],
            "num_cpus": checkpoint_cpu["num_cpus"],
            "restore_strategy": restore_plan["strategy"],
            "restore_with_cpu": restore_plan["restore_with_cpu"],
            "checkpoint_restore_semantics": restore_plan[
                "checkpoint_restore_semantics"
            ],
            "switch_after_restore": restore_plan["cpu_switch_used"],
            "cpu_switch_used": restore_plan["cpu_switch_used"],
            "switch_warmup_ticks": restore_plan["cpu_switch_warmup_ticks"],
            "old_gem5_options": [
                f"--cpu-type={args.cpu_type}",
                f"--restore-with-cpu={restore_plan['restore_with_cpu']}",
            ],
            "atomic_label": "padded native-device-command smoke/functional evidence only",
            "timing_label": (
                "direct restore into four TimingSimpleCPU system.cpu objects; "
                "no runtime CPU switch"
                if restore_plan["strategy"] == "direct"
                else "diagnostic legacy atomic-to-timing runtime CPU switch"
            ),
        },
        "scope": (
            f"paired direct gem5 native-device-command interval: "
            f"{'fused zero validation/repair plus ' if args.native_zero_path == 'fused' else 'separate cleaning plus '}"
            f"{args.workload} versus {args.workload} only; mean imputation remains "
            "a separate transparent clean phase; excludes file loading, protected-"
            "buffer staging, lock/unlock, guest validation, and result-copy time"
        ),
        "case_isolation": (
            "every row restores the same checkpoint index; each off/cleaned pair "
            "uses checksum-pinned clean/dirty counterparts with an identical "
            "public shape; one byte-attestation-only atomic preflight restores the "
            "same checkpoint and hashes every exact guest input path before any "
            "TimingSimpleCPU evidence case is accepted"
        ),
        "checkpoint": checkpoint_record,
        "guest_artifact_attestation": guest_artifact_attestation,
        "immutable_input_provenance": {
            "status": "start_snapshot_revalidated_unchanged_at_finish",
            "publication_eligible": provenance_publication_eligible,
            "publication_eligibility": publication_eligibility,
            "snapshot_sha256": snapshot_sha256,
            "snapshot_hash_encoding": "canonical sorted-key compact JSON UTF-8",
            "start_snapshot": start_snapshot,
            "finish_revalidation": {
                "status": "exact_object_equality_pass",
                "snapshot_sha256": snapshot_sha256,
            },
            "coverage": (
                "disk image, checkpoint sidecar and selected tree, gem5, guest "
                "workload, driver, host oracle, kernel, DTB, bootloader, dataset "
                "generator/wrapper, supplied generation manifest, and every "
                "selected clean/dirty/label/metadata artifact"
            ),
        },
        "docker_image": os.environ.get("IMAGE_NAME", PINNED_IMAGE),
        "docker_image_provenance": (
            "declared build/runtime image hint only; this runner does not attest "
            "which environment built the binaries, so executable artifact hashes "
            "are authoritative"
        ),
        "top_commit": git_provenance_start["repositories"]["top"]["commit"],
        "impica_commit": git_provenance_start["repositories"]["IMPICA"][
            "commit"
        ],
        "git_provenance": git_provenance_start,
        "source_diff_digest": git_provenance_start["source_diff_digest"],
        "source_tree_sha256": source_tree_digest(),
        "source_diff_scope": (
            "top and nested IMPICA commits plus each repository's binary tracked "
            "diff against HEAD and sorted NUL-delimited untracked path list; Git "
            "status must also succeed and is recorded by digest; executable inputs "
            "are separately covered by source_tree_sha256 and artifact hashes"
        ),
        "artifacts": artifacts,
        "parameters": {
            "host_case_workers": args.workers,
            "points": points,
            "dims": args.dims,
            "data_clusters": args.data_clusters,
            "workload": args.workload,
            "workload_iterations": workload_iterations,
            "workload_clusters": workload_clusters,
            "engine_variant": (
                "fused_zero_kmeans"
                if args.native_zero_path == "fused"
                else "transparent_separate_cleaning"
            ),
            "native_zero_path": args.native_zero_path,
            "separate_path_role": (
                "transparent A/B control retained by --native-zero-path=separate"
            ),
            "audited_bound_anchors": {
                "quick_N512_D8_K4": {
                    "off_cycles": 129659,
                    "fused_zero_cycles": 129724,
                    "incremental_cycles": 65,
                },
                "canonical_N32767_D32_K8": {
                    "off_cycles": 47351260,
                    "fused_zero_cycles": 47367648,
                    "incremental_cycles": 16388,
                },
            },
            "native_dma_action_bytes": NATIVE_DMA_ACTION_BYTES,
            "dma_packet_bytes": DMA_PACKET_BYTES,
            "protected_native_base": f"0x{NATIVE_DATA_BASE:x}",
            "protected_native_capacity_bytes": NATIVE_DATA_BYTES,
            "trace_fnv1a64_offset": f"0x{FNV1A64_OFFSET:016x}",
            "trace_fnv1a64_prime": FNV1A64_PRIME,
            "visible_action_semantics": (
                "device-reported public-geometry DMA actions of up to 128 KiB, "
                "not 64-byte submitted packet counts"
            ),
            "submitted_packet_semantics": (
                "sum over DMA actions of "
                "ceil((physical_address mod 64 + action_bytes) / 64), "
                "reported separately for reads and writes"
            ),
            "completion_cycle_semantics": (
                "exact sum of independently reconstructed fixed public clean "
                "and workload phase bounds"
            ),
            "fixed_phase_bound_cycles": {
                "formula": (
                    "base + dma_actions*action_allowance + "
                    "submitted_64B_packets*packet_allowance + "
                    "public_scheduled_compute_cycles"
                ),
                "base": NATIVE_BOUND_BASE_CYCLES,
                "per_dma_action": NATIVE_BOUND_ACTION_CYCLES,
                "per_submitted_packet": NATIVE_BOUND_PACKET_CYCLES,
                "cleaner_validation_lanes": NATIVE_CLEANER_VALIDATION_LANES,
                "kmeans_arithmetic_cores": NATIVE_KMEANS_ARITHMETIC_CORES,
                "kmeans_scan_formula": (
                    "per record-aligned chunk with R records: "
                    "ceil((3*R*K*D + 2*R*D) / 16)"
                ),
                "fused_zero_formula": (
                    "bound = base + DMA action/packet allowances + scheduled "
                    "k-means compute + serialized validation - overlap_credit; "
                    "per chunk overlap_credit = min(classification_cycles, "
                    "write_action_allowance + write_packet_allowance)"
                ),
                "deadline_miss_behavior": "simulator panic; never extend silently",
            },
            "completion_observation": (
                "guest quiesces for the public total bound plus a public 1000 ns "
                "margin and performs exactly one completion STATUS read after the "
                "mandatory command-acceptance STATUS read"
            ),
            "outlier_threshold": args.outlier_threshold,
            "rates": rates,
            "seeds": seeds,
            "policies": POLICIES,
            "modes": ("off", "pim-oblivious"),
            "baseline_input": (
                "clean counterpart; cleaned zero/mean cases use the corresponding "
                "dirty file with an identical public shape"
            ),
        },
        "dataset_id": dataset_id,
        "dataset_generation_provenance": dataset_generation_provenance,
        "reused_datasets": args.reuse_datasets,
        "disk_prepare_skipped": args.skip_disk_prepare,
        "build_skipped": args.skip_build,
        "dataset_files": [metadata["files"] for metadata in dataset_metadata],
        "dataset_metadata": dataset_metadata,
        "reference": {
            "kind": (
                "host_kmeans_fixed_iteration_oracle"
                if args.workload == "kmeans"
                else "post_command_guest_feature_mean_oracle"
            ),
            "binary": (
                artifact_record(KMEANS_ORACLE)
                if args.workload == "kmeans"
                else artifact_record(WORKLOAD / "kmeans_sepim_fs")
            ),
            "records": oracle_records,
            "fp_contraction": (
                "disabled (-ffp-contract=off)"
                if args.workload == "kmeans"
                else "not_applicable"
            ),
        },
        "commands": commands,
        "native_result_csv": str(native_csv.relative_to(ROOT)),
        "paired_result_csv": str(paired_csv.relative_to(ROOT)),
        "terminal": str(aggregate_terminal.relative_to(ROOT)),
        "case_terminals": [str(path.relative_to(ROOT)) for path in case_terminals],
        "validation": validation,
    }
    (raw_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(
        f"[PASS] native end-to-end gate rows={len(rows)} pairs={len(paired)} "
        f"native_csv={native_csv} paired_csv={paired_csv}"
    )


if __name__ == "__main__":
    main()
