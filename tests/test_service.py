"""
Tests for DocumentExtractionService.
Covers: Format routing, signature validation, spoofed file defense,
unsupported formats, path sanitization, and resource limits.
"""

import os
import tempfile
import unittest
from app.contracts import ExtractionStatus
from app.service import DocumentExtractionService
from tests.helpers import create_synthetic_docx_bytes, create_synthetic_xlsx_bytes, HAS_OPENPYXL


class TestDocumentExtractionService(unittest.TestCase):

    def setUp(self):
        self.service = DocumentExtractionService(max_file_size=1024 * 1024)  # 1 MB

    def test_txt_dispatch(self):
        result = self.service.extract_bytes(b"Text content", filename="doc.txt")
        self.assertEqual(result.status, ExtractionStatus.SUCCESS)
        self.assertEqual(result.format, "txt")

    def test_docx_dispatch(self):
        docx_bytes = create_synthetic_docx_bytes(paragraphs=["Hello world docx"])
        result = self.service.extract_bytes(docx_bytes, filename="sample.docx")
        self.assertEqual(result.status, ExtractionStatus.SUCCESS)
        self.assertEqual(result.format, "docx")

    def test_xlsx_dispatch(self):
        if not HAS_OPENPYXL:
            self.skipTest("openpyxl not installed")
        xlsx_bytes = create_synthetic_xlsx_bytes({"Sheet1": [["A", "B"], ["1", "2"]]})
        result = self.service.extract_bytes(xlsx_bytes, filename="data.xlsx")
        self.assertEqual(result.status, ExtractionStatus.SUCCESS)
        self.assertEqual(result.format, "xlsx")

    def test_csv_dispatch(self):
        result = self.service.extract_bytes(b"col1,col2\nval1,val2\n", filename="test.csv")
        self.assertEqual(result.status, ExtractionStatus.SUCCESS)
        self.assertEqual(result.format, "csv")

    def test_unsupported_format_rejected(self):
        result = self.service.extract_bytes(b"%PDF-1.4...", filename="document.pdf")
        self.assertEqual(result.status, ExtractionStatus.FAILED)
        self.assertEqual(result.error_code, "UNSUPPORTED_FORMAT")

    def test_spoofed_docx_fails_signature_check(self):
        # Plain text saved with .docx extension
        result = self.service.extract_bytes(b"Just plain text masquerading as docx", filename="spoofed.docx")
        self.assertEqual(result.status, ExtractionStatus.FAILED)
        self.assertEqual(result.error_code, "INVALID_SIGNATURE")

    def test_spoofed_xlsx_fails_signature_check(self):
        # Plain text saved with .xlsx extension
        result = self.service.extract_bytes(b"Just plain text masquerading as xlsx", filename="spoofed.xlsx")
        self.assertEqual(result.status, ExtractionStatus.FAILED)
        self.assertEqual(result.error_code, "INVALID_SIGNATURE")

    def test_binary_null_bytes_in_txt_fails_signature(self):
        # ELF / Mach-O / binary executable masquerading as txt
        fake_binary = b"\x7fELF\x02\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00" + (b"\x00" * 50)
        result = self.service.extract_bytes(fake_binary, filename="malware.txt")
        self.assertEqual(result.status, ExtractionStatus.FAILED)
        self.assertEqual(result.error_code, "INVALID_SIGNATURE")

    def test_size_limit_rejection(self):
        small_service = DocumentExtractionService(max_file_size=100)
        oversized = b"A" * 200
        result = small_service.extract_bytes(oversized, filename="big.txt")
        self.assertEqual(result.status, ExtractionStatus.FAILED)
        self.assertEqual(result.error_code, "RESOURCE_LIMIT_EXCEEDED")

    def test_extract_file_path_and_sanitization(self):
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"Temp file content line 1\n\nLine 2")
            temp_path = f.name

        try:
            result = self.service.extract_file(temp_path)
            self.assertEqual(result.status, ExtractionStatus.SUCCESS)
            self.assertIn("Temp file content line 1", result.content)

            # Test non-existent file error message sanitization
            non_existent = "/Users/zesan/secret_path/does_not_exist_12345.txt"
            res_missing = self.service.extract_file(non_existent)
            self.assertEqual(res_missing.status, ExtractionStatus.FAILED)
            # Ensure secret path is not leaked
            self.assertNotIn("/Users/zesan/secret_path", res_missing.error_message or "")
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)


    def test_max_text_length_truncation(self):
        limited_service = DocumentExtractionService(max_text_length=50)
        long_text = b"This is a long sentence that should exceed the fifty character limit."
        result = limited_service.extract_bytes(long_text, filename="long.txt")
        self.assertEqual(result.status, ExtractionStatus.SUCCESS)
        self.assertLessEqual(len(result.content), 50)

    def test_extract_file_docx(self):
        docx_bytes = create_synthetic_docx_bytes(paragraphs=["Paragraph from file on disk."])
        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as f:
            f.write(docx_bytes)
            path = f.name
        try:
            result = self.service.extract_file(path)
            self.assertEqual(result.status, ExtractionStatus.SUCCESS)
            self.assertEqual(result.format, "docx")
            self.assertIn("Paragraph from file on disk.", result.content)
        finally:
            if os.path.exists(path):
                os.remove(path)


if __name__ == "__main__":
    unittest.main()
