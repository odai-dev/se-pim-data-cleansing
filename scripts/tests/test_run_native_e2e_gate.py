#!/usr/bin/env python3
"""Focused tests for native E2E CPU and source-provenance gates."""

import importlib.util
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "run_native_e2e_gate", ROOT / "scripts" / "run_native_e2e_gate.py"
)
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)


def write_config(path, primary, mem_mode, switch=None, cpus=4):
    lines = [
        "[system]",
        "cache_line_size=64",
        f"mem_mode={mem_mode}",
    ]
    for index in range(cpus):
        lines.extend((f"[system.cpu{index}]", f"type={primary}"))
    if switch is not None:
        for index in range(cpus):
            lines.extend((f"[system.switch_cpus{index}]", f"type={switch}"))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


class RestoreStrategyTests(unittest.TestCase):
    def test_direct_timing_command_and_config_have_no_switch_cpu(self):
        plan = GATE.build_restore_plan(2, "results/cpt", "timing", "atomic")
        self.assertEqual(
            plan["options"],
            "-r 2 --checkpoint-dir=results/cpt --cpu-type=timing "
            "--restore-with-cpu=timing",
        )
        self.assertFalse(plan["cpu_switch_used"])
        self.assertFalse(plan["publication_strategy_eligible"])
        with tempfile.TemporaryDirectory() as temporary:
            config = Path(temporary) / "config.ini"
            write_config(config, "TimingSimpleCPU", "timing")
            record = GATE.validate_case_cpu_config(
                config, "timing", "atomic", "direct", 4
            )
        self.assertEqual(record["restore_with_cpu"], "timing")
        self.assertFalse(record["cpu_switch_used"])
        self.assertEqual(
            record["checkpoint_restore_semantics"],
            "atomic_architectural_checkpoint_state_restored_directly_into_"
            "TimingSimpleCPU",
        )

    def test_same_class_timing_checkpoint_is_publication_strategy(self):
        plan = GATE.build_restore_plan(1, "results/cpt", "timing", "timing")
        self.assertTrue(plan["publication_strategy_eligible"])
        self.assertEqual(
            plan["checkpoint_restore_semantics"], "same_cpu_class_direct_restore"
        )
        with tempfile.TemporaryDirectory() as temporary:
            config = Path(temporary) / "config.ini"
            write_config(config, "TimingSimpleCPU", "timing")
            record = GATE.validate_case_cpu_config(
                config, "timing", "timing", "direct", 4
            )
        self.assertEqual(
            record["checkpoint_restore_semantics"], "same_cpu_class_direct_restore"
        )

    def test_legacy_switch_is_explicit_and_diagnostic(self):
        plan = GATE.build_restore_plan(
            1, "results/cpt", "timing", "atomic", "switch"
        )
        self.assertIn("--restore-with-cpu=atomic", plan["options"])
        self.assertTrue(plan["cpu_switch_used"])
        self.assertFalse(plan["publication_strategy_eligible"])
        with tempfile.TemporaryDirectory() as temporary:
            config = Path(temporary) / "config.ini"
            write_config(
                config, "AtomicSimpleCPU", "atomic", switch="TimingSimpleCPU"
            )
            record = GATE.validate_case_cpu_config(
                config, "timing", "atomic", "switch", 4
            )
        self.assertTrue(record["cpu_switch_used"])
        self.assertEqual(record["cpu_switch_warmup_ticks"], 10000)

    def test_direct_timing_rejects_switch_cpu_sections(self):
        with tempfile.TemporaryDirectory() as temporary:
            config = Path(temporary) / "config.ini"
            write_config(
                config, "TimingSimpleCPU", "timing", switch="TimingSimpleCPU"
            )
            with self.assertRaisesRegex(RuntimeError, "unexpectedly constructed"):
                GATE.validate_case_cpu_config(
                    config, "timing", "atomic", "direct", 4
                )


class PublicationEligibilityTests(unittest.TestCase):
    def setUp(self):
        self.git = {
            "repositories": {
                "top": {"commit": "a" * 40},
                "IMPICA": {"commit": "b" * 40},
            }
        }
        self.checkpoint = {
            "status": "schema_1_checkpoint_lineage_validated",
            "publication_eligible": True,
        }
        self.dataset = {
            "status": "supplied_strictly_validated_generation_transcript"
        }
        self.direct = {
            "strategy": "direct",
            "cpu_switch_used": False,
            "checkpoint_cpu_type": "timing",
            "checkpoint_restore_semantics": "same_cpu_class_direct_restore",
        }

    def evaluate(self, **changes):
        values = {
            "cpu_type": "timing",
            "restore_plan": self.direct,
            "checkpoint_provenance": self.checkpoint,
            "dataset_generation_record": self.dataset,
            "quick": False,
            "is_subset": False,
            "git_provenance": self.git,
        }
        values.update(changes)
        return GATE.evaluate_publication_eligibility(**values)

    def test_only_strict_direct_timing_matrix_is_eligible(self):
        self.assertTrue(self.evaluate()["eligible"])
        self.assertFalse(self.evaluate(cpu_type="atomic")["eligible"])
        self.assertFalse(self.evaluate(quick=True)["eligible"])
        self.assertFalse(self.evaluate(is_subset=True)["eligible"])
        self.assertFalse(
            self.evaluate(dataset_generation_record=None)["eligible"]
        )
        self.assertFalse(
            self.evaluate(
                restore_plan={"strategy": "switch", "cpu_switch_used": True}
            )["eligible"]
        )

    def test_atomic_checkpoint_fallback_is_not_publication_eligible(self):
        fallback = dict(self.direct)
        fallback.update(
            checkpoint_cpu_type="atomic",
            checkpoint_restore_semantics=(
                "atomic_architectural_checkpoint_state_restored_directly_into_"
                "TimingSimpleCPU"
            ),
        )
        result = self.evaluate(restore_plan=fallback)
        self.assertFalse(result["eligible"])
        self.assertIn(
            "same_class_timing_checkpoint", result["ineligible_reasons"]
        )

    def test_invalid_commit_is_ineligible(self):
        invalid = {
            "repositories": {
                "top": {"commit": "unavailable"},
                "IMPICA": {"commit": "b" * 40},
            }
        }
        result = self.evaluate(git_provenance=invalid)
        self.assertFalse(result["eligible"])
        self.assertIn(
            "valid_top_and_impica_commits", result["ineligible_reasons"]
        )


class GuestArtifactAttestationTests(unittest.TestCase):
    def test_atomic_preflight_hashes_each_unique_guest_input_once(self):
        workload_hash = "a" * 64
        driver_hash = "b" * 64
        first_hash = "c" * 64
        second_hash = "d" * 64
        cases = [
            {"dataset": Path("first.bin"), "input_sha256": first_hash},
            {"dataset": Path("first.bin"), "input_sha256": first_hash},
            {"dataset": Path("second.bin"), "input_sha256": second_hash},
        ]
        with tempfile.TemporaryDirectory() as temporary:
            raw = Path(temporary)

            def fake_run(command, env):
                out = Path(env["OUTDIR"])
                out.mkdir(parents=True)
                write_config(out / "config.ini", "AtomicSimpleCPU", "atomic")
                (out / "system.terminal").write_text(
                    "GUEST_ATTEST_WORKLOAD sha256=" + workload_hash
                    + " GUEST_ATTEST_DRIVER sha256=" + driver_hash + "\n"
                    + "GUEST_ATTEST_DATASET path=data/matrix/first.bin sha256="
                    + first_hash + "\n"
                    + "GUEST_ATTEST_DATASET path=data/matrix/second.bin sha256="
                    + second_hash + "\n",
                    encoding="utf-8",
                )

            with mock.patch.object(GATE, "run", side_effect=fake_run) as runner:
                record = GATE.run_guest_artifact_attestation(
                    raw_dir=raw,
                    checkpoint_arg="results/checkpoint",
                    checkpoint_index=2,
                    checkpoint_cpu={"cpu_type": "timing", "num_cpus": 4},
                    dataset_id="matrix",
                    cases=cases,
                    expected_guest_sha256=workload_hash,
                    expected_driver_sha256=driver_hash,
                )
        runner.assert_called_once()
        self.assertEqual(record["status"], "pass")
        self.assertEqual(record["unique_dataset_files"], 2)
        self.assertEqual(
            record["cpu_configuration"]["checkpoint_restore_semantics"],
            "timing_architectural_checkpoint_state_restored_directly_into_AtomicSimpleCPU",
        )


class GitProvenanceTests(unittest.TestCase):
    def initialize_repo(self, path, name):
        subprocess.run(["git", "init", "-q", path], check=True)
        subprocess.run(
            ["git", "-C", path, "config", "user.email", "test@example.invalid"],
            check=True,
        )
        subprocess.run(
            ["git", "-C", path, "config", "user.name", "Native Gate Test"],
            check=True,
        )
        tracked = Path(path) / f"{name}.txt"
        tracked.write_text("initial\n", encoding="utf-8")
        subprocess.run(["git", "-C", path, "add", tracked.name], check=True)
        subprocess.run(
            ["git", "-C", path, "commit", "-q", "-m", "initial"], check=True
        )
        return tracked

    def test_digest_binds_tracked_diff_and_untracked_paths(self):
        with tempfile.TemporaryDirectory() as temporary:
            top = Path(temporary) / "top"
            nested = Path(temporary) / "nested"
            top.mkdir()
            nested.mkdir()
            tracked = self.initialize_repo(top, "top")
            self.initialize_repo(nested, "nested")
            repos = (("top", top), ("IMPICA", nested))
            clean = GATE.collect_git_provenance(repos)
            tracked.write_text("changed\n", encoding="utf-8")
            dirty = GATE.collect_git_provenance(repos)
            self.assertNotEqual(
                clean["source_diff_digest"], dirty["source_diff_digest"]
            )
            (nested / "untracked file.txt").write_text("x", encoding="utf-8")
            untracked = GATE.collect_git_provenance(repos)
            self.assertNotEqual(
                dirty["source_diff_digest"], untracked["source_diff_digest"]
            )
            self.assertEqual(
                untracked["repositories"]["IMPICA"]["untracked_path_count"], 1
            )

    def test_git_uses_command_local_safe_directory(self):
        completed = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=b"ok\n", stderr=b""
        )
        with mock.patch.object(GATE.subprocess, "run", return_value=completed) as run:
            output = GATE.git_bytes(Path("/tmp/native gate repo"), "status")
        command = run.call_args.args[0]
        self.assertEqual(command[:3], ["git", "-c", "safe.directory=/tmp/native gate repo"])
        self.assertNotIn("--global", command)
        self.assertEqual(output, b"ok\n")

    def test_git_failure_is_fatal(self):
        completed = subprocess.CompletedProcess(
            args=[], returncode=128, stdout=b"", stderr=b"unsafe repository"
        )
        with mock.patch.object(GATE.subprocess, "run", return_value=completed):
            with self.assertRaisesRegex(RuntimeError, "Git provenance command failed"):
                GATE.git_bytes(Path("/tmp/repo"), "status")


class ContainerWrapperTests(unittest.TestCase):
    def test_disk_image_is_one_explicit_translated_environment_argument(self):
        with tempfile.TemporaryDirectory() as temporary:
            temporary = Path(temporary)
            fake_bin = temporary / "bin"
            fake_bin.mkdir()
            capture = temporary / "argv.txt"
            docker = fake_bin / "docker"
            docker.write_text(
                "#!/usr/bin/env bash\n"
                "if [[ $1 == info ]]; then exit 0; fi\n"
                "if [[ $1 == image && $2 == inspect ]]; then exit 0; fi\n"
                "printf '%s\\n' \"$@\" > \"$CAPTURE\"\n",
                encoding="utf-8",
            )
            docker.chmod(0o755)
            disk = ROOT / "third_party" / "disk with spaces;$(not-executed).img"
            environment = os.environ.copy()
            environment.update(
                {
                    "PATH": f"{fake_bin}:{environment['PATH']}",
                    "CAPTURE": str(capture),
                    "DISK_IMAGE": str(disk),
                    "EVIL_UNRELATED_ENV": "must-not-be-forwarded",
                    "IMAGE_NAME": "test-image",
                }
            )
            subprocess.run(
                [
                    "bash",
                    "-c",
                    "source scripts/_common.sh; "
                    "maybe_reexec_in_container always scripts/run_native_e2e_gate.sh "
                    "--quick",
                ],
                cwd=ROOT,
                env=environment,
                check=True,
            )
            arguments = capture.read_text(encoding="utf-8").splitlines()
            self.assertIn(
                "DISK_IMAGE=/workspace/third_party/"
                "disk with spaces;$(not-executed).img",
                arguments,
            )
            self.assertFalse(
                any("EVIL_UNRELATED_ENV" in argument for argument in arguments)
            )


if __name__ == "__main__":
    unittest.main()
