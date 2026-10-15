"""
Comma-Separated Values (.csv) Extractor.
Uses standard library csv, conservative dialect probing, quoted field handling,
BOM detection, and jagged row validation without formula execution.
"""

import io
import csv
import unicodedata
from typing import Union, Optional, Tuple, List, Dict, Any

# pyrefly: ignore [missing-import]
from ..contracts import ExtractionResult, ExtractionStatus, DocumentBlock, TableBlock, BlockType
# pyrefly: ignore [missing-import]
from ..exceptions import (
    ExtractionException,
    EmptyFileException,
    CorruptedFileException,
    ResourceLimitException,
)
from .base import BaseExtractor

try:
    # pyrefly: ignore [missing-import]
    import charset_normalizer
    HAS_CHARSET_NORMALIZER = True
except ImportError:
    HAS_CHARSET_NORMALIZER = False


class CsvExtractor(BaseExtractor):
    """
    Extracts tabular data from CSV, TSV, and DSV files.
    """

    ALLOWED_DELIMITERS = [",", "\t", ";", "|"]

    def extract(self, file_source: Union[str, bytes], filename: Optional[str] = None) -> ExtractionResult:
        try:
            raw_bytes, source_filename = self._read_source_bytes(file_source)
        except EmptyFileException:
            return self._create_failed_result("csv", "FILE_EMPTY", "CSV file is empty (0 bytes)")
        except ExtractionException as e:
            return self._create_failed_result("csv", e.error_code, e.sanitized_message)
        except Exception as e:
            return self._create_failed_result("csv", "READ_ERROR", f"Error reading file: {str(e)}")

        effective_filename = filename or source_filename or "data.csv"
        warnings: List[str] = []

        # 1. Decode text with BOM detection
        text, encoding, has_bom = self._decode_csv_bytes(raw_bytes, warnings)
        if text is None or not text.strip():
            return self._create_failed_result(
                "csv",
                "FILE_EMPTY" if text is not None else "DECODING_FAILURE",
                "CSV file is empty or could not be decoded",
                warnings=warnings,
            )

        # Normalize Unicode NFC and strip BOM marker
        text = unicodedata.normalize("NFC", text)
        if text.startswith("\ufeff"):
            text = text.lstrip("\ufeff")
            has_bom = True

        # 2. Conservative Dialect & Delimiter Probing
        delimiter, quotechar, sniffer_confident = self._detect_dialect(text, warnings)

        # 3. Parse CSV rows using detected dialect
        try:
            reader = csv.reader(
                io.StringIO(text),
                delimiter=delimiter,
                quotechar=quotechar,
                skipinitialspace=True,
            )
            raw_rows = [row for row in reader if any(cell.strip() for cell in row)]
        except Exception as e:
            return self._create_failed_result(
                "csv",
                "CORRUPTED_FILE",
                f"CSV parsing error: {str(e)}",
                warnings=warnings,
            )

        if not raw_rows:
            return self._create_failed_result(
                "csv",
                "FILE_EMPTY",
                "CSV file contains no non-empty rows",
                warnings=warnings,
            )

        # 4. Check for Column Width Consistency (Jagged rows)
        col_counts = [len(r) for r in raw_rows]
        primary_col_count = max(set(col_counts), key=col_counts.count)
        inconsistent_rows = [i + 1 for i, count in enumerate(col_counts) if count != primary_col_count]

        status = ExtractionStatus.SUCCESS
        if inconsistent_rows:
            warnings.append(
                f"Inconsistent column counts detected across {len(inconsistent_rows)} row(s). "
                f"Expected {primary_col_count} columns, found variations on row(s): {inconsistent_rows[:10]}"
            )
            status = ExtractionStatus.NEEDS_REVIEW if len(inconsistent_rows) > len(raw_rows) * 0.25 else ExtractionStatus.SUCCESS_WITH_WARNINGS

        # Normalize all rows to primary_col_count
        normalized_rows: List[List[str]] = []
        for r in raw_rows:
            cleaned_row = [str(cell).strip() for cell in r]
            if len(cleaned_row) < primary_col_count:
                cleaned_row.extend([""] * (primary_col_count - len(cleaned_row)))
            elif len(cleaned_row) > primary_col_count:
                cleaned_row = cleaned_row[:primary_col_count]
            normalized_rows.append(cleaned_row)

        # 5. Header Detection (Heuristic with fallback)
        has_header = self._detect_has_header(normalized_rows)
        if has_header:
            headers = normalized_rows[0]
            data_rows = normalized_rows[1:]
        else:
            headers = [f"column_{i+1}" for i in range(primary_col_count)]
            data_rows = normalized_rows
            warnings.append("No distinct header row detected; generated synthetic column names")
            if status == ExtractionStatus.SUCCESS:
                status = ExtractionStatus.SUCCESS_WITH_WARNINGS

        # 6. Create TableBlock and Assemble Result
        table_block = TableBlock(
            order=1,
            text="",
            headers=headers,
            rows=data_rows,
            caption=effective_filename,
            metadata={
                "delimiter": delimiter,
                "col_count": primary_col_count,
                "row_count": len(normalized_rows),
                "has_header": has_header,
            },
        )
        blocks: List[DocumentBlock] = [table_block]

        content, stats = self._assemble_content_and_stats(
            blocks,
            additional_stats={
                "row_count": len(normalized_rows),
                "col_count": primary_col_count,
                "inconsistent_row_count": len(inconsistent_rows),
            },
        )

        metadata = {
            "delimiter": delimiter,
            "quotechar": quotechar,
            "has_header": has_header,
            "encoding": encoding,
            "has_bom": has_bom,
            "filename": effective_filename,
            "inconsistent_rows_count": len(inconsistent_rows),
        }

        return ExtractionResult(
            status=status,
            format="csv",
            content=content,
            blocks=blocks,
            metadata=metadata,
            warnings=warnings,
            stats=stats,
        )

    def _decode_csv_bytes(self, raw_bytes: bytes, warnings: List[str]) -> Tuple[Optional[str], str, bool]:
        """Decodes CSV bytes checking BOM, UTF-8, and fallbacks."""
        if raw_bytes.startswith(b"\xef\xbb\xbf"):
            try:
                return raw_bytes.decode("utf-8-sig"), "utf-8-sig", True
            except UnicodeDecodeError:
                pass

        if raw_bytes.startswith(b"\xff\xfe") or raw_bytes.startswith(b"\xfe\xff"):
            try:
                return raw_bytes.decode("utf-16"), "utf-16", True
            except UnicodeDecodeError:
                pass

        try:
            return raw_bytes.decode("utf-8"), "utf-8", False
        except UnicodeDecodeError:
            pass

        if HAS_CHARSET_NORMALIZER:
            try:
                best = charset_normalizer.from_bytes(raw_bytes).best()
                if best is not None:
                    return str(best), best.encoding or "unknown", False
            except Exception:
                pass

        for enc in ["windows-1252", "iso-8859-1"]:
            try:
                decoded = raw_bytes.decode(enc)
                warnings.append(f"Decoded CSV using legacy encoding '{enc}'")
                return decoded, enc, False
            except UnicodeDecodeError:
                continue

        return None, "unknown", False

    def _detect_dialect(self, text: str, warnings: List[str]) -> Tuple[str, str, bool]:
        """Conservatively detects CSV delimiter and quote character."""
        sample = text[:4096]
        sniffer = csv.Sniffer()
        try:
            dialect = sniffer.sniff(sample, delimiters=",\t;|")
            delimiter = dialect.delimiter
            quotechar = dialect.quotechar or '"'
            if delimiter in self.ALLOWED_DELIMITERS:
                return delimiter, quotechar, True
        except Exception:
            pass

        # Fallback: Count frequencies of allowed delimiters on initial lines
        lines = [line for line in sample.split("\n") if line.strip()][:5]
        if lines:
            counts = {d: sum(line.count(d) for line in lines) for d in self.ALLOWED_DELIMITERS}
            best_delimiter = max(counts, key=counts.get)
            if counts[best_delimiter] > 0:
                warnings.append(f"Dialect sniffer uncertain; inferred delimiter '{best_delimiter}' via character frequency")
                return best_delimiter, '"', False

        warnings.append("Delimiter sniffing failed; defaulted to comma (',')")
        return ",", '"', False

    def _detect_has_header(self, rows: List[List[str]]) -> bool:
        """Determines if the first row is likely a column header."""
        if not rows or len(rows) < 2:
            return True

        first_row = rows[0]
        second_row = rows[1]

        # If first row has any empty cells, less likely to be pure header
        if any(cell == "" for cell in first_row):
            return False

        # If first row contains numbers where second row also contains numbers, likely data
        def is_numeric(s: str) -> bool:
            return s.replace(".", "", 1).replace(",", "", 1).replace("-", "", 1).isdigit()

        first_numeric = sum(is_numeric(c) for c in first_row)
        second_numeric = sum(is_numeric(c) for c in second_row)

        if first_numeric == 0 and second_numeric > 0:
            return True

        if first_numeric > 0 and first_numeric == second_numeric:
            return False

        return True
