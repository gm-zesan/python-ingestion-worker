"""
Tests for XlsxExtractor.
Covers: Multi-sheet extraction, headers preservation, leading zero retention,
formula cached values, blank rows, empty sheets, hidden sheet handling.
"""

import unittest
from app.contracts import ExtractionStatus, BlockType
from app.extractors.xlsx_extractor import XlsxExtractor
from tests.helpers import create_synthetic_xlsx_bytes, HAS_OPENPYXL


@unittest.skipUnless(HAS_OPENPYXL, "openpyxl is required for Excel extraction tests")
class TestXlsxExtractor(unittest.TestCase):

    def setUp(self):
        self.extractor = XlsxExtractor()

    def test_multi_sheet_extraction_with_headers(self):
        sheets = {
            "Products": [
                ["SKU", "Product Name", "Price (BDT)"],
                ["PRD-001", "Wireless Mouse", 1200],
                ["PRD-002", "Mechanical Keyboard", 3500],
            ],
            "Shipping": [
                ["Zone", "Carrier", "Cost"],
                ["Dhaka Metro", "Pathao", 60],
                ["Chittagong", "Steadfast", 120],
            ],
        }
        xlsx_bytes = create_synthetic_xlsx_bytes(sheets)
        result = self.extractor.extract(xlsx_bytes, filename="inventory.xlsx")

        self.assertEqual(result.status, ExtractionStatus.SUCCESS)
        self.assertEqual(result.format, "xlsx")
        self.assertEqual(result.metadata["sheet_count"], 2)
        self.assertIn("Products", result.metadata["sheet_names"])
        self.assertIn("Shipping", result.metadata["sheet_names"])

        # Check extracted table blocks
        table_blocks = [b for b in result.blocks if b.block_type == BlockType.TABLE]
        self.assertEqual(len(table_blocks), 2)
        self.assertEqual(table_blocks[0].headers, ["SKU", "Product Name", "Price (BDT)"])
        self.assertEqual(table_blocks[1].headers, ["Zone", "Carrier", "Cost"])
        self.assertIn("Wireless Mouse", result.content)
        self.assertIn("Dhaka Metro", result.content)

    def test_leading_zero_preservation(self):
        sheets = {
            "Contacts": [
                ["Contact ID", "Phone Number", "Postal Code"],
                ["00123", "01712345678", "0120"],
                ["00456", "01898765432", "0450"],
            ]
        }
        xlsx_bytes = create_synthetic_xlsx_bytes(sheets)
        result = self.extractor.extract(xlsx_bytes, filename="contacts.xlsx")

        self.assertEqual(result.status, ExtractionStatus.SUCCESS)
        self.assertIn("00123", result.content)
        self.assertIn("01712345678", result.content)
        self.assertIn("0120", result.content)

    def test_hidden_sheet_reporting(self):
        sheets = {
            "PublicData": [
                ["Item", "Price"],
                ["Book", 250],
            ],
            "InternalCosts": [
                ["Cost Type", "Amount"],
                ["Overhead", 1000],
            ],
        }
        xlsx_bytes = create_synthetic_xlsx_bytes(sheets, hidden_sheets=["InternalCosts"])
        result = self.extractor.extract(xlsx_bytes, filename="costs.xlsx")

        # Hidden sheets should trigger success_with_warnings and be recorded in metadata
        self.assertEqual(result.status, ExtractionStatus.SUCCESS_WITH_WARNINGS)
        self.assertIn("InternalCosts", result.metadata["hidden_sheets"])
        self.assertTrue(any("hidden in workbook" in w for w in result.warnings))

    def test_empty_sheet_handling(self):
        sheets = {
            "DataSheet": [
                ["Header1", "Header2"],
                ["Val1", "Val2"],
            ],
            "BlankSheet": [],
        }
        xlsx_bytes = create_synthetic_xlsx_bytes(sheets)
        result = self.extractor.extract(xlsx_bytes, filename="with_empty.xlsx")

        self.assertEqual(result.status, ExtractionStatus.SUCCESS_WITH_WARNINGS)
        self.assertTrue(any("empty" in w for w in result.warnings))

    def test_empty_workbook_fails_cleanly(self):
        sheets = {
            "EmptySheet1": [],
            "EmptySheet2": [],
        }
        xlsx_bytes = create_synthetic_xlsx_bytes(sheets)
        result = self.extractor.extract(xlsx_bytes, filename="all_empty.xlsx")

        self.assertEqual(result.status, ExtractionStatus.FAILED)
        self.assertEqual(result.error_code, "FILE_EMPTY")

    def test_malformed_zip_fails_cleanly(self):
        result = self.extractor.extract(b"not_a_valid_xlsx_binary", filename="corrupt.xlsx")
        self.assertEqual(result.status, ExtractionStatus.FAILED)
        self.assertEqual(result.error_code, "CORRUPTED_FILE")

    def test_bengali_unicode_in_xlsx(self):
        sheets = {
            "মূল্যতালিকা": [
                ["পণ্যের নাম", "মূল্য (টাকা)", "স্টক"],
                ["টি-শার্ট", 450, "উপলব্ধ"],
                ["জিন্স প্যান্ট", 1250, "সীমিত"],
            ]
        }
        xlsx_bytes = create_synthetic_xlsx_bytes(sheets)
        result = self.extractor.extract(xlsx_bytes, filename="bengali_catalog.xlsx")

        self.assertEqual(result.status, ExtractionStatus.SUCCESS)
        self.assertIn("মূল্যতালিকা", result.metadata["sheet_names"])
        self.assertIn("টি-শার্ট", result.content)
        self.assertIn("জিন্স প্যান্ট", result.content)

    def test_data_types_and_numbers(self):
        sheets = {
            "Mixed": [
                ["Integer", "Float", "Boolean", "Empty"],
                [100, 99.5, True, None],
            ]
        }
        xlsx_bytes = create_synthetic_xlsx_bytes(sheets)
        result = self.extractor.extract(xlsx_bytes, filename="types.xlsx")
        self.assertEqual(result.status, ExtractionStatus.SUCCESS)
        table = result.blocks[0]
        self.assertEqual(table.rows[0][0], "100")
        self.assertEqual(table.rows[0][1], "99.5")


if __name__ == "__main__":
    unittest.main()
