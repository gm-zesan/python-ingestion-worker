"""
Evaluation engine for Document Extraction Benchmark.
Computes Character Error Rate (CER), Character Accuracy Rate (CAR),
structural fidelity, status adherence, and warning validation.
"""

import unicodedata
from typing import Tuple, List, Dict, Any, Optional

from app.contracts import ExtractionResult, ExtractionStatus, BlockType
from .models import GroundTruth, FixtureEvaluationResult


def normalize_for_evaluation(text: Optional[str]) -> str:
    """
    Normalizes text for benchmark comparison.
    Policy:
    - Normalizes Unicode to Canonical Composition (NFC).
    - Unifies carriage returns and newlines (\\r\\n and \\r -> \\n).
    - Trims line-level trailing whitespace while preserving line structure.
    - Explicitly PRESERVES all Bengali script characters (U+0980..U+09FF)
      including Zero Width Joiner (ZWJ U+200D) and Zero Width Non-Joiner (ZWNJ U+200C).
    """
    if not text:
        return ""

    # 1. Unicode NFC
    normalized = unicodedata.normalize("NFC", text)

    # 2. Line ending unification
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")

    # 3. Strip trailing whitespace per line and overall boundaries
    lines = [line.strip() for line in normalized.split("\n")]
    
    # Filter empty lines at edges while keeping paragraph breaks
    return "\n".join(lines).strip()


def calculate_levenshtein_distance(s1: str, s2: str) -> int:
    """
    Computes exact Levenshtein edit distance between two strings using
    space-optimized dynamic programming (O(min(M, N)) auxiliary memory).
    """
    if s1 == s2:
        return 0
    if len(s1) < len(s2):
        s1, s2 = s2, s1
    if len(s2) == 0:
        return len(s1)

    prev_row = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        curr_row = [i + 1] * (len(s2) + 1)
        for j, c2 in enumerate(s2):
            insertions = prev_row[j + 1] + 1
            deletions = curr_row[j] + 1
            substitutions = prev_row[j] + (0 if c1 == c2 else 1)
            curr_row[j + 1] = min(insertions, deletions, substitutions)
        prev_row = curr_row

    return prev_row[len(s2)]


def calculate_cer(extracted_text: str, ground_truth_text: str) -> Tuple[float, int]:
    """
    Calculates Character Error Rate (CER) and raw edit distance:
    CER = Levenshtein(extracted, ground_truth) / max(len(ground_truth), 1)
    Returns (cer, distance).
    """
    norm_extracted = normalize_for_evaluation(extracted_text)
    norm_gt = normalize_for_evaluation(ground_truth_text)

    if norm_extracted == norm_gt:
        return 0.0, 0

    if not norm_gt:
        # Ground truth was empty but extracted text is not
        return 1.0, len(norm_extracted)

    distance = calculate_levenshtein_distance(norm_extracted, norm_gt)
    cer = distance / len(norm_gt)
    return cer, distance


def calculate_car(cer: float) -> float:
    """
    Calculates Character Accuracy Rate:
    CAR = max(0.0, 1.0 - CER)
    """
    return max(0.0, 1.0 - cer)


def evaluate_structural_correctness(
    actual_blocks: List[Any],
    expected_blocks: List[Dict[str, Any]],
) -> Tuple[bool, float, List[str]]:
    """
    Compares extracted blocks with ground-truth expected blocks.
    Checks:
    - Block types (heading, paragraph, table, worksheet)
    - Heading levels (h1, h2, etc.)
    - Table headers, row count, column count
    Returns (is_match, score, list_of_mismatches).
    """
    if not expected_blocks:
        return True, 1.0, []

    mismatches: List[str] = []
    total_checks = 0
    passed_checks = 0

    # 1. Block count check
    total_checks += 1
    if len(actual_blocks) != len(expected_blocks):
        mismatches.append(f"Block count mismatch: expected {len(expected_blocks)}, got {len(actual_blocks)}")
    else:
        passed_checks += 1

    min_len = min(len(actual_blocks), len(expected_blocks))
    for i in range(min_len):
        act = actual_blocks[i]
        exp = expected_blocks[i]

        act_type = act.block_type.value if hasattr(act.block_type, "value") else str(act.block_type)
        exp_type = exp.get("block_type", "").lower()

        # Check block type
        total_checks += 1
        if act_type.lower() != exp_type:
            mismatches.append(f"Block [{i+1}] type mismatch: expected '{exp_type}', got '{act_type}'")
        else:
            passed_checks += 1

        # Check heading level
        if exp_type == "heading" and "level" in exp:
            total_checks += 1
            act_level = getattr(act, "level", None)
            if act_level != exp["level"]:
                mismatches.append(f"Block [{i+1}] heading level mismatch: expected {exp['level']}, got {act_level}")
            else:
                passed_checks += 1

        # Check table headers and dimensions
        if exp_type == "table":
            if "headers" in exp:
                total_checks += 1
                act_headers = getattr(act, "headers", [])
                if act_headers != exp["headers"]:
                    mismatches.append(f"Block [{i+1}] table headers mismatch: expected {exp['headers']}, got {act_headers}")
                else:
                    passed_checks += 1

            if "row_count" in exp:
                total_checks += 1
                act_rows = getattr(act, "rows", [])
                if len(act_rows) != exp["row_count"]:
                    mismatches.append(f"Block [{i+1}] table row count mismatch: expected {exp['row_count']}, got {len(act_rows)}")
                else:
                    passed_checks += 1

    structural_score = passed_checks / max(total_checks, 1)
    is_match = (len(mismatches) == 0)
    return is_match, structural_score, mismatches


def evaluate_warnings(
    actual_warnings: List[str],
    expected_warnings: List[str],
    forbidden_warnings: List[str],
) -> Tuple[bool, List[str], List[str]]:
    """
    Validates expected and forbidden warning substrings.
    """
    missing_warnings: List[str] = []
    forbidden_found: List[str] = []

    actual_combined = " ".join(actual_warnings).lower()

    for exp_w in expected_warnings:
        if exp_w.lower() not in actual_combined:
            missing_warnings.append(exp_w)

    for forb_w in forbidden_warnings:
        if forb_w.lower() in actual_combined:
            forbidden_found.append(forb_w)

    passed = (len(missing_warnings) == 0 and len(forbidden_found) == 0)
    return passed, missing_warnings, forbidden_found


def evaluate_metadata(
    actual_metadata: Dict[str, Any],
    expected_metadata: Dict[str, Any],
) -> Tuple[bool, List[str]]:
    """
    Validates specific expected metadata attributes.
    """
    mismatches: List[str] = []
    for k, exp_val in expected_metadata.items():
        if k not in actual_metadata:
            mismatches.append(f"Missing expected metadata key: '{k}'")
            continue
        act_val = actual_metadata[k]
        if act_val != exp_val:
            mismatches.append(f"Metadata '{k}' mismatch: expected {exp_val}, got {act_val}")

    return (len(mismatches) == 0), mismatches


def evaluate_fixture(
    result: ExtractionResult,
    gt: GroundTruth,
    execution_time_ms: float = 0.0,
) -> FixtureEvaluationResult:
    """
    Performs full evaluation of an extraction result against ground truth.
    """
    actual_status_str = result.status.value if hasattr(result.status, "value") else str(result.status)
    status_match = actual_status_str in gt.accepted_statuses

    actual_error = result.error_code
    error_code_match = True
    if gt.expected_error_code is not None:
        error_code_match = (actual_error == gt.expected_error_code)

    # Text accuracy (only relevant for non-empty ground truth)
    cer = 0.0
    car = 1.0
    lev_dist = 0
    if gt.expected_text:
        cer, lev_dist = calculate_cer(result.content, gt.expected_text)
        car = calculate_car(cer)

    # Structural accuracy
    structure_match, struct_score, struct_mismatches = evaluate_structural_correctness(
        result.blocks,
        gt.expected_blocks,
    )

    # Warnings validation
    warnings_passed, missing_warns, forbidden_warns = evaluate_warnings(
        result.warnings,
        gt.expected_warnings,
        gt.forbidden_warnings,
    )

    # Metadata validation
    meta_match, meta_mismatches = evaluate_metadata(
        result.metadata,
        gt.expected_metadata,
    )

    # Overall pass determination based on thresholds
    thresholds = gt.provisional_thresholds
    max_allowed_cer = thresholds.get("max_cer", 0.00)
    min_allowed_car = thresholds.get("min_car", 1.00)
    require_exact_struct = thresholds.get("require_exact_structure", True)

    overall_passed = True
    if not status_match:
        overall_passed = False
    if not error_code_match:
        overall_passed = False
    if not warnings_passed:
        overall_passed = False
    if not meta_match:
        overall_passed = False

    if gt.expected_status != "failed":
        if cer > max_allowed_cer or car < min_allowed_car:
            overall_passed = False
        if require_exact_struct and not structure_match:
            overall_passed = False

    text_preview = (result.content[:100] + "...") if len(result.content) > 100 else result.content
    gt_preview = (gt.expected_text[:100] + "...") if len(gt.expected_text) > 100 else gt.expected_text

    return FixtureEvaluationResult(
        fixture_id=gt.fixture_id,
        format=gt.format,
        scenario=gt.scenario,
        passed=overall_passed,
        status_match=status_match,
        actual_status=actual_status_str,
        expected_status=gt.expected_status,
        error_code_match=error_code_match,
        actual_error_code=actual_error,
        expected_error_code=gt.expected_error_code,
        cer=round(cer, 4),
        car=round(car, 4),
        levenshtein_distance=lev_dist,
        structure_match=structure_match,
        structural_score=round(struct_score, 4),
        structure_mismatches=struct_mismatches,
        warnings_passed=warnings_passed,
        missing_warnings=missing_warns,
        forbidden_warnings_found=forbidden_warns,
        metadata_match=meta_match,
        metadata_mismatches=meta_mismatches,
        execution_time_ms=round(execution_time_ms, 2),
        extracted_text_preview=text_preview.replace("\n", " "),
        expected_text_preview=gt_preview.replace("\n", " "),
    )
