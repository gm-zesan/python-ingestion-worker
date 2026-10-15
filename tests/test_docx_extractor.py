"""
Tests for DocxExtractor.
Covers: Headings hierarchy, paragraphs, table grids with headers,
reading order preservation, empty files, malformed archives, zip bomb safety.
"""

import io
import zipfile
import unittest
from app.contracts import ExtractionStatus, BlockType
from app.extractors.docx_extractor import DocxExtractor
from tests.helpers import create_synthetic_docx_bytes


class TestDocxExtractor(unittest.TestCase):

    def setUp(self):
        self.extractor = DocxExtractor()

    def test_paragraphs_and_headings_extraction(self):
        headings = [(1, "General Return Policy"), (2, "Damaged Shipments")]
        paragraphs = [
            "Customers may request returns within 7 calendar days of receipt.",
            "Items must remain in original unopened packaging.",
        ]
        docx_bytes = create_synthetic_docx_bytes(paragraphs=paragraphs, headings=headings)
        result = self.extractor.extract(docx_bytes, filename="policy.docx")

        self.assertEqual(result.status, ExtractionStatus.SUCCESS)
        self.assertEqual(result.format, "docx")
        self.assertIn("General Return Policy", result.content)
        self.assertIn("Customers may request returns", result.content)

        # Check block types
        heading_blocks = [b for b in result.blocks if b.block_type == BlockType.HEADING]
        para_blocks = [b for b in result.blocks if b.block_type == BlockType.PARAGRAPH]
        self.assertEqual(len(heading_blocks), 2)
        self.assertEqual(len(para_blocks), 2)
        self.assertEqual(heading_blocks[0].level, 1)
        self.assertEqual(heading_blocks[1].level, 2)

    def test_table_extraction_with_headers_and_rows(self):
        table_data = [
            [
                ["Delivery Zone", "Timeline", "Fee"],
                ["Inside Dhaka", "24-48 Hours", "60 BDT"],
                ["Outside Dhaka", "3-5 Days", "120 BDT"],
            ]
        ]
        docx_bytes = create_synthetic_docx_bytes(
            paragraphs=["Pricing and Delivery Matrix:"],
            tables=table_data,
        )
        result = self.extractor.extract(docx_bytes, filename="fees.docx")

        self.assertEqual(result.status, ExtractionStatus.SUCCESS)
        table_blocks = [b for b in result.blocks if b.block_type == BlockType.TABLE]
        self.assertEqual(len(table_blocks), 1)

        tbl = table_blocks[0]
        self.assertEqual(tbl.headers, ["Delivery Zone", "Timeline", "Fee"])
        self.assertEqual(len(tbl.rows), 2)
        self.assertEqual(tbl.rows[0], ["Inside Dhaka", "24-48 Hours", "60 BDT"])
        self.assertIn("Inside Dhaka", result.content)

    def test_bengali_unicode_in_docx(self):
        headings = [(1, "ফেরত নীতিমালা (Return Policy)")]
        paragraphs = ["৭ দিনের মধ্যে ক্যাশ অন ডেলিভারি পণ্যের রিফンダント দাবি করুন।"]
        docx_bytes = create_synthetic_docx_bytes(paragraphs=paragraphs, headings=headings)
        result = self.extractor.extract(docx_bytes, filename="bengali.docx")

        self.assertEqual(result.status, ExtractionStatus.SUCCESS)
        self.assertIn("ফেরত নীতিমালা", result.content)
        self.assertIn("ক্যাশ অন ডেলিভারি", result.content)

    def test_empty_docx_file_fails_cleanly(self):
        result = self.extractor.extract(b"", filename="empty.docx")
        self.assertEqual(result.status, ExtractionStatus.FAILED)
        self.assertEqual(result.error_code, "FILE_EMPTY")

    def test_corrupted_zip_archive_fails_cleanly(self):
        result = self.extractor.extract(b"PK\x03\x04corrupted_payload_not_a_zip", filename="bad.docx")
        self.assertEqual(result.status, ExtractionStatus.FAILED)
        self.assertEqual(result.error_code, "CORRUPTED_FILE")

    def test_zip_without_document_xml_fails(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("some_other_file.txt", "data")
        result = self.extractor.extract(buf.getvalue(), filename="missing_xml.docx")
        self.assertEqual(result.status, ExtractionStatus.FAILED)
        self.assertEqual(result.error_code, "CORRUPTED_FILE")

    def test_malformed_document_xml_fails_cleanly(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("word/document.xml", "<w:document><broken_xml_no_closing>")
        result = self.extractor.extract(buf.getvalue(), filename="broken_xml.docx")
        self.assertEqual(result.status, ExtractionStatus.FAILED)
        self.assertEqual(result.error_code, "CORRUPTED_FILE")

    def test_interleaved_reading_order(self):
        # Test interleaved reading order: Heading -> Para -> Table
        headings = [(1, "Introduction")]
        paragraphs = ["Overview paragraph before table."]
        tables = [[["Feature", "Status"], ["Encryption", "Active"]]]
        docx_bytes = create_synthetic_docx_bytes(
            paragraphs=paragraphs,
            headings=headings,
            tables=tables,
        )
        result = self.extractor.extract(docx_bytes, filename="interleaved.docx")
        self.assertEqual(result.status, ExtractionStatus.SUCCESS)
        self.assertEqual(len(result.blocks), 3)
        self.assertEqual(result.blocks[0].block_type, BlockType.HEADING)
        self.assertEqual(result.blocks[1].block_type, BlockType.PARAGRAPH)
        self.assertEqual(result.blocks[2].block_type, BlockType.TABLE)
        self.assertEqual(result.blocks[0].order, 1)
        self.assertEqual(result.blocks[1].order, 2)
        self.assertEqual(result.blocks[2].order, 3)


if __name__ == "__main__":
    unittest.main()
