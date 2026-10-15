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

    def test_bengali_unicode_zwj_and_zwnj_preservation(self):
        # Explicit test for Zero Width Joiner (\u200D) and Zero Width Non-Joiner (\u200C)
        zwj_word = "র\u200d্যাপিড"      # Bengali ya-phala with ZWJ
        zwnj_word = "ক্\u200cষ"         # Explicit non-ligature with ZWNJ
        content = f"সংযুক্ত শব্দ ১: {zwj_word}\n\nসংযুক্ত শব্দ ২: {zwnj_word}"

        result = self.extractor.extract(content.encode("utf-8"), filename="bengali_zwj.txt")
        self.assertEqual(result.status, ExtractionStatus.SUCCESS)
        self.assertIn("\u200d", result.content, "ZWJ character must be preserved without stripping")
        self.assertIn("\u200c", result.content, "ZWNJ character must be preserved without stripping")
        self.assertIn(zwj_word, result.blocks[0].text)
        self.assertIn(zwnj_word, result.blocks[1].text)

    def test_undecodable_binary_fails_cleanly_without_silent_corruption(self):
        # Random non-ASCII binary sequence with unmapped control characters
        raw_bytes = b"\x81\x8d\x8f\x90\x9d\x01\x02\x03\x04\x05\x06\x07\x08"
        result = self.extractor.extract(raw_bytes, filename="binary.txt")
        self.assertEqual(result.status, ExtractionStatus.FAILED)
        self.assertEqual(result.error_code, "DECODING_FAILURE")
        self.assertEqual(result.content, "")

    def test_legacy_windows_1252_encoding(self):
        # Windows-1252 specific byte sequence (smart quotes, em-dash: \x93, \x94, \x97)
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
