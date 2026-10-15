"""
Unit tests for Benchmark Evaluation Engine (evaluator.py).
Tests CER, CAR, Bengali normalization, ZWJ/ZWNJ preservation, structural comparisons,
status and error matching, and warning validation.
"""

import unittest
from app.contracts import (
    ExtractionResult,
    ExtractionStatus,
    DocumentBlock,
    TableBlock,
    BlockType,
)
from benchmark.models import GroundTruth
from benchmark.evaluator import (
    calculate_cer,
    calculate_car,
    calculate_levenshtein_distance,
    normalize_for_evaluation,
    evaluate_structural_correctness,
    evaluate_warnings,
    evaluate_metadata,
    evaluate_fixture,
)


class TestBenchmarkEvaluator(unittest.TestCase):

    # -------------------------------------------------------------------------
    # 1. CER, CAR, and Levenshtein Distance
    # -------------------------------------------------------------------------

    def test_cer_and_car_exact_match(self):
        text = "Exact matching content for document."
        cer, dist = calculate_cer(text, text)
        car = calculate_car(cer)
        self.assertEqual(dist, 0)
        self.assertEqual(cer, 0.0)
        self.assertEqual(car, 1.0)

    def test_cer_and_car_unequal_strings(self):
        s1 = "kitten"
        s2 = "sitting"
        # distance is 3 (k->s, e->i, +g)
        cer, dist = calculate_cer(s1, s2)
        car = calculate_car(cer)
        self.assertEqual(dist, 3)
        self.assertAlmostEqual(cer, 3 / 7)
        self.assertAlmostEqual(car, 1.0 - (3 / 7))

    def test_cer_empty_strings(self):
        # Both empty
        cer, dist = calculate_cer("", "")
        self.assertEqual(cer, 0.0)
        self.assertEqual(dist, 0)

        # Extracted has text, GT is empty -> CER must be 1.0 (unexpected text)
        cer, dist = calculate_cer("Unexpected extracted content", "")
        self.assertEqual(cer, 1.0)
        self.assertEqual(dist, len("Unexpected extracted content"))

        # Extracted is empty, GT has text -> CER must be 1.0
        cer, dist = calculate_cer("", "Expected content")
        self.assertEqual(cer, 1.0)
        self.assertEqual(dist, len("Expected content"))

    # -------------------------------------------------------------------------
    # 2. Bengali Unicode Normalization & ZWJ/ZWNJ Preservation
    # -------------------------------------------------------------------------

    def test_bengali_unicode_nfc_normalization(self):
        # NFD vs NFC Bengali text should normalize identically
        import unicodedata
        nfc_text = "ডেলিভারি চার্জ ৬০৳"
        nfd_text = unicodedata.normalize("NFD", nfc_text)
        self.assertEqual(normalize_for_evaluation(nfd_text), normalize_for_evaluation(nfc_text))

    def test_bengali_zwj_and_zwnj_differences_are_detectable(self):
        # Text with ZWJ vs without ZWJ must have distance > 0
        with_zwj = "র\u200d্যাপিড"
        without_zwj = "র্যাপিড"
        cer, dist = calculate_cer(with_zwj, without_zwj)
        self.assertGreater(dist, 0, "Stripping ZWJ must produce non-zero edit distance")
        self.assertGreater(cer, 0.0)

        # Text with ZWNJ vs without ZWNJ must have distance > 0
        with_zwnj = "ক্\u200cষ"
        without_zwnj = "ক্ষ"
        cer2, dist2 = calculate_cer(with_zwnj, without_zwnj)
        self.assertGreater(dist2, 0, "Stripping ZWNJ must produce non-zero edit distance")
        self.assertGreater(cer2, 0.0)

    def test_internal_whitespace_and_boundaries(self):
        # Leading and trailing line spaces preserved on lines, internal spacing preserved
        text_with_indent = "  Indent line\nSecond line"
        norm = normalize_for_evaluation(text_with_indent)
        self.assertTrue(norm.startswith("  Indent line"), "Leading indentation must be preserved")

        # Boundary empty lines removed, internal paragraph breaks kept
        raw = "\n\nFirst paragraph\n\nSecond paragraph\n\n\n"
        norm = normalize_for_evaluation(raw)
        self.assertEqual(norm, "First paragraph\n\nSecond paragraph")

    # -------------------------------------------------------------------------
    # 3. Status and Error Code Adherence
    # -------------------------------------------------------------------------

    def test_status_mismatch_fails_evaluation(self):
        res = ExtractionResult(
            status=ExtractionStatus.FAILED,
            format="txt",
            content="",
            error_code="FILE_EMPTY",
        )
        gt = GroundTruth(
            fixture_id="TEST-01",
            filename="test.txt",
            format="txt",
            category="test",
            scenario="Expected success test",
            expected_status="success",
        )
        eval_res = evaluate_fixture(res, gt)
        self.assertFalse(eval_res.passed)
        self.assertFalse(eval_res.status_match)
        self.assertTrue(any("Status mismatch" in r for r in eval_res.failure_reasons))

    def test_error_code_exact_match(self):
        res = ExtractionResult(
            status=ExtractionStatus.FAILED,
            format="txt",
            content="",
            error_code="INVALID_SIGNATURE",
        )
        gt = GroundTruth(
            fixture_id="TEST-02",
            filename="test.txt",
            format="txt",
            category="test",
            scenario="Signature failure test",
            expected_status="failed",
            expected_error_code="INVALID_SIGNATURE",
        )
        eval_res = evaluate_fixture(res, gt)
        self.assertTrue(eval_res.passed)
        self.assertTrue(eval_res.error_code_match)

    def test_error_code_mismatch_fails_evaluation(self):
        res = ExtractionResult(
            status=ExtractionStatus.FAILED,
            format="txt",
            content="",
            error_code="FILE_EMPTY",
        )
        gt = GroundTruth(
            fixture_id="TEST-03",
            filename="test.txt",
            format="txt",
            category="test",
            scenario="Corrupt archive test",
            expected_status="failed",
            expected_error_code="CORRUPTED_FILE",
        )
        eval_res = evaluate_fixture(res, gt)
        self.assertFalse(eval_res.passed)
        self.assertFalse(eval_res.error_code_match)
        self.assertTrue(any("Error code mismatch" in r for r in eval_res.failure_reasons))

    def test_negative_fixture_missing_error_code_fails(self):
        res = ExtractionResult(
            status=ExtractionStatus.FAILED,
            format="txt",
            content="",
            error_code=None,
        )
        gt = GroundTruth(
            fixture_id="TEST-04",
            filename="test.txt",
            format="txt",
            category="test",
            scenario="Failed without code",
            expected_status="failed",
            allow_any_error_code=True,
        )
        eval_res = evaluate_fixture(res, gt)
        self.assertFalse(eval_res.passed)
        self.assertTrue(any("error_code was empty" in r for r in eval_res.failure_reasons))

    def test_failed_extraction_does_not_pass_silently(self):
        # A crashed extraction returning FAILED must not pass when SUCCESS is expected
        res = ExtractionResult(
            status=ExtractionStatus.FAILED,
            format="docx",
            content="",
            error_code="CORRUPTED_FILE",
            error_message="Xml parser crashed",
        )
        gt = GroundTruth(
            fixture_id="TEST-05",
            filename="test.docx",
            format="docx",
            category="test",
            scenario="Should have succeeded",
            expected_status="success",
            accepted_statuses=["success"],
            expected_text="Some document text",
        )
        eval_res = evaluate_fixture(res, gt)
        self.assertFalse(eval_res.passed)
        self.assertTrue(any("unexpectedly failed" in r for r in eval_res.failure_reasons))

    # -------------------------------------------------------------------------
    # 4. Inapplicable Text and Zero-Length Ground Truth
    # -------------------------------------------------------------------------

    def test_text_inapplicable_reported_as_none(self):
        res = ExtractionResult(
            status=ExtractionStatus.FAILED,
            format="txt",
            content="",
            error_code="FILE_EMPTY",
        )
        gt = GroundTruth(
            fixture_id="TEST-06",
            filename="test.txt",
            format="txt",
            category="test",
            scenario="Empty file",
            expected_status="failed",
            expected_error_code="FILE_EMPTY",
        )
        eval_res = evaluate_fixture(res, gt)
        self.assertTrue(eval_res.passed)
        self.assertFalse(eval_res.text_applicable)
        self.assertIsNone(eval_res.cer)
        self.assertIsNone(eval_res.car)
        self.assertIsNone(eval_res.levenshtein_distance)

    def test_unexpected_extracted_content_fails_empty_ground_truth(self):
        # Expected empty text, but extractor produced unexpected content
        res = ExtractionResult(
            status=ExtractionStatus.SUCCESS,
            format="txt",
            content="Ghost text that should not exist",
        )
        gt = GroundTruth(
            fixture_id="TEST-07",
            filename="test.txt",
            format="txt",
            category="test",
            scenario="Empty document",
            expected_status="success",
            expected_text="",
            text_applicable=True,
        )
        eval_res = evaluate_fixture(res, gt)
        self.assertFalse(eval_res.passed)
        self.assertEqual(eval_res.cer, 1.0)
        self.assertEqual(eval_res.car, 0.0)

    # -------------------------------------------------------------------------
    # 5. Warning Validation
    # -------------------------------------------------------------------------

    def test_warning_validation_missing_required(self):
        passed, missing, forbidden = evaluate_warnings(
            actual_warnings=["Unrelated warning message"],
            expected_warnings=["Required Warning"],
            forbidden_warnings=[],
            expected_status="success_with_warnings",
        )
        self.assertFalse(passed)
        self.assertIn("Required Warning", missing)

    def test_warning_validation_forbidden_present(self):
        passed, missing, forbidden = evaluate_warnings(
            actual_warnings=["Contains forbidden substring here"],
            expected_warnings=[],
            forbidden_warnings=["forbidden substring"],
            expected_status="success_with_warnings",
        )
        self.assertFalse(passed)
        self.assertIn("forbidden substring", forbidden)

    def test_clean_fixture_disallows_unexpected_warnings(self):
        passed, missing, forbidden = evaluate_warnings(
            actual_warnings=["Unexpected warning appeared"],
            expected_warnings=[],
            forbidden_warnings=[],
            expected_status="success",  # Clean success
        )
        self.assertFalse(passed)
        self.assertTrue(len(forbidden) > 0)
        self.assertTrue(any("Unexpected warning in clean fixture" in f for f in forbidden))

    # -------------------------------------------------------------------------
    # 6. Structural Validation (Blocks, Headings, Tables, Worksheets)
    # -------------------------------------------------------------------------

    def test_structural_block_count_and_type_mismatch(self):
        actual = [
            DocumentBlock(block_type=BlockType.PARAGRAPH, text="Hello"),
        ]
        expected = [
            {"block_type": "heading", "level": 1, "text": "Hello"},
        ]
        is_match, score, mismatches = evaluate_structural_correctness(actual, expected)
        self.assertFalse(is_match)
        self.assertTrue(any("type mismatch" in m for m in mismatches))

    def test_structural_heading_level_mismatch(self):
        actual = [
            DocumentBlock(block_type=BlockType.HEADING, level=2, text="Title"),
        ]
        expected = [
            {"block_type": "heading", "level": 1, "text": "Title"},
        ]
        is_match, score, mismatches = evaluate_structural_correctness(actual, expected)
        self.assertFalse(is_match)
        self.assertTrue(any("heading level mismatch" in m for m in mismatches))

    def test_structural_table_headers_and_cell_mismatch(self):
        actual = [
            TableBlock(
                headers=["ColA", "ColB"],
                rows=[["1", "2"]],
            )
        ]
        # Expecting different headers
        expected = [
            {
                "block_type": "table",
                "headers": ["ColA", "ColDifferent"],
                "rows": [["1", "2"]],
                "row_count": 1,
            }
        ]
        is_match, score, mismatches = evaluate_structural_correctness(actual, expected)
        self.assertFalse(is_match)
        self.assertTrue(any("headers mismatch" in m for m in mismatches))

        # Expecting different cell values
        expected_cells = [
            {
                "block_type": "table",
                "headers": ["ColA", "ColB"],
                "rows": [["1", "999"]],
                "row_count": 1,
            }
        ]
        is_match2, score2, mismatches2 = evaluate_structural_correctness(actual, expected_cells)
        self.assertFalse(is_match2)
        self.assertTrue(any("cell values mismatch" in m for m in mismatches2))

    def test_structural_worksheet_name_mismatch(self):
        actual = [
            TableBlock(
                headers=["A"],
                rows=[["1"]],
                metadata={"sheet_name": "SheetAlpha"},
            )
        ]
        expected = [
            {
                "block_type": "table",
                "sheet_name": "SheetBeta",
                "headers": ["A"],
                "rows": [["1"]],
            }
        ]
        is_match, score, mismatches = evaluate_structural_correctness(actual, expected)
        self.assertFalse(is_match)
        self.assertTrue(any("sheet name mismatch" in m for m in mismatches))


if __name__ == "__main__":
    unittest.main()
