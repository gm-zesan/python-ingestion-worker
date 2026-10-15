"""
Tests for TxtExtractor.
Covers: UTF-8, BOM, line breaks, legacy encodings, Bengali Unicode preservation,
empty inputs, corrupted/mojibake detection, resource limits.
"""

import unittest
from app.contracts import ExtractionStatus, BlockType
from app.extractors.txt_extractor import TxtExtractor


class TestTxtExtractor(unittest.TestCase):

    def setUp(self):
        self.extractor = TxtExtractor()

    def test_valid_utf8_extraction(self):
        content = "First paragraph of policy.\n\nSecond paragraph with terms."
        result = self.extractor.extract(content.encode("utf-8"), filename="policy.txt")
        self.assertEqual(result.status, ExtractionStatus.SUCCESS)
        self.assertEqual(result.format, "txt")
        self.assertEqual(len(result.blocks), 2)
        self.assertIn("First paragraph of policy.", result.content)
        self.assertIn("Second paragraph with terms.", result.content)
        self.assertEqual(result.metadata["encoding"], "utf-8")
        self.assertFalse(result.metadata["has_bom"])

    def test_utf8_with_bom(self):
        content = "\ufeffBOM prefix text.\n\nNext section."
        raw_bytes = content.encode("utf-8-sig")
        result = self.extractor.extract(raw_bytes, filename="bom.txt")
        self.assertEqual(result.status, ExtractionStatus.SUCCESS)
        self.assertTrue(result.metadata["has_bom"])
        self.assertIn("BOM prefix text.", result.content)

    def test_bengali_unicode_nfc_preservation(self):
        # Bengali text with complex conjuncts, diacritics, and currency symbol ৳
        bengali_text = (
            "আমাদের রিটার্ন পলিসি অনুযায়ী ৭ দিনের মধ্যে পণ্য ফেরত দেওয়া যাবে।\n\n"
            "ডেলিভারি চার্জ: ঢাকা শহরের ভেতরে ৬০ টাকা (৳ ৬০), বাইরে ১২০ টাকা (৳ ১২০)।"
        )
        result = self.extractor.extract(bengali_text.encode("utf-8"), filename="bengali_faq.txt")
        self.assertEqual(result.status, ExtractionStatus.SUCCESS)
        self.assertIn("আমাদের রিটার্ন পলিসি", result.content)
        self.assertIn("৳ ৬০", result.content)
        self.assertIn("৳ ১২০", result.content)
        self.assertEqual(len(result.blocks), 2)

    def test_legacy_windows_1252_encoding(self):
        # Windows-1252 specific byte sequence (smart quotes, em-dash: \x93, \x94, \x97)
        # "Hello" with smart quotes and em-dash
        raw_bytes = b"Special \x93quoted\x94 term \x97 legacy file."
        result = self.extractor.extract(raw_bytes, filename="legacy.txt")
        self.assertTrue(result.is_successful)
        self.assertIn("quoted", result.content)

    def test_empty_file_fails_cleanly(self):
        result = self.extractor.extract(b"", filename="empty.txt")
        self.assertEqual(result.status, ExtractionStatus.FAILED)
        self.assertEqual(result.error_code, "FILE_EMPTY")

    def test_whitespace_only_file_fails_cleanly(self):
        result = self.extractor.extract(b"   \n\n   \t  \n", filename="blank.txt")
        self.assertEqual(result.status, ExtractionStatus.FAILED)
        self.assertEqual(result.error_code, "FILE_EMPTY")

    def test_high_mojibake_flags_needs_review(self):
        # File with excessive replacement characters / corruption
        corrupted_text = "Good text " + ("\ufffd" * 50) + " trailing text."
        result = self.extractor.extract(corrupted_text.encode("utf-8"), filename="corrupted.txt")
        self.assertEqual(result.status, ExtractionStatus.NEEDS_REVIEW)
        self.assertTrue(any("mojibake" in w.lower() for w in result.warnings))

    def test_file_size_limit_enforcement(self):
        small_extractor = TxtExtractor(max_file_size=50)
        large_content = b"A" * 100
        result = small_extractor.extract(large_content, filename="large.txt")
        self.assertEqual(result.status, ExtractionStatus.FAILED)
        self.assertEqual(result.error_code, "RESOURCE_LIMIT_EXCEEDED")


if __name__ == "__main__":
    unittest.main()
