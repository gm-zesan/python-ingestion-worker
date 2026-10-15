"""
Unit tests for Benchmark Harness, CLI runner, and Deterministic Generator.
Verifies manifest completeness, duplicate ID detection, deterministic hashing,
JSON report serialization, and CLI error exit codes.
"""

import os
import json
import tempfile
import hashlib
import unittest
import subprocess
import sys

from benchmark.models import BenchmarkFixture, GroundTruth, BenchmarkReport, FormatSummary
from benchmark.harness import BenchmarkHarness
from benchmark.generator import generate_all_fixtures, save_fixtures_to_disk


class TestBenchmarkHarness(unittest.TestCase):

    def test_manifest_validation_detects_duplicate_ids(self):
        harness = BenchmarkHarness()
        harness.fixtures = [
            (
                BenchmarkFixture(
                    fixture_id="DUP-01",
                    filename="dup1.txt",
                    format="txt",
                    category="cat",
                    scenario="scen",
                    raw_bytes=b"1",
                ),
                GroundTruth(
                    fixture_id="DUP-01",
                    filename="dup1.txt",
                    format="txt",
                    category="cat",
                    scenario="scen",
                    expected_status="success",
                )
            ),
            (
                BenchmarkFixture(
                    fixture_id="DUP-01",
                    filename="dup2.txt",
                    format="txt",
                    category="cat",
                    scenario="scen",
                    raw_bytes=b"2",
                ),
                GroundTruth(
                    fixture_id="DUP-01",
                    filename="dup2.txt",
                    format="txt",
                    category="cat",
                    scenario="scen",
                    expected_status="success",
                )
            ),
        ]
        with self.assertRaises(ValueError) as ctx:
            harness.validate_manifest()
        self.assertIn("Duplicate fixture ID detected", str(ctx.exception))

    def test_manifest_validation_detects_fixture_gt_id_mismatch(self):
        harness = BenchmarkHarness()
        harness.fixtures = [
            (
                BenchmarkFixture(
                    fixture_id="FIX-01",
                    filename="f.txt",
                    format="txt",
                    category="cat",
                    scenario="scen",
                    raw_bytes=b"1",
                ),
                GroundTruth(
                    fixture_id="GT-MISMATCH",
                    filename="f.txt",
                    format="txt",
                    category="cat",
                    scenario="scen",
                    expected_status="success",
                )
            )
        ]
        with self.assertRaises(ValueError) as ctx:
            harness.validate_manifest()
        self.assertIn("Fixture ID mismatch", str(ctx.exception))

    def test_missing_binary_fixture_raises_filenotfound(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            gt_dir = os.path.join(temp_dir, "ground_truth")
            fix_dir = os.path.join(temp_dir, "fixtures")
            os.makedirs(gt_dir)
            os.makedirs(fix_dir)

            gt = GroundTruth(
                fixture_id="MISSING-01",
                filename="missing.txt",
                format="txt",
                category="test",
                scenario="missing binary file",
                expected_status="success",
            )
            with open(os.path.join(gt_dir, "MISSING-01.json"), "w") as f:
                json.dump(gt.to_dict(), f)

            harness = BenchmarkHarness()
            with self.assertRaises(FileNotFoundError) as ctx:
                harness.load_from_disk(temp_dir)
            self.assertIn("Fixture binary file missing", str(ctx.exception))

    def test_json_report_serialization_and_deserialization(self):
        harness = BenchmarkHarness()
        harness.load_from_generator()
        report = harness.run(format_filter="txt")

        # Must serialize cleanly to dict and JSON
        report_dict = report.to_dict()
        json_str = json.dumps(report_dict, indent=2)
        deserialized = json.loads(json_str)

        self.assertIn("format_summaries", deserialized)
        self.assertIn("results", deserialized)
        self.assertIn("overall_verdict", deserialized)
        self.assertEqual(deserialized["overall_verdict"], "PASSED")
        self.assertIn("txt", deserialized["format_summaries"])
        self.assertEqual(deserialized["format_summaries"]["txt"]["total_fixtures"], 9)
        self.assertEqual(deserialized["format_summaries"]["txt"]["passed_fixtures"], 9)

    def test_deterministic_fixture_generation_across_runs(self):
        with tempfile.TemporaryDirectory() as dir1, tempfile.TemporaryDirectory() as dir2:
            save_fixtures_to_disk(dir1)
            save_fixtures_to_disk(dir2)

            f1 = sorted(os.listdir(os.path.join(dir1, "fixtures")))
            f2 = sorted(os.listdir(os.path.join(dir2, "fixtures")))
            self.assertEqual(f1, f2)
            self.assertEqual(len(f1), 45)

            for fname in f1:
                p1 = os.path.join(dir1, "fixtures", fname)
                p2 = os.path.join(dir2, "fixtures", fname)
                with open(p1, "rb") as fp1, open(p2, "rb") as fp2:
                    h1 = hashlib.sha256(fp1.read()).hexdigest()
                    h2 = hashlib.sha256(fp2.read()).hexdigest()
                self.assertEqual(
                    h1,
                    h2,
                    f"Generated fixture file '{fname}' hash differs across runs!",
                )

            gt1 = sorted(os.listdir(os.path.join(dir1, "ground_truth")))
            gt2 = sorted(os.listdir(os.path.join(dir2, "ground_truth")))
            self.assertEqual(gt1, gt2)
            self.assertEqual(len(gt1), 45)

            for fname in gt1:
                p1 = os.path.join(dir1, "ground_truth", fname)
                p2 = os.path.join(dir2, "ground_truth", fname)
                with open(p1, "rb") as fp1, open(p2, "rb") as fp2:
                    h1 = hashlib.sha256(fp1.read()).hexdigest()
                    h2 = hashlib.sha256(fp2.read()).hexdigest()
                self.assertEqual(
                    h1,
                    h2,
                    f"Generated ground truth file '{fname}' hash differs across runs!",
                )

    def test_cli_exit_code_zero_on_success(self):
        cmd = [sys.executable, "-m", "benchmark.run", "--format", "txt"]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, f"CLI exited non-zero on success: {proc.stderr}")
        self.assertIn("VERDICT:         PASSED", proc.stdout.upper())

    def test_cli_exit_code_non_zero_on_fixture_failure(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            gt_dir = os.path.join(temp_dir, "ground_truth")
            fix_dir = os.path.join(temp_dir, "fixtures")
            os.makedirs(gt_dir)
            os.makedirs(fix_dir)

            # Create a fixture that will fail extraction (e.g. wrong error code expected)
            with open(os.path.join(fix_dir, "failing.txt"), "wb") as f:
                f.write(b"")
            gt = GroundTruth(
                fixture_id="FAIL-01",
                filename="failing.txt",
                format="txt",
                category="test",
                scenario="failing expectation",
                expected_status="failed",
                expected_error_code="WRONG_ERROR_CODE",  # Actual is FILE_EMPTY
            )
            with open(os.path.join(gt_dir, "FAIL-01.json"), "w") as f:
                json.dump(gt.to_dict(), f)

            cmd = [sys.executable, "-m", "benchmark.run", "--benchmark-dir", temp_dir]
            proc = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(proc.returncode, 1, "CLI must exit with code 1 when a fixture fails")
            self.assertIn("VERDICT:         FAILED", proc.stdout.upper())


if __name__ == "__main__":
    unittest.main()
