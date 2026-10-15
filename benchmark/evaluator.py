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
    - Trims line-level trailing whitespace while preserving leading indentation
      and internal spacing.
    - Explicitly PRESERVES all Bengali script characters (U+0980..U+09FF)
      including Zero Width Joiner (ZWJ U+200D) and Zero Width Non-Joiner (ZWNJ U+200C).
    - Trims leading and trailing empty lines from the document boundaries
      while preserving internal paragraph breaks.
    """
    if text is None:
        return ""

    # 1. Unicode NFC
    normalized = unicodedata.normalize("NFC", text)

    # 2. Line ending unification
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")

    # 3. Strip trailing whitespace per line without destroying leading indent/spaces
    lines = [line.rstrip() for line in normalized.split("\n")]

    # 4. Filter leading/trailing empty lines at document boundaries
    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()

    return "\n".join(lines)


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
        # Ground truth was expected to be empty, but text was extracted
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
    - Block count and ordering
    - Block types (heading, paragraph, table, worksheet, etc.)
    - Block text content (normalized)
    - Heading levels (h1, h2, h3, etc.)
    - Table headers, row counts, and cell values
    - Worksheet names and table captions
    Returns (is_match, score, list_of_mismatches).
    """
    if not expected_blocks:
        if not actual_blocks:
            return True, 1.0, []
        return False, 0.0, [f"Expected 0 blocks, but extracted {len(actual_blocks)} blocks"]

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

        # Check block text if explicitly specified in ground truth
        if "text" in exp:
            total_checks += 1
            act_text_norm = normalize_for_evaluation(getattr(act, "text", ""))
            exp_text_norm = normalize_for_evaluation(exp["text"])
            if act_text_norm != exp_text_norm:
                mismatches.append(
                    f"Block [{i+1}] text mismatch: expected '{exp_text_norm[:40]}...', got '{act_text_norm[:40]}...'"
                )
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

        # Check table specifics
        if exp_type == "table":
            if "headers" in exp:
                total_checks += 1
                act_headers = [normalize_for_evaluation(h) for h in getattr(act, "headers", [])]
                exp_headers = [normalize_for_evaluation(h) for h in exp["headers"]]
                if act_headers != exp_headers:
                    mismatches.append(f"Block [{i+1}] table headers mismatch: expected {exp_headers}, got {act_headers}")
                else:
                    passed_checks += 1

            if "row_count" in exp:
                total_checks += 1
                act_rows = getattr(act, "rows", [])
                if len(act_rows) != exp["row_count"]:
                    mismatches.append(f"Block [{i+1}] table row count mismatch: expected {exp['row_count']}, got {len(act_rows)}")
                else:
                    passed_checks += 1

            if "rows" in exp:
                total_checks += 1
                act_rows = [[normalize_for_evaluation(c) for c in r] for r in getattr(act, "rows", [])]
                exp_rows = [[normalize_for_evaluation(c) for c in r] for r in exp["rows"]]
                if act_rows != exp_rows:
                    mismatches.append(f"Block [{i+1}] table row cell values mismatch: expected {exp_rows}, got {act_rows}")
                else:
                    passed_checks += 1

            if "caption" in exp:
                total_checks += 1
                act_caption = getattr(act, "caption", "") or ""
                if normalize_for_evaluation(act_caption) != normalize_for_evaluation(exp["caption"]):
                    mismatches.append(f"Block [{i+1}] table caption mismatch: expected '{exp['caption']}', got '{act_caption}'")
                else:
                    passed_checks += 1

        # Check worksheet name / metadata
        if "sheet_name" in exp:
            total_checks += 1
            act_sheet = act.metadata.get("sheet_name") if hasattr(act, "metadata") else None
            if act_sheet != exp["sheet_name"]:
                mismatches.append(f"Block [{i+1}] sheet name mismatch: expected '{exp['sheet_name']}', got '{act_sheet}'")
            else:
                passed_checks += 1

    # Report excess or missing blocks
    if len(actual_blocks) > len(expected_blocks):
        for j in range(len(expected_blocks), len(actual_blocks)):
            b = actual_blocks[j]
            b_type = b.block_type.value if hasattr(b.block_type, "value") else str(b.block_type)
            mismatches.append(f"Unexpected extra block [{j+1}]: type '{b_type}'")
    elif len(actual_blocks) < len(expected_blocks):
        for j in range(len(actual_blocks), len(expected_blocks)):
            e = expected_blocks[j]
            mismatches.append(f"Missing expected block [{j+1}]: type '{e.get('block_type')}'")

    structural_score = passed_checks / max(total_checks, 1)
    is_match = (len(mismatches) == 0)
    return is_match, structural_score, mismatches


def evaluate_warnings(
    actual_warnings: List[str],
    expected_warnings: List[str],
    forbidden_warnings: List[str],
    expected_status: str,
) -> Tuple[bool, List[str], List[str]]:
    """
    Validates expected and forbidden warning substrings.
    Policy:
    - Expected warnings: every substring must appear case-insensitively in actual warnings.
    - Forbidden warnings: no substring in forbidden_warnings may appear in actual warnings.
    - Clean fixtures: if expected_status is 'success' and expected_warnings is empty,
      any generated warning is flagged as unexpected unless explicitly accepted.
    """
    missing_warnings: List[str] = []
    forbidden_found: List[str] = []

    actual_combined = " ".join(actual_warnings).lower()

    for exp_w in expected_warnings:
        if exp_w.lower() not in actual_combined:
            missing_warnings.append(exp_w)

    for forb_w in forbidden_warnings:
        if forb_w == "*":
            if actual_warnings:
                forbidden_found.extend(actual_warnings)
        elif forb_w.lower() in actual_combined:
            forbidden_found.append(forb_w)

    # For strictly clean fixtures (expected clean success without warnings),
    # ensure no unexpected warnings were generated
    if expected_status == "success" and not expected_warnings and actual_warnings:
        for w in actual_warnings:
            if w not in forbidden_found:
                forbidden_found.append(f"Unexpected warning in clean fixture: '{w}'")

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
    Ensures:
    - A failed extraction never silently passes unless explicitly expected.
    - Negative fixtures have verified error codes.
    - Inapplicable text metrics are reported as None rather than 1.0.
    - Zero-length ground truth cannot conceal unexpected extracted text.
    - Structural checks, warnings, and metadata are strictly verified.
    """
    failure_reasons: List[str] = []

    # 1. Status comparison
    actual_status_str = result.status.value if hasattr(result.status, "value") else str(result.status)
    accepted_set = {s.value if hasattr(s, "value") else str(s) for s in gt.accepted_statuses}
    status_match = actual_status_str in accepted_set

    if not status_match:
        failure_reasons.append(
            f"Status mismatch: expected '{gt.expected_status}' (accepted: {sorted(accepted_set)}), got '{actual_status_str}'"
        )

    # 2. Error code comparison
    actual_error = result.error_code
    error_code_match = True

    if gt.expected_error_code is not None:
        error_code_match = (actual_error == gt.expected_error_code)
        if not error_code_match:
            failure_reasons.append(
                f"Error code mismatch: expected '{gt.expected_error_code}', got '{actual_error}'"
            )
    elif gt.expected_status == "failed" or actual_status_str == "failed":
        if gt.expected_status == "failed":
            if not gt.allow_any_error_code:
                # Ground truth defect: negative fixtures must explicitly define expected error code
                error_code_match = False
                failure_reasons.append(
                    f"Negative fixture '{gt.fixture_id}' must explicitly specify expected_error_code"
                )
            elif not actual_error:
                error_code_match = False
                failure_reasons.append("Expected extraction failure with error code, but error_code was empty")

    # Inadvertent extraction failure defense:
    # A failed extraction must not pass merely because text/structural checks were skipped
    if actual_status_str == "failed" and "failed" not in accepted_set:
        failure_reasons.append(
            f"Extraction unexpectedly failed with error '{actual_error}': {result.error_message}"
        )

    # 3. Text Accuracy Evaluation (CER / CAR)
    is_text_applicable = gt.text_applicable if gt.text_applicable is not None else (gt.expected_status != "failed")
    cer: Optional[float] = None
    car: Optional[float] = None
    lev_dist: Optional[int] = None

    if is_text_applicable:
        cer, lev_dist = calculate_cer(result.content, gt.expected_text)
        car = calculate_car(cer)

        thresholds = gt.provisional_thresholds
        max_allowed_cer = thresholds.get("max_cer", 0.00)
        min_allowed_car = thresholds.get("min_car", 1.00)

        if cer > max_allowed_cer:
            failure_reasons.append(
                f"CER {cer:.4f} exceeds max allowed {max_allowed_cer:.4f} (edit distance: {lev_dist})"
            )
        if car < min_allowed_car:
            failure_reasons.append(
                f"CAR {car:.4f} is below min required {min_allowed_car:.4f}"
            )
    else:
        # Prevent zero-length ground truth in failed/negative tests from concealing unexpected content
        if result.content and actual_status_str != "failed":
            failure_reasons.append(
                f"Unexpected content extracted in non-text scenario: '{result.content[:50]}...'"
            )

    # 4. Structural Accuracy Evaluation
    structure_match, struct_score, struct_mismatches = evaluate_structural_correctness(
        result.blocks,
        gt.expected_blocks,
    )

    if gt.expected_status != "failed" or gt.expected_blocks:
        require_exact_struct = gt.provisional_thresholds.get("require_exact_structure", True)
        if require_exact_struct and not structure_match:
            failure_reasons.extend(struct_mismatches)

    # 5. Warnings Validation
    warnings_passed, missing_warns, forbidden_warns = evaluate_warnings(
        result.warnings,
        gt.expected_warnings,
        gt.forbidden_warnings,
        gt.expected_status,
    )
    if not warnings_passed:
        if missing_warns:
            failure_reasons.append(f"Missing required warnings: {missing_warns}")
        if forbidden_warns:
            failure_reasons.append(f"Forbidden/unexpected warnings encountered: {forbidden_warns}")

    # 6. Metadata Validation
    meta_match, meta_mismatches = evaluate_metadata(
        result.metadata,
        gt.expected_metadata,
    )
    if not meta_match:
        failure_reasons.extend(meta_mismatches)

    overall_passed = (len(failure_reasons) == 0)

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
        text_applicable=is_text_applicable,
        cer=round(cer, 4) if cer is not None else None,
        car=round(car, 4) if car is not None else None,
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
        failure_reasons=failure_reasons,
    )
