"""
Benchmark Harness and Execution Engine.
Orchestrates loading, execution through DocumentExtractionService,
evaluation, aggregate metric calculation, and report generation.
"""

import os
import json
import time
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple

from app.service import DocumentExtractionService
from .models import (
    BenchmarkFixture,
    GroundTruth,
    FixtureEvaluationResult,
    FormatSummary,
    BenchmarkReport,
)
from .evaluator import evaluate_fixture
from .generator import generate_all_fixtures, save_fixtures_to_disk


class BenchmarkHarness:
    """
    Orchestrates the execution of document extraction benchmarks.
    Enforces deterministic fixture discovery, integrity checks,
    and unbiased per-format/per-scenario reporting.
    """

    def __init__(self, service: Optional[DocumentExtractionService] = None):
        self.service = service or DocumentExtractionService()
        self.fixtures: List[Tuple[BenchmarkFixture, GroundTruth]] = []
        self._validated = False

    def load_from_generator(self) -> None:
        """Loads fixtures directly from the deterministic generator."""
        self.fixtures = generate_all_fixtures()
        self.validate_manifest()

    def load_from_disk(self, benchmark_dir: str = "benchmark") -> None:
        """Loads fixtures and ground truth JSON files from disk."""
        fixtures_dir = os.path.join(benchmark_dir, "fixtures")
        gt_dir = os.path.join(benchmark_dir, "ground_truth")

        if not os.path.exists(fixtures_dir) or not os.path.exists(gt_dir):
            # If not yet generated on disk, generate them first
            self.fixtures = save_fixtures_to_disk(benchmark_dir)
            self.validate_manifest()
            return

        loaded_items: List[Tuple[BenchmarkFixture, GroundTruth]] = []
        for gt_filename in sorted(os.listdir(gt_dir)):
            if not gt_filename.endswith(".json"):
                continue
            gt_path = os.path.join(gt_dir, gt_filename)
            with open(gt_path, "r", encoding="utf-8") as f:
                gt_data = json.load(f)
            gt = GroundTruth.from_dict(gt_data)

            fix_path = os.path.join(fixtures_dir, gt.filename)
            if not os.path.exists(fix_path):
                raise FileNotFoundError(
                    f"Fixture binary file missing for ground truth {gt.fixture_id}: {fix_path}"
                )

            with open(fix_path, "rb") as f:
                raw_bytes = f.read()

            fix = BenchmarkFixture(
                fixture_id=gt.fixture_id,
                filename=gt.filename,
                format=gt.format,
                category=gt.category,
                scenario=gt.scenario,
                raw_bytes=raw_bytes,
                file_path=fix_path,
            )
            loaded_items.append((fix, gt))

        self.fixtures = loaded_items
        self.validate_manifest()

    def validate_manifest(self) -> None:
        """
        Validates manifest completeness and uniqueness of fixture IDs.
        Raises ValueError on duplicate fixture IDs or malformed manifest.
        """
        seen_ids = set()
        for fix, gt in self.fixtures:
            if fix.fixture_id != gt.fixture_id:
                raise ValueError(
                    f"Fixture ID mismatch: fixture={fix.fixture_id}, ground_truth={gt.fixture_id}"
                )
            if fix.fixture_id in seen_ids:
                raise ValueError(f"Duplicate fixture ID detected: '{fix.fixture_id}'")
            seen_ids.add(fix.fixture_id)

            if not gt.format:
                raise ValueError(f"Fixture '{fix.fixture_id}' is missing format specification")
            if not gt.expected_status:
                raise ValueError(f"Fixture '{fix.fixture_id}' is missing expected_status")

        self._validated = True

    def run(self, format_filter: Optional[str] = None) -> BenchmarkReport:
        """
        Executes each fixture through DocumentExtractionService, evaluates output,
        and constructs the BenchmarkReport.
        """
        if not self._validated:
            self.validate_manifest()

        items = self.fixtures
        if format_filter:
            items = [item for item in items if item[0].format.lower() == format_filter.lower()]

        results: List[FixtureEvaluationResult] = []
        start_total = time.perf_counter()

        for fix, gt in items:
            t0 = time.perf_counter()
            extraction_result = self.service.extract_bytes(fix.raw_bytes, fix.filename)
            duration_ms = (time.perf_counter() - t0) * 1000.0

            eval_res = evaluate_fixture(extraction_result, gt, execution_time_ms=duration_ms)
            results.append(eval_res)

        total_duration_ms = (time.perf_counter() - start_total) * 1000.0

        return self._build_report(results, total_duration_ms)

    def _build_report(
        self,
        results: List[FixtureEvaluationResult],
        total_duration_ms: float,
    ) -> BenchmarkReport:
        """Aggregates individual fixture results into format and scenario summaries."""
        total_fixtures = len(results)
        passed_fixtures = sum(1 for r in results if r.passed)
        failed_fixtures = total_fixtures - passed_fixtures
        overall_pass_rate = (passed_fixtures / total_fixtures) if total_fixtures > 0 else 0.0

        # Calculate overall CAR and CER across only applicable text fixtures
        text_applicable_results = [r for r in results if r.text_applicable and r.car is not None]
        total_text_applicable = len(text_applicable_results)

        overall_car = (
            sum(r.car for r in text_applicable_results) / total_text_applicable
            if total_text_applicable > 0 else None
        )
        overall_cer = (
            sum(r.cer for r in text_applicable_results if r.cer is not None) / total_text_applicable
            if total_text_applicable > 0 else None
        )

        overall_verdict = "PASSED" if failed_fixtures == 0 else "FAILED"

        # Format summaries
        format_groups: Dict[str, List[FixtureEvaluationResult]] = {}
        for r in results:
            format_groups.setdefault(r.format, []).append(r)

        format_summaries: Dict[str, FormatSummary] = {}
        for fmt, f_results in sorted(format_groups.items()):
            fmt_total = len(f_results)
            fmt_passed = sum(1 for r in f_results if r.passed)
            fmt_failed = fmt_total - fmt_passed
            fmt_pass_rate = fmt_passed / fmt_total if fmt_total > 0 else 0.0

            fmt_text_res = [r for r in f_results if r.text_applicable and r.car is not None]
            fmt_text_count = len(fmt_text_res)
            fmt_mean_car = (sum(r.car for r in fmt_text_res) / fmt_text_count) if fmt_text_count > 0 else None
            fmt_mean_cer = (sum(r.cer for r in fmt_text_res if r.cer is not None) / fmt_text_count) if fmt_text_count > 0 else None

            fmt_struct_passes = sum(1 for r in f_results if r.structure_match)
            fmt_mean_struct = sum(r.structural_score for r in f_results) / fmt_total if fmt_total > 0 else 1.0
            fmt_warns_passed = sum(1 for r in f_results if r.warnings_passed)
            fmt_mean_time = sum(r.execution_time_ms for r in f_results) / fmt_total if fmt_total > 0 else 0.0
            failed_ids = [r.fixture_id for r in f_results if not r.passed]

            format_summaries[fmt] = FormatSummary(
                format=fmt,
                total_fixtures=fmt_total,
                passed_fixtures=fmt_passed,
                failed_fixtures=fmt_failed,
                pass_rate=round(fmt_pass_rate, 4),
                text_applicable_count=fmt_text_count,
                mean_car=round(fmt_mean_car, 4) if fmt_mean_car is not None else None,
                mean_cer=round(fmt_mean_cer, 4) if fmt_mean_cer is not None else None,
                exact_structure_pass_count=fmt_struct_passes,
                mean_structural_score=round(fmt_mean_struct, 4),
                warnings_passed_count=fmt_warns_passed,
                mean_execution_time_ms=round(fmt_mean_time, 2),
                failed_fixture_ids=failed_ids,
            )

        # Scenario metrics
        scenario_groups: Dict[str, List[FixtureEvaluationResult]] = {}
        for r in results:
            scenario_groups.setdefault(r.scenario, []).append(r)

        scenario_metrics: Dict[str, Dict[str, Any]] = {}
        for scn, s_results in scenario_groups.items():
            s_total = len(s_results)
            s_passed = sum(1 for r in s_results if r.passed)
            scenario_metrics[scn] = {
                "total": s_total,
                "passed": s_passed,
                "failed": s_total - s_passed,
                "pass_rate": round(s_passed / s_total, 4) if s_total > 0 else 0.0,
            }

        return BenchmarkReport(
            total_fixtures=total_fixtures,
            passed_fixtures=passed_fixtures,
            failed_fixtures=failed_fixtures,
            overall_pass_rate=round(overall_pass_rate, 4),
            total_text_applicable=total_text_applicable,
            overall_car=round(overall_car, 4) if overall_car is not None else None,
            overall_cer=round(overall_cer, 4) if overall_cer is not None else None,
            overall_verdict=overall_verdict,
            format_summaries=format_summaries,
            scenario_metrics=scenario_metrics,
            results=results,
            execution_time_ms=round(total_duration_ms, 2),
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    @staticmethod
    def format_console_summary(report: BenchmarkReport) -> str:
        """Generates a structured, concise console summary from the BenchmarkReport."""
        lines = []
        lines.append("=" * 78)
        lines.append("DOCUMENT EXTRACTION BENCHMARK EVALUATION REPORT (PHASE 2B)")
        lines.append("=" * 78)
        lines.append(f"Timestamp:       {report.timestamp}")
        lines.append(f"Total Fixtures:  {report.total_fixtures}")
        lines.append(f"Passed:          {report.passed_fixtures}")
        lines.append(f"Failed:          {report.failed_fixtures}")
        lines.append(f"Overall Pass %:  {report.overall_pass_rate * 100:.1f}%")
        car_str = f"{report.overall_car * 100:.2f}% (over {report.total_text_applicable} text fixtures)" if report.overall_car is not None else "N/A"
        cer_str = f"{report.overall_cer:.4f}" if report.overall_cer is not None else "N/A"
        lines.append(f"Overall Mean CAR:{car_str}")
        lines.append(f"Overall Mean CER:{cer_str}")
        lines.append(f"Total Execution: {report.execution_time_ms:.2f} ms (informational timing)")
        lines.append(f"Verdict:         {report.overall_verdict}")
        lines.append("-" * 78)
        lines.append(f"{'Format':<8} | {'Total':<6} | {'Pass':<5} | {'Fail':<5} | {'Pass %':<7} | {'Mean CAR':<9} | {'Mean CER':<9} | {'Struct %':<8}")
        lines.append("-" * 78)

        for fmt, summ in sorted(report.format_summaries.items()):
            car_val = f"{summ.mean_car * 100:.1f}%" if summ.mean_car is not None else "N/A"
            cer_val = f"{summ.mean_cer:.4f}" if summ.mean_cer is not None else "N/A"
            struct_pct = f"{summ.mean_structural_score * 100:.1f}%"
            lines.append(
                f"{fmt.upper():<8} | {summ.total_fixtures:<6} | {summ.passed_fixtures:<5} | {summ.failed_fixtures:<5} | "
                f"{summ.pass_rate * 100:>5.1f}% | {car_val:<9} | {cer_val:<9} | {struct_pct:<8}"
            )

        lines.append("-" * 78)

        if report.failed_fixtures > 0:
            lines.append("\nFAILED FIXTURES AND ACTIONABLE MISMATCH DETAILS:")
            lines.append("-" * 78)
            for r in report.results:
                if not r.passed:
                    lines.append(f"❌ [{r.fixture_id}] ({r.format.upper()}) Scenario: {r.scenario}")
                    lines.append(f"   Status: actual={r.actual_status}, expected={r.expected_status}")
                    if r.actual_error_code or r.expected_error_code:
                        lines.append(f"   Error: actual={r.actual_error_code}, expected={r.expected_error_code}")
                    for reason in r.failure_reasons:
                        lines.append(f"   - {reason}")
                    lines.append("")
        else:
            lines.append("\n✅ ALL REGISTERED BENCHMARK FIXTURES PASSED EVALUATION.")

        lines.append("=" * 78)
        lines.append("Note: Timing is informational only; not a performance SLA.")
        lines.append("=" * 78)
        return "\n".join(lines)
