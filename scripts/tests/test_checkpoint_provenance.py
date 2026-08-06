#!/usr/bin/env python3
"""Focused tests for checkpoint parent-lineage provenance."""

import argparse
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "checkpoint_provenance", ROOT / "scripts" / "checkpoint_provenance.py"
)
PROVENANCE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PROVENANCE)


class ParentCheckpointProvenanceTests(unittest.TestCase):
    def fixture(self, temporary, *, creation_kind, with_parent):
        root = Path(temporary)
        inputs = root / "inputs"
        inputs.mkdir()
        values = {}
        for logical_name, _ in PROVENANCE.INPUT_ARGUMENTS:
            path = inputs / logical_name
            path.write_bytes((logical_name + "\n").encode())
            values[logical_name] = str(path)
        data = root / "data"
        data.mkdir()
        (data / "matrix.bin").write_bytes(b"matrix")
        parent = root / "parent"
        if with_parent:
            parent.mkdir()
            (parent / "checkpoint_provenance.json").write_text("{}\n")
            child = parent / "cpt.1"
            child.mkdir()
            (child / "m5.cpt").write_bytes(b"parent-state")
        output = root / "output"
        output.mkdir()
        creator = inputs / "creator"
        creator.write_bytes(b"creator\n")
        namespace = argparse.Namespace(
            project_root=str(root),
            checkpoint_dir=str(output),
            workload_data_root=str(data),
            cpu_type="timing",
            num_cpus=4,
            memory_size="2048MB",
            kernel_memory_limit="1984MB",
            container_image="image@sha256:" + "a" * 64,
            working_directory=str(root),
            command="gem5 timing recheckpoint",
            environment=[],
            creator_input=[f"checkpoint_creator={creator}"],
            creation_kind=creation_kind,
            parent_checkpoint_dir=str(parent) if with_parent else None,
            snapshot=str(output / ".snapshot.json"),
            **values,
        )
        return namespace, parent, output

    def test_recheckpoint_snapshot_binds_complete_parent_tree(self):
        with tempfile.TemporaryDirectory() as temporary:
            args, _, _ = self.fixture(
                temporary,
                creation_kind="timing_recheckpoint_from_parent",
                with_parent=True,
            )
            PROVENANCE.capture_inputs(args)
            document = json.loads(Path(args.snapshot).read_text())
        self.assertEqual(
            document["checkpoint_creation"]["creation_kind"],
            "timing_recheckpoint_from_parent",
        )
        self.assertEqual(document["parent_checkpoint_tree"]["file_count"], 2)
        self.assertEqual(
            {item["path"] for item in document["parent_checkpoint_tree"]["files"]},
            {"checkpoint_provenance.json", "cpt.1/m5.cpt"},
        )

    def test_creation_kind_and_parent_must_agree(self):
        for kind, with_parent in (
            ("cold_boot", True),
            ("timing_recheckpoint_from_parent", False),
        ):
            with self.subTest(kind=kind, with_parent=with_parent):
                with tempfile.TemporaryDirectory() as temporary:
                    args, _, _ = self.fixture(
                        temporary, creation_kind=kind, with_parent=with_parent
                    )
                    with self.assertRaisesRegex(
                        PROVENANCE.ProvenanceError, "requires exactly one parent"
                    ):
                        PROVENANCE.capture_inputs(args)

    def test_finalize_rejects_parent_changed_after_capture(self):
        with tempfile.TemporaryDirectory() as temporary:
            args, parent, output = self.fixture(
                temporary,
                creation_kind="timing_recheckpoint_from_parent",
                with_parent=True,
            )
            PROVENANCE.capture_inputs(args)
            (parent / "cpt.1" / "m5.cpt").write_bytes(b"changed")
            finalize = argparse.Namespace(
                snapshot=args.snapshot,
                output=str(output / "checkpoint_provenance.json"),
                checkpoint_dir=str(output),
                restore_index=1,
                checkpoint_started_utc="2026-07-15T00:00:00Z",
                checkpoint_finished_utc="2026-07-15T00:00:01Z",
                remove_snapshot=False,
            )
            with self.assertRaisesRegex(
                PROVENANCE.ProvenanceError, "parent checkpoint tree changed"
            ):
                PROVENANCE.finalize(finalize)


if __name__ == "__main__":
    unittest.main()
