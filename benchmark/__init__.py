"""
Document Extraction Benchmark Harness and Evaluation Suite.
"""

from .models import (
    BenchmarkFixture,
    GroundTruth,
    FixtureEvaluationResult,
    BenchmarkReport,
    FormatSummary,
)
from .evaluator import (
    calculate_cer,
    calculate_car,
    calculate_levenshtein_distance,
    normalize_for_evaluation,
    evaluate_fixture,
)
from .harness import BenchmarkHarness
from .generator import generate_all_fixtures

__all__ = [
    "BenchmarkFixture",
    "GroundTruth",
    "FixtureEvaluationResult",
    "BenchmarkReport",
    "FormatSummary",
    "calculate_cer",
    "calculate_car",
    "calculate_levenshtein_distance",
    "normalize_for_evaluation",
    "evaluate_fixture",
    "BenchmarkHarness",
    "generate_all_fixtures",
]
