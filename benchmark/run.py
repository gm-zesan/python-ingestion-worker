"""
Benchmark CLI entrypoint.
Usage:
    python -m benchmark.run [--output-json REPORT_PATH] [--format FORMAT] [--regenerate-fixtures]
"""

import sys
import os
import argparse
import json

from .harness import BenchmarkHarness
from .generator import save_fixtures_to_disk


def parse_args():
    parser = argparse.ArgumentParser(
        description="Document Extraction Benchmark Runner (Phase 2B)"
    )
    parser.add_argument(
        "--output-json",
        type=str,
        default="benchmark_report.json",
        help="Destination path for machine-readable benchmark JSON report (default: benchmark_report.json)",
    )
    parser.add_argument(
        "--format",
        type=str,
        default=None,
        choices=["txt", "docx", "xlsx", "csv"],
        help="Optional filter to evaluate a specific format only",
    )
    parser.add_argument(
        "--benchmark-dir",
        type=str,
        default="benchmark",
        help="Base directory containing fixtures/ and ground_truth/ (default: benchmark)",
    )
    parser.add_argument(
        "--regenerate-fixtures",
        action="store_true",
        help="Force deterministic regeneration of fixture binaries and ground truth files before running",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    if args.regenerate_fixtures:
        print("Regenerating all fixtures deterministically to disk...")
        save_fixtures_to_disk(args.benchmark_dir)

    harness = BenchmarkHarness()
    try:
        harness.load_from_disk(args.benchmark_dir)
    except Exception as e:
        print(f"Error loading benchmark fixtures: {e}", file=sys.stderr)
        sys.exit(2)

    report = harness.run(format_filter=args.format)

    # Print human-readable console summary
    summary_text = BenchmarkHarness.format_console_summary(report)
    print(summary_text)

    # Save machine-readable JSON report
    if args.output_json:
        try:
            with open(args.output_json, "w", encoding="utf-8") as f:
                json.dump(report.to_dict(), f, indent=2, ensure_ascii=False)
            print(f"\nMachine-readable benchmark report saved to: {args.output_json}")
        except Exception as e:
            print(f"Failed to write JSON report to {args.output_json}: {e}", file=sys.stderr)

    # Exit non-zero if any required fixture failed
    if report.failed_fixtures > 0:
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
