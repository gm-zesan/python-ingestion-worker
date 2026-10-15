"""
Tests for CsvExtractor.
Covers: Comma, tab, semicolon, pipe delimiters, quoted delimiters,
quoted newlines, UTF-8 BOM, headerless data, inconsistent / jagged rows.
"""

import unittest
from app.contracts import ExtractionStatus, BlockType
from app.extractors.csv_extractor import CsvExtractor


class TestCsvExtractor(unittest.TestCase):

    def setUp(self):
        self.extractor = CsvExtractor()

    def test_standard_comma_csv_extraction(self):
        csv_text = "Product,Price,Stock\nSmartphone,25000,10\nLaptop,65000,5\n"
        result = self.extractor.extract(csv_text.encode("utf-8"), filename="products.csv")

        self.assertEqual(result.status, ExtractionStatus.SUCCESS)
        self.assertEqual(result.format, "csv")
        self.assertEqual(result.metadata["delimiter"], ",")
        self.assertTrue(result.metadata["has_header"])

        table_blocks = [b for b in result.blocks if b.block_type == BlockType.TABLE]
        self.assertEqual(len(table_blocks), 1)
        self.assertEqual(table_blocks[0].headers, ["Product", "Price", "Stock"])
        self.assertEqual(len(table_blocks[0].rows), 2)
        self.assertIn("Smartphone", result.content)

    def test_alternate_delimiters(self):
        # Semicolon delimited
        semicolon_csv = "District;Rate;TransitDays\nDhaka;60;1\nChittagong;120;2\n"
        res_semi = self.extractor.extract(semicolon_csv.encode("utf-8"), filename="rates.csv")
        self.assertEqual(res_semi.status, ExtractionStatus.SUCCESS)
        self.assertEqual(res_semi.metadata["delimiter"], ";")

        # Tab delimited
        tab_csv = "Name\tDepartment\tRole\nRahim\tSupport\tAgent\nKarim\tBilling\tLead\n"
        res_tab = self.extractor.extract(tab_csv.encode("utf-8"), filename="staff.tsv")
        self.assertEqual(res_tab.status, ExtractionStatus.SUCCESS)
        self.assertEqual(res_tab.metadata["delimiter"], "\t")

    def test_quoted_delimiters_and_newlines(self):
        # Cell containing comma inside quotes and newline inside quotes
        csv_text = (
            'ID,Description,Amount\n'
            '1,"Refund for order, item damaged",1500\n'
            '2,"Multiline note\nSecond line of note",2000\n'
        )
        result = self.extractor.extract(csv_text.encode("utf-8"), filename="complex.csv")
        self.assertEqual(result.status, ExtractionStatus.SUCCESS)
        table = result.blocks[0]
        self.assertEqual(len(table.rows), 2)
        self.assertEqual(table.rows[0][1], "Refund for order, item damaged")
        self.assertIn("Multiline note", table.rows[1][1])

    def test_inert_formula_text_not_evaluated_in_csv(self):
        # CSV injection style strings: =SUM(...) or =cmd|' /C calc'!A0 must remain harmless literal text
        csv_text = "Formula,Target\n=SUM(A1:A10),Sales\n=cmd|' /C calc'!A0,Threat\n"
        result = self.extractor.extract(csv_text.encode("utf-8"), filename="formulas.csv")
        self.assertEqual(result.status, ExtractionStatus.SUCCESS)
        table = result.blocks[0]
        self.assertEqual(table.rows[0][0], "=SUM(A1:A10)")
        self.assertEqual(table.rows[1][0], "=cmd|' /C calc'!A0")
        self.assertIn("=SUM(A1:A10)", result.content)

    def test_utf8_with_bom_csv(self):
        csv_text = "\ufeffCategory,Discount\nElectronics,10%\nFashion,15%\n"
        result = self.extractor.extract(csv_text.encode("utf-8-sig"), filename="promo.csv")
        self.assertEqual(result.status, ExtractionStatus.SUCCESS)
        self.assertTrue(result.metadata["has_bom"])
        self.assertEqual(result.blocks[0].headers[0], "Category")

    def test_inconsistent_jagged_rows_handling(self):
        # Row 1 has 3 cols, Row 2 has 4 cols (jagged)
        csv_text = (
            "Name,Age,City\n"
            "Alice,30,Dhaka\n"
            "Bob,25,Chittagong,ExtraField\n"
            "Charlie,35,Sylhet\n"
        )
        result = self.extractor.extract(csv_text.encode("utf-8"), filename="jagged.csv")
        self.assertIn(result.status, (ExtractionStatus.SUCCESS_WITH_WARNINGS, ExtractionStatus.NEEDS_REVIEW))
        self.assertTrue(any("inconsistent" in w.lower() for w in result.warnings))

    def test_headerless_csv_generates_synthetic_headers(self):
        # All numeric data rows
        csv_text = (
            "1001,250,5\n"
            "1002,300,10\n"
            "1003,150,2\n"
        )
        result = self.extractor.extract(csv_text.encode("utf-8"), filename="numbers.csv")
        self.assertTrue(result.is_successful)
        table = result.blocks[0]
        self.assertEqual(table.headers, ["column_1", "column_2", "column_3"])
        self.assertEqual(len(table.rows), 3)

    def test_empty_csv_fails_cleanly(self):
        result = self.extractor.extract(b"", filename="empty.csv")
        self.assertEqual(result.status, ExtractionStatus.FAILED)
        self.assertEqual(result.error_code, "FILE_EMPTY")

    def test_pipe_delimiter(self):
        csv_text = "SKU|Name|Price\nP101|Earbuds|1500\nP102|Adapter|500\n"
        result = self.extractor.extract(csv_text.encode("utf-8"), filename="items.psv")
        self.assertEqual(result.status, ExtractionStatus.SUCCESS)
        self.assertEqual(result.metadata["delimiter"], "|")
        self.assertEqual(result.blocks[0].headers, ["SKU", "Name", "Price"])

    def test_bengali_unicode_csv(self):
        csv_text = (
            "এলাকা,চার্জ (টাকা),সময়\n"
            "ঢাকা সদর,৬০,২৪ ঘন্টা\n"
            "নারায়ণগঞ্জ,১০০,৪৮ ঘন্টা\n"
        )
        result = self.extractor.extract(csv_text.encode("utf-8"), filename="bengali_shipping.csv")
        self.assertEqual(result.status, ExtractionStatus.SUCCESS)
        self.assertIn("ঢাকা সদর", result.content)
        self.assertIn("২৪ ঘন্টা", result.content)


if __name__ == "__main__":
    unittest.main()
