#!/usr/bin/env python3
"""Capture and bind immutable inputs to a native gem5 checkpoint.

The checkpoint creator uses this helper in two phases.  ``capture`` hashes
every input after guest-disk injection but before gem5 starts.  ``finalize``
rehashes those inputs, rejects any change, and atomically writes a sidecar that
also binds the selected checkpoint tree and its top-level gem5 outputs.
"""

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


SCHEMA_VERSION = 1
TREE_HASH_ALGORITHM = "sha256_concat_path_nul_sha256_nul_v1"
INPUT_ARGUMENTS = (
    ("disk_image", "disk-image"),
    ("gem5_opt", "gem5-opt"),
    ("aarch64_guest", "aarch64-guest"),
    ("test_driver_ko", "test-driver-ko"),
    ("kmeans_oracle", "kmeans-oracle"),
    ("kernel", "kernel"),
    ("dtb", "dtb"),
    ("bootloader", "bootloader"),
    ("dataset_generator", "dataset-generator"),
    ("dataset_wrapper", "dataset-wrapper"),
)


class ProvenanceError(RuntimeError):
    """An input or checkpoint cannot be captured reproducibly."""


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def validate_utc(value, label):
    normalized = value
    has_timezone = normalized.endswith("Z") or normalized.endswith("+00:00")
    if normalized.endswith("Z"):
        normalized = normalized[:-1]
    elif normalized.endswith("+00:00"):
        normalized = normalized[:-6]
    try:
        datetime.strptime(normalized, "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        try:
            datetime.strptime(normalized, "%Y-%m-%dT%H:%M:%S.%f")
        except ValueError as error:
            raise ProvenanceError(
                f"{label} is not an ISO-8601 timestamp: {value!r}"
            ) from error
    if not has_timezone:
        raise ProvenanceError(f"{label} must include a timezone: {value!r}")
    return value


def shown_path(path, project_root):
    resolved = path.resolve()
    try:
        return resolved.relative_to(project_root).as_posix()
    except ValueError:
        return str(resolved)


def sha256_file(path):
    before = path.stat()
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
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
        raise ProvenanceError(f"file changed while hashing: {path}")
    return after.st_size, digest.hexdigest()


def artifact(path, project_root, logical_name=None, display_path=None):
    if path.is_symlink():
        raise ProvenanceError(
            f"provenance inputs must not be symbolic links: {path}"
        )
    resolved = path.resolve()
    if not resolved.is_file():
        raise ProvenanceError(f"required provenance input is missing: {resolved}")
    size, digest = sha256_file(resolved)
    record = {
        "path": display_path if display_path is not None else shown_path(resolved, project_root),
        "bytes": size,
        "sha256": digest,
        "required": True,
    }
    if logical_name is not None:
        record["logical_name"] = logical_name
    return record


def tree_digest(records):
    digest = hashlib.sha256()
    for record in sorted(records, key=lambda item: item["path"]):
        digest.update(record["path"].encode("utf-8"))
        digest.update(b"\0")
        digest.update(record["sha256"].encode("ascii"))
        digest.update(b"\0")
    return digest.hexdigest()


def list_tree_files(root):
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file()
    )


def capture_tree(root, project_root):
    resolved = root.resolve()
    if not resolved.is_dir():
        raise ProvenanceError(f"required workload data tree is missing: {resolved}")
    before = list_tree_files(resolved)
    records = [
        artifact(
            path,
            project_root,
            display_path=path.relative_to(resolved).as_posix(),
        )
        for path in before
    ]
    after = list_tree_files(resolved)
    if before != after:
        raise ProvenanceError(f"file set changed while hashing data tree: {resolved}")
    return {
        "root": shown_path(resolved, project_root),
        "file_count": len(records),
        "files": records,
        "tree_hash_algorithm": TREE_HASH_ALGORITHM,
        "tree_sha256": tree_digest(records),
    }


def parse_environment(values):
    environment = {}
    for value in values:
        if "=" not in value:
            raise ProvenanceError(f"environment entry must be KEY=VALUE: {value!r}")
        key, item = value.split("=", 1)
        if not key or key in environment:
            raise ProvenanceError(f"invalid or duplicate environment key: {key!r}")
        environment[key] = item
    return dict(sorted(environment.items()))


def capture_named_files(values, project_root, label):
    records = {}
    for value in values:
        if "=" not in value:
            raise ProvenanceError(f"{label} entry must be NAME=PATH: {value!r}")
        name, path_text = value.split("=", 1)
        if not name or name in records:
            raise ProvenanceError(f"invalid or duplicate {label} name: {name!r}")
        records[name] = artifact(
            Path(path_text), project_root, logical_name=name
        )
    return dict(sorted(records.items()))


def atomic_json(path, document):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise ProvenanceError(f"refusing to overwrite provenance file: {path}")
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    try:
        with temporary.open("x", encoding="utf-8") as stream:
            json.dump(document, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(str(temporary), str(path))
        directory_fd = os.open(str(path.parent), os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def input_paths(args):
    return {
        logical_name: Path(getattr(args, logical_name))
        for logical_name, _ in INPUT_ARGUMENTS
    }


def capture_inputs(args):
    if args.num_cpus <= 0:
        raise ProvenanceError("num_cpus must be positive")
    has_parent = bool(args.parent_checkpoint_dir)
    if (args.creation_kind == "timing_recheckpoint_from_parent") != has_parent:
        raise ProvenanceError(
            "timing_recheckpoint_from_parent requires exactly one parent "
            "checkpoint directory; cold_boot must not declare one"
        )
    project_root = Path(args.project_root).resolve()
    checkpoint_dir = Path(args.checkpoint_dir).resolve()
    capture_started = utc_now()
    inputs = {
        logical_name: artifact(path, project_root, logical_name=logical_name)
        for logical_name, path in input_paths(args).items()
    }
    creator_inputs = capture_named_files(
        args.creator_input, project_root, "creator input"
    )
    if not creator_inputs:
        raise ProvenanceError("at least one checkpoint creator input is required")
    workload_tree = capture_tree(Path(args.workload_data_root), project_root)
    parent_checkpoint_tree = (
        capture_tree(Path(args.parent_checkpoint_dir), project_root)
        if args.parent_checkpoint_dir
        else None
    )
    expected_class = {
        "atomic": "AtomicSimpleCPU",
        "timing": "TimingSimpleCPU",
    }[args.cpu_type]
    snapshot = {
        "schema_version": SCHEMA_VERSION,
        "kind": "checkpoint_input_snapshot",
        "capture_started_utc": capture_started,
        "capture_finished_utc": utc_now(),
        "project_root": str(project_root),
        "checkpoint_directory": shown_path(checkpoint_dir, project_root),
        "checkpoint_creation": {
            "creation_kind": args.creation_kind,
            "cpu_type": args.cpu_type,
            "expected_cpu_class": expected_class,
            "expected_mem_mode": args.cpu_type,
            "num_cpus": args.num_cpus,
            "memory_size": args.memory_size,
            "kernel_memory_limit": args.kernel_memory_limit,
            "container_image": args.container_image,
            "working_directory": shown_path(Path(args.working_directory), project_root),
            "command": args.command,
            "environment": parse_environment(args.environment),
            "started_utc": None,
            "finished_utc": None,
        },
        "inputs": inputs,
        "creator_inputs": creator_inputs,
        "workload_data_tree": workload_tree,
    }
    if parent_checkpoint_tree is not None:
        snapshot["parent_checkpoint_tree"] = parent_checkpoint_tree
    atomic_json(Path(args.snapshot), snapshot)
    print(
        "[PASS] captured checkpoint inputs: inputs=%d data_files=%d snapshot=%s"
        % (len(inputs), workload_tree["file_count"], args.snapshot)
    )


def load_snapshot(path):
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ProvenanceError(f"cannot load input snapshot {path}: {error}") from error
    if document.get("schema_version") != SCHEMA_VERSION:
        raise ProvenanceError("input snapshot has an unsupported schema_version")
    if document.get("kind") != "checkpoint_input_snapshot":
        raise ProvenanceError("input snapshot has the wrong document kind")
    return document


def recapture_named_inputs(snapshot, project_root):
    records = {}
    for logical_name, previous in sorted(snapshot["inputs"].items()):
        path = Path(previous["path"])
        if not path.is_absolute():
            path = project_root / path
        records[logical_name] = artifact(
            path,
            project_root,
            logical_name=logical_name,
        )
    return records


def compare_capture(label, before, after):
    if before != after:
        before_text = json.dumps(before, indent=2, sort_keys=True)
        after_text = json.dumps(after, indent=2, sort_keys=True)
        raise ProvenanceError(
            f"{label} changed during checkpoint creation\n"
            f"--- before ---\n{before_text}\n--- after ---\n{after_text}"
        )


def checkpoint_sort_key(path):
    suffix = path.name.partition(".")[2]
    return (0, int(suffix)) if suffix.isdigit() else (1, suffix)


def capture_selected_checkpoint(checkpoint_dir, restore_index, project_root):
    candidates = sorted(
        (path for path in checkpoint_dir.glob("cpt.*") if path.is_dir()),
        key=checkpoint_sort_key,
    )
    if restore_index < 1 or restore_index > len(candidates):
        raise ProvenanceError(
            "checkpoint restore index %d is outside 1..%d under %s"
            % (restore_index, len(candidates), checkpoint_dir)
        )
    selected = candidates[restore_index - 1]
    paths_before = list_tree_files(selected)
    records = [
        artifact(
            path,
            project_root,
            display_path=path.relative_to(selected).as_posix(),
        )
        for path in paths_before
    ]
    if paths_before != list_tree_files(selected):
        raise ProvenanceError(f"selected checkpoint changed while hashing: {selected}")
    if not any(record["path"] == "m5.cpt" for record in records):
        raise ProvenanceError(f"selected checkpoint lacks m5.cpt: {selected}")
    return {
        "restore_index": restore_index,
        "selected_checkpoint": selected.name,
        "path": shown_path(selected, project_root),
        "file_count": len(records),
        "files": records,
        "tree_hash_algorithm": TREE_HASH_ALGORITHM,
        "selected_checkpoint_tree_sha256": tree_digest(records),
    }


def bound_checkpoint_tree(selected, output_files):
    records = []
    selected_name = selected["selected_checkpoint"]
    for record in selected["files"]:
        bound = dict(record)
        bound["path"] = f"selected_checkpoint/{selected_name}/{record['path']}"
        records.append(bound)
    for label, record in sorted(output_files.items()):
        bound = dict(record)
        bound["path"] = "config.ini" if label == "config_ini" else "system.terminal"
        records.append(bound)
    return {
        "file_count": len(records),
        "files": records,
        "tree_hash_algorithm": TREE_HASH_ALGORITHM,
        "tree_sha256": tree_digest(records),
    }


def finalize(args):
    snapshot_path = Path(args.snapshot).resolve()
    output_path = Path(args.output).resolve()
    if output_path.exists():
        raise ProvenanceError(f"refusing to overwrite provenance sidecar: {output_path}")
    snapshot = load_snapshot(snapshot_path)
    project_root = Path(snapshot["project_root"]).resolve()
    checkpoint_dir = Path(args.checkpoint_dir).resolve()
    expected_checkpoint_dir = snapshot["checkpoint_directory"]
    if shown_path(checkpoint_dir, project_root) != expected_checkpoint_dir:
        raise ProvenanceError(
            "checkpoint directory does not match the pre-boot snapshot: %s != %s"
            % (shown_path(checkpoint_dir, project_root), expected_checkpoint_dir)
        )

    current_inputs = recapture_named_inputs(snapshot, project_root)
    compare_capture("named checkpoint inputs", snapshot["inputs"], current_inputs)
    current_creator_inputs = {}
    for logical_name, previous in sorted(snapshot["creator_inputs"].items()):
        path = Path(previous["path"])
        if not path.is_absolute():
            path = project_root / path
        current_creator_inputs[logical_name] = artifact(
            path, project_root, logical_name=logical_name
        )
    compare_capture(
        "checkpoint creator inputs",
        snapshot["creator_inputs"],
        current_creator_inputs,
    )
    data_root = Path(snapshot["workload_data_tree"]["root"])
    if not data_root.is_absolute():
        data_root = project_root / data_root
    current_tree = capture_tree(data_root, project_root)
    compare_capture(
        "workload data tree", snapshot["workload_data_tree"], current_tree
    )
    parent_checkpoint_tree = snapshot.get("parent_checkpoint_tree")
    if parent_checkpoint_tree is not None:
        parent_root = Path(parent_checkpoint_tree["root"])
        if not parent_root.is_absolute():
            parent_root = project_root / parent_root
        current_parent_tree = capture_tree(parent_root, project_root)
        compare_capture(
            "parent checkpoint tree", parent_checkpoint_tree, current_parent_tree
        )

    selected = capture_selected_checkpoint(
        checkpoint_dir, args.restore_index, project_root
    )
    output_files = {
        "config_ini": artifact(
            checkpoint_dir / "config.ini",
            project_root,
            logical_name="config_ini",
        ),
        "system_terminal": artifact(
            checkpoint_dir / "system.terminal",
            project_root,
            logical_name="system_terminal",
        ),
    }
    checkpoint_creation = dict(snapshot["checkpoint_creation"])
    checkpoint_creation["started_utc"] = validate_utc(
        args.checkpoint_started_utc, "checkpoint_started_utc"
    )
    checkpoint_creation["finished_utc"] = validate_utc(
        args.checkpoint_finished_utc, "checkpoint_finished_utc"
    )
    document = {
        "schema_version": SCHEMA_VERSION,
        "created_utc": utc_now(),
        "capture_started_utc": snapshot["capture_started_utc"],
        "capture_finished_utc": snapshot["capture_finished_utc"],
        "project_root": snapshot["project_root"],
        "checkpoint_directory": snapshot["checkpoint_directory"],
        "checkpoint_creation": checkpoint_creation,
        "inputs": snapshot["inputs"],
        "creator_inputs": snapshot["creator_inputs"],
        "workload_data_tree": snapshot["workload_data_tree"],
        "selected_checkpoint": selected,
        "output_files": output_files,
        "bound_checkpoint_tree": bound_checkpoint_tree(selected, output_files),
    }
    if parent_checkpoint_tree is not None:
        document["parent_checkpoint_tree"] = parent_checkpoint_tree
    atomic_json(output_path, document)
    if args.remove_snapshot:
        snapshot_path.unlink()
    print(
        "[PASS] checkpoint provenance finalized: checkpoint=%s files=%d output=%s"
        % (
            selected["selected_checkpoint"],
            document["bound_checkpoint_tree"]["file_count"],
            output_path,
        )
    )


def build_parser():
    parser = argparse.ArgumentParser(
        description="Capture and bind native checkpoint provenance"
    )
    subparsers = parser.add_subparsers(dest="operation")

    capture_parser = subparsers.add_parser("capture")
    capture_parser.add_argument("--project-root", required=True)
    capture_parser.add_argument("--snapshot", required=True)
    capture_parser.add_argument("--checkpoint-dir", required=True)
    capture_parser.add_argument("--workload-data-root", required=True)
    for logical_name, cli_name in INPUT_ARGUMENTS:
        capture_parser.add_argument(f"--{cli_name}", dest=logical_name, required=True)
    capture_parser.add_argument(
        "--cpu-type", choices=("atomic", "timing"), required=True
    )
    capture_parser.add_argument("--num-cpus", type=int, required=True)
    capture_parser.add_argument("--memory-size", required=True)
    capture_parser.add_argument("--kernel-memory-limit", required=True)
    capture_parser.add_argument("--container-image", required=True)
    capture_parser.add_argument("--working-directory", required=True)
    capture_parser.add_argument("--command", required=True)
    capture_parser.add_argument("--environment", action="append", default=[])
    capture_parser.add_argument("--creator-input", action="append", default=[])
    capture_parser.add_argument(
        "--creation-kind",
        choices=("cold_boot", "timing_recheckpoint_from_parent"),
        default="cold_boot",
    )
    capture_parser.add_argument("--parent-checkpoint-dir")
    capture_parser.set_defaults(handler=capture_inputs)

    finalize_parser = subparsers.add_parser("finalize")
    finalize_parser.add_argument("--snapshot", required=True)
    finalize_parser.add_argument("--output", required=True)
    finalize_parser.add_argument("--checkpoint-dir", required=True)
    finalize_parser.add_argument("--restore-index", type=int, default=1)
    finalize_parser.add_argument("--checkpoint-started-utc", required=True)
    finalize_parser.add_argument("--checkpoint-finished-utc", required=True)
    finalize_parser.add_argument("--remove-snapshot", action="store_true")
    finalize_parser.set_defaults(handler=finalize)
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    if not hasattr(args, "handler"):
        parser.error("an operation is required: capture or finalize")
    try:
        args.handler(args)
    except ProvenanceError as error:
        print(f"[ERROR] {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
