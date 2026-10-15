"""
Excel Spreadsheet (.xlsx) Extractor.
Extracts multiple worksheets, table grids, headers, and cell values.
Uses read-only and data-only modes in openpyxl to never execute formulas or VBA macros,
while safely checking for uncalculated formula error values.
"""

import io
import zipfile
from typing import Union, Optional, Tuple, List, Dict, Any

from ..contracts import ExtractionResult, ExtractionStatus, DocumentBlock, TableBlock, BlockType
from ..exceptions import (
    ExtractionException,
    EmptyFileException,
    CorruptedFileException,
    ResourceLimitException,
)
from .base import BaseExtractor

try:
    import openpyxl
    HAS_OPENPYXL = True
except ImportError:
    HAS_OPENPYXL = False

EXCEL_ERROR_VALUES = {"#NULL!", "#DIV/0!", "#VALUE!", "#REF!", "#NAME?", "#NUM!", "#N/A"}


class XlsxExtractor(BaseExtractor):
    """
    Extracts tabular data from Microsoft Excel (.xlsx) files across all worksheets.
    """

    def extract(self, file_source: Union[str, bytes], filename: Optional[str] = None) -> ExtractionResult:
        if not HAS_OPENPYXL:
            return self._create_failed_result(
                "xlsx",
                "DEPENDENCY_MISSING",
                "openpyxl library is required for XLSX extraction",
            )

        try:
            raw_bytes, source_filename = self._read_source_bytes(file_source)
        except EmptyFileException:
            return self._create_failed_result("xlsx", "FILE_EMPTY", "Excel file is empty (0 bytes)")
        except ExtractionException as e:
            return self._create_failed_result("xlsx", e.error_code, e.sanitized_message)
        except Exception as e:
            return self._create_failed_result("xlsx", "READ_ERROR", f"Error reading file: {str(e)}")

        effective_filename = filename or source_filename or "workbook.xlsx"

        # 1. Zip Bomb Defense (Enforced before openpyxl parsing)
        try:
            self._check_zip_bomb(raw_bytes)
        except ExtractionException as e:
            return self._create_failed_result("xlsx", e.error_code, e.sanitized_message)

        # 2. Check for required Excel workbook XML entries
        try:
            with zipfile.ZipFile(io.BytesIO(raw_bytes)) as z:
                namelist = z.namelist()
                if "xl/workbook.xml" not in namelist:
                    return self._create_failed_result(
                        "xlsx",
                        "CORRUPTED_FILE",
                        "Invalid XLSX structure: missing xl/workbook.xml in archive",
                    )
                # Check for macro sheets (xl/vbaProject.bin)
                has_macros = any("vbaProject.bin" in n for n in namelist)
        except zipfile.BadZipFile:
            return self._create_failed_result("xlsx", "CORRUPTED_FILE", "Malformed XLSX zip archive")

        warnings: List[str] = []
        if has_macros:
            warnings.append("Workbook contains VBA macros (.xlsm/vbaProject.bin); macros were NOT executed")

        # 3. Load Workbook in Read-Only Data-Only Mode (never executes formulas, extracts cached values)
        try:
            wb = openpyxl.load_workbook(
                io.BytesIO(raw_bytes),
                read_only=True,
                data_only=True,  # Read cached formula evaluation results rather than formula strings
                keep_vba=False,   # Never load VBA code
            )
        except Exception as e:
            return self._create_failed_result(
                "xlsx",
                "CORRUPTED_FILE",
                f"Failed to open Excel workbook: {str(e)}",
            )

        blocks: List[DocumentBlock] = []
        order = 0
        sheet_summaries: List[Dict[str, Any]] = []
        hidden_sheets: List[str] = []
        total_rows_extracted = 0
        total_cells_extracted = 0
        empty_sheets_count = 0
        has_formula_errors = False
        formula_error_occurrences: List[str] = []

        try:
            sheet_names = wb.sheetnames
            for sheet_name in sheet_names:
                sheet = wb[sheet_name]
                is_hidden = getattr(sheet, "sheet_state", "visible") != "visible"
                if is_hidden:
                    hidden_sheets.append(sheet_name)
                    warnings.append(f"Worksheet '{sheet_name}' is hidden in workbook")

                rows_data: List[List[str]] = []
                for row in sheet.iter_rows(values_only=True):
                    if not row or all(v is None or str(v).strip() == "" for v in row):
                        continue

                    formatted_row: List[str] = []
                    for val in row:
                        cell_str = self._format_cell_value(val)
                        if cell_str in EXCEL_ERROR_VALUES:
                            has_formula_errors = True
                            if cell_str not in formula_error_occurrences:
                                formula_error_occurrences.append(cell_str)
                        formatted_row.append(cell_str)

                    # Trim trailing empty cells from row
                    while formatted_row and formatted_row[-1] == "":
                        formatted_row.pop()
                    if formatted_row:
                        rows_data.append(formatted_row)

                if not rows_data:
                    empty_sheets_count += 1
                    sheet_summaries.append({
                        "name": sheet_name,
                        "is_hidden": is_hidden,
                        "row_count": 0,
                        "col_count": 0,
                        "is_empty": True,
                    })
                    continue

                order += 1
                headers = rows_data[0] if rows_data else []
                data_rows = rows_data[1:] if len(rows_data) > 1 else []

                col_count = max(len(r) for r in rows_data) if rows_data else 0
                total_rows_extracted += len(rows_data)
                total_cells_extracted += sum(len(r) for r in rows_data)

                # Normalize column widths across all rows in this sheet
                normalized_rows: List[List[str]] = []
                for r in data_rows:
                    if len(r) < len(headers):
                        r = r + [""] * (len(headers) - len(r))
                    normalized_rows.append(r)

                table_block = TableBlock(
                    order=order,
                    text="",
                    headers=headers,
                    rows=normalized_rows,
                    caption=f"Sheet: {sheet_name}",
                    metadata={
                        "sheet_name": sheet_name,
                        "is_hidden": is_hidden,
                        "row_count": len(rows_data),
                        "col_count": len(headers),
                    },
                )
                blocks.append(table_block)

                sheet_summaries.append({
                    "name": sheet_name,
                    "is_hidden": is_hidden,
                    "row_count": len(rows_data),
                    "col_count": len(headers),
                    "is_empty": False,
                })

        finally:
            wb.close()

        # 4. Check if entire workbook was empty
        if not blocks:
            return self._create_failed_result(
                "xlsx",
                "FILE_EMPTY",
                "Excel workbook contains no readable data across any worksheet",
                warnings=warnings,
                metadata={"sheet_names": sheet_names, "sheet_count": len(sheet_names)},
            )

        if empty_sheets_count > 0:
            warnings.append(f"{empty_sheets_count} worksheet(s) were empty and contained no data")

        if has_formula_errors:
            warnings.append(
                f"Worksheet contains uncalculated formulas or Excel error values ({', '.join(formula_error_occurrences)})"
            )

        # 5. Assemble Content and Stats
        content, stats = self._assemble_content_and_stats(
            blocks,
            additional_stats={
                "sheet_count": len(sheet_names),
                "total_rows": total_rows_extracted,
                "total_cells": total_cells_extracted,
                "empty_sheets_count": empty_sheets_count,
            },
        )

        metadata = {
            "sheet_names": sheet_names,
            "sheet_count": len(sheet_names),
            "hidden_sheets": hidden_sheets,
            "sheet_summaries": sheet_summaries,
            "filename": effective_filename,
            "has_formula_errors": has_formula_errors,
        }

        status = ExtractionStatus.SUCCESS
        if has_formula_errors:
            status = ExtractionStatus.NEEDS_REVIEW
        elif warnings:
            status = ExtractionStatus.SUCCESS_WITH_WARNINGS

        return ExtractionResult(
            status=status,
            format="xlsx",
            content=content,
            blocks=blocks,
            metadata=metadata,
            warnings=warnings,
            stats=stats,
        )

    def _format_cell_value(self, val: Any) -> str:
        """Formats cell values without converting string identifiers into numbers or dropping leading zeros."""
        if val is None:
            return ""
        if isinstance(val, str):
            return val.strip()
        if isinstance(val, (int, float)):
            if isinstance(val, float) and val.is_integer():
                return str(int(val))
            return str(val)
        if hasattr(val, "strftime"):
            return val.strftime("%Y-%m-%d %H:%M:%S" if hasattr(val, "hour") else "%Y-%m-%d")
        return str(val).strip()
