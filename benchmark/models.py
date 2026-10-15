"""
Data models and contracts for Benchmark Fixtures, Ground Truth, and Evaluation Results.
"""

from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional


@dataclass
class BenchmarkFixture:
    """Represents a test file fixture in the benchmark corpus."""
    fixture_id: str
    filename: str
    format: str
    category: str
    scenario: str
    raw_bytes: bytes
    file_path: Optional[str] = None


@dataclass
class GroundTruth:
    """Expected evaluation expectations and structural contracts for a fixture."""
    fixture_id: str
    filename: str
    format: str
    category: str
    scenario: str
    expected_status: str
    accepted_statuses: List[str] = field(default_factory=list)
    expected_error_code: Optional[str] = None
    allow_any_error_code: bool = False
    expected_warnings: List[str] = field(default_factory=list)
    forbidden_warnings: List[str] = field(default_factory=list)
    expected_text: str = ""
    text_applicable: Optional[bool] = None
    expected_blocks: List[Dict[str, Any]] = field(default_factory=list)
    expected_metadata: Dict[str, Any] = field(default_factory=dict)
    provisional_thresholds: Dict[str, Any] = field(default_factory=lambda: {
        "max_cer": 0.00,
        "min_car": 1.00,
        "require_exact_structure": True,
    })
    threshold_rationale: Optional[str] = None
    known_unsupported_content: Optional[str] = None

    def __post_init__(self):
        if not self.accepted_statuses and self.expected_status:
            self.accepted_statuses = [self.expected_status]
        if self.text_applicable is None:
            # By contract, negative/failed extractions do not evaluate text similarity
            self.text_applicable = (self.expected_status != "failed")

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GroundTruth":
        return cls(**data)


@dataclass
class FixtureEvaluationResult:
    """Evaluation output for an individual fixture run through extraction."""
    fixture_id: str
    format: str
    scenario: str
    passed: bool
    status_match: bool
    actual_status: str
    expected_status: str
    error_code_match: bool
    actual_error_code: Optional[str] = None
    expected_error_code: Optional[str] = None
    text_applicable: bool = True
    cer: Optional[float] = None
    car: Optional[float] = None
    levenshtein_distance: Optional[int] = None
    structure_match: bool = True
    structural_score: float = 1.0
    structure_mismatches: List[str] = field(default_factory=list)
    warnings_passed: bool = True
    missing_warnings: List[str] = field(default_factory=list)
    forbidden_warnings_found: List[str] = field(default_factory=list)
    metadata_match: bool = True
    metadata_mismatches: List[str] = field(default_factory=list)
    execution_time_ms: float = 0.0
    extracted_text_preview: str = ""
    expected_text_preview: str = ""
    failure_reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class FormatSummary:
    """Aggregate statistics for a specific file format."""
    format: str
    total_fixtures: int
    passed_fixtures: int
    failed_fixtures: int
    pass_rate: float
    text_applicable_count: int
    mean_car: Optional[float]
    mean_cer: Optional[float]
    exact_structure_pass_count: int
    mean_structural_score: float
    warnings_passed_count: int
    mean_execution_time_ms: float
    failed_fixture_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class BenchmarkReport:
    """Top-level evaluation report encompassing all formats and aggregate metrics."""
    total_fixtures: int
    passed_fixtures: int
    failed_fixtures: int
    overall_pass_rate: float
    total_text_applicable: int
    overall_car: Optional[float]
    overall_cer: Optional[float]
    overall_verdict: str  # "PASSED" or "DEFECTS_EXPOSED"
    format_summaries: Dict[str, FormatSummary]
    scenario_metrics: Dict[str, Dict[str, Any]]
    results: List[FixtureEvaluationResult]
    execution_time_ms: float
    timestamp: str

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["format_summaries"] = {
            k: v.to_dict() if hasattr(v, "to_dict") else v
            for k, v in self.format_summaries.items()
        }
        data["results"] = [
            r.to_dict() if hasattr(r, "to_dict") else r
            for r in self.results
        ]
        return data
