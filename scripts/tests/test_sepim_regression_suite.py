import csv
import importlib.util
import math
from pathlib import Path
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "run_sepim_regression_suite.py"
SPEC = importlib.util.spec_from_file_location("run_sepim_regression_suite", SCRIPT)
suite = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(suite)


SHA = "a" * 64


def terminal_with_csv(case_dir, artifact, header, rows):
    case_dir.mkdir(parents=True)
    path = case_dir / "system.terminal"
    lines = [
        f"REGRESSION_ARTIFACT_SHA256 {artifact}={SHA}",
        "FSCSV_BEGIN",
        ",".join(header),
    ]
    lines.extend(",".join(str(value) for value in row) for row in rows)
    lines.extend(["FSCSV_END", f"REGRESSION_CASE_PASS {artifact}"])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def write_trace(path, rows):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=suite.TRACE_CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


class PlanTests(unittest.TestCase):
    def test_quick_and_full_case_sets_are_exact(self):
        self.assertEqual(2, suite.SCHEMA_VERSION)
        self.assertEqual(
            list(suite.EXPECTED_QUICK_CASE_IDS),
            [record["id"] for record in suite.planned_cases("quick")],
        )
        self.assertEqual(
            list(suite.EXPECTED_FULL_CASE_IDS),
            [record["id"] for record in suite.planned_cases("full")],
        )
        self.assertEqual(
            list(suite.EXPECTED_FULL_CASE_IDS),
            [record["id"] for record in suite.case_specs("full")],
        )
        kmeans = suite.case_specs("full")[-1]
        self.assertEqual("./kmeans_sepim_fs", kmeans["guest_command"].split(" ||", 1)[0])
        self.assertEqual(
            "--cpu-type=timing --restore-with-cpu=timing",
            suite.restore_cpu_options("trace"),
        )

    def test_promotability_requires_full_pinned_immutable_exact_pass(self):
        commands = [{"network": "none"}]
        base = {
            "mode": "full",
            "status": "passed",
            "network": "none",
            "commands": commands,
            "container_image": {
                "requested_reference_pinned": True,
                "image_id": "sha256:" + "b" * 64,
            },
            "source_evidence_immutable": True,
            "runtime_inputs_immutable": True,
            "injected_artifacts_immutable": True,
            "legacy_dma_event_coverage": {"status": "incomplete"},
            "cases": [
                {"id": case_id, "pass": True}
                for case_id in suite.EXPECTED_FULL_CASE_IDS
            ],
        }
        self.assertTrue(suite.evaluate_promotability(base)["eligible"])
        base["mode"] = "quick"
        base["cases"] = [
            {"id": case_id, "pass": True}
            for case_id in suite.EXPECTED_QUICK_CASE_IDS
        ]
        self.assertFalse(suite.evaluate_promotability(base)["eligible"])


class CsvValidationTests(unittest.TestCase):
    def test_full_dma_and_controlled_matrices(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            dma_header = [
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
            dma_rows = []
            for access_mode in ("seq_read", "seq_write", "rand_read", "rand_write"):
                for size in (512, 1024, 2048, 4096, 8192):
                    dma_rows.append(
                        [access_mode, size, 1000, 10, 11, 2, 1.8, 10, 32]
                    )
            path = terminal_with_csv(
                root / "dma", "dma_benchmark_fs", dma_header, dma_rows
            )
            result = suite.parse_dma_terminal(path, SHA, mode="full")
            self.assertEqual(1000, result["transfers_per_row"])
            self.assertEqual(20, result["rows"])

            controlled_header = [
                "block_kb",
                "normal_mbps",
                "controlled_mbps",
                "path_oram_mbps",
            ]
            blocks = [1, 2, 4, 8, 16, 32, 64, 128]
            path = terminal_with_csv(
                root / "controlled",
                "controlled_access_bench_fs",
                controlled_header,
                [[block, 1300, 100, 0.7] for block in blocks],
            )
            result = suite.parse_controlled_terminal(path, SHA, mode="full")
            self.assertEqual(blocks, result["blocks_kib"])

    def test_legacy_kmeans_exact_matrix_and_formulas(self):
        header = [
            "dataset_mb",
            "pim_cores",
            "cpu_sec",
            "pim_baseline_sec",
            "sepim_sec",
            "overhead_pct",
            "speedup_vs_cpu",
        ]
        rows = []
        for dataset_mb in (64, 128, 256, 512):
            for cores in (1, 2, 4, 8):
                bytes_per_op = 1024 + 80 * (cores - 1)
                operations = (dataset_mb * 3000) // cores
                base_cycles = 90000 + (bytes_per_op * 13) // 10
                sepim_cycles = base_cycles + (bytes_per_op + 15) // 16
                cpu = 63.5 * dataset_mb / 512.0
                pim = base_cycles * operations / 1.0e9
                sepim = sepim_cycles * operations / 1.0e9
                overhead = (sepim - pim) * 100.0 / pim
                speedup = cpu / sepim
                rows.append(
                    [
                        dataset_mb,
                        cores,
                        f"{cpu:.4f}",
                        f"{pim:.4f}",
                        f"{sepim:.4f}",
                        f"{overhead:.4f}",
                        f"{speedup:.4f}",
                    ]
                )
        with tempfile.TemporaryDirectory() as temp:
            path = terminal_with_csv(
                Path(temp) / "kmeans", "kmeans_sepim_fs", header, rows
            )
            result = suite.parse_kmeans_legacy_terminal(path, SHA)
            self.assertEqual(16, result["rows"])
            self.assertEqual("legacy_extrapolated_mmio_model", result["model_kind"])
            self.assertFalse(result["direct_end_to_end_measurement"])


class TraceValidationTests(unittest.TestCase):
    def test_trace_run_requires_direct_timing_cpu_graph(self):
        config = """
[system]
mem_mode=timing
mem_ranges=0:2147483647
[system.cpu0]
type=TimingSimpleCPU
[system.cpu1]
type=TimingSimpleCPU
[system.cpu2]
type=TimingSimpleCPU
[system.cpu3]
type=TimingSimpleCPU
"""
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "config.ini"
            path.write_text(config, encoding="utf-8")
            result = suite.validate_trace_timing_config(path)
            self.assertEqual("timing", result["mem_mode"])
            self.assertFalse(result["cpu_switch_used"])
            self.assertTrue(result["comm_monitor_capture_capable"])

    def test_trace_topology_requires_both_enabled_monitors(self):
        config = """
[system.sepim_trace_monitor]
type=CommMonitor
trace_enable=true
trace_file=/tmp/main.ptrc
[system.sepim_trace_monitor_io]
type=CommMonitor
trace_enable=true
trace_file=/tmp/main.ptrc.io
"""
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "config.ini"
            path.write_text(config, encoding="utf-8")
            result = suite.validate_trace_topology(path)
            self.assertEqual("primary", result["main_trace_role"])
            self.assertTrue(all(result["trace_enabled"].values()))

    def test_cpu_and_sepim_primary_tail_validation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            cpu_rows = []
            for index in range(suite.TRACE_TAIL_PACKETS):
                cpu_rows.append(
                    {
                        "time": str(index),
                        "addr": f"0x{0x80000000 + (index % 256) * 64:x}",
                        "rw": "R" if index % 3 else "W",
                        "size": "64",
                        "cmd": "1" if index % 3 else "4",
                        "flags": "0",
                    }
                )
            cpu_path = root / "cpu.csv"
            write_trace(cpu_path, cpu_rows)
            result = suite.validate_trace_csv(cpu_path, "cpu")
            self.assertGreaterEqual(result["unique_addresses"], 64)

            sepim_rows = []
            required = suite.REQUIRED_SEPIM_MMIO_OFFSETS
            for index in range(suite.TRACE_TAIL_PACKETS):
                if index < 600:
                    offset = required[index % len(required)]
                    rw = "R" if offset == 0x44 else "W"
                    address = suite.PIM_MMIO_BASE + offset
                    size = 4
                else:
                    rw = "R"
                    address = 0x80000000 + index * 64
                    size = 64
                sepim_rows.append(
                    {
                        "time": str(index),
                        "addr": f"0x{address:x}",
                        "rw": rw,
                        "size": str(size),
                        "cmd": "1" if rw == "R" else "4",
                        "flags": "0",
                    }
                )
            sepim_path = root / "sepim.csv"
            write_trace(sepim_path, sepim_rows)
            result = suite.validate_trace_csv(sepim_path, "sepim")
            self.assertEqual(600, result["sepim_mmio"]["observed_rows"])
            self.assertEqual("primary", result["role"])

    def test_nonmonotonic_trace_is_rejected(self):
        rows = []
        for index in range(suite.TRACE_TAIL_PACKETS):
            tick = index if index != 10 else 0
            rows.append(
                {
                    "time": str(tick),
                    "addr": f"0x{0x80000000 + index * 64:x}",
                    "rw": "R",
                    "size": "64",
                    "cmd": "1",
                    "flags": "0",
                }
            )
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "bad.csv"
            write_trace(path, rows)
            with self.assertRaisesRegex(suite.RegressionError, "monotonic"):
                suite.validate_trace_csv(path, "cpu")

    def test_empty_decoded_io_trace_is_valid_auxiliary_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "io.csv"
            write_trace(path, [])
            result = suite.validate_trace_csv(
                path, "auxiliary", require_exact_tail=False
            )
            self.assertEqual(0, result["rows"])
            self.assertEqual("auxiliary", result["role"])


if __name__ == "__main__":
    unittest.main()
