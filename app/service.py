"""
Document Extraction Service.
Validates input format, signatures, and size limits, and dispatches to format-specific extractors.
"""

import os
import io
import zipfile
from typing import Union, Optional, Dict, Any

from .contracts import ExtractionResult, ExtractionStatus
from .exceptions import (
    ExtractionException,
    UnsupportedFormatException,
    CorruptedFileException,
    ResourceLimitException,
    SecurityException,
    EmptyFileException,
    sanitize_error_message,
)
from .extractors import (
    BaseExtractor,
    TxtExtractor,
    DocxExtractor,
    XlsxExtractor,
    CsvExtractor,
)


class DocumentExtractionService:
    """
    Central orchestration service for document extraction.
    Performs security validation, signature verification, and format routing.
    """

    SUPPORTED_EXTENSIONS = {
        "txt": "txt",
        "text": "txt",
        "docx": "docx",
        "xlsx": "xlsx",
        "csv": "csv",
        "tsv": "csv",
    }

    # Zip magic bytes: PK\x03\x04
    ZIP_MAGIC = b"PK\x03\x04"

    def __init__(
        self,
        max_file_size: int = BaseExtractor.DEFAULT_MAX_FILE_SIZE,
        max_uncompressed_size: int = BaseExtractor.DEFAULT_MAX_UNCOMPRESSED_SIZE,
        max_text_length: int = BaseExtractor.DEFAULT_MAX_TEXT_LENGTH,
    ):
        self.max_file_size = max_file_size
        self.extractors = {
            "txt": TxtExtractor(max_file_size, max_uncompressed_size, max_text_length),
            "docx": DocxExtractor(max_file_size, max_uncompressed_size, max_text_length),
            "xlsx": XlsxExtractor(max_file_size, max_uncompressed_size, max_text_length),
            "csv": CsvExtractor(max_file_size, max_uncompressed_size, max_text_length),
        }

    def extract_file(self, file_path: str, original_filename: Optional[str] = None) -> ExtractionResult:
        """Extracts text and structure from a file on the local filesystem."""
        try:
            # Check path validity and traversal
            norm_path = os.path.normpath(file_path)
            if not os.path.exists(norm_path) or not os.path.isfile(norm_path):
                return self._error_result("unknown", "FILE_NOT_FOUND", "Specified document does not exist")

            filename = original_filename or os.path.basename(norm_path)
            size = os.path.getsize(norm_path)
            if size == 0:
                return self._error_result("unknown", "FILE_EMPTY", "Uploaded file is 0 bytes")
            if size > self.max_file_size:
                return self._error_result(
                    "unknown",
                    "RESOURCE_LIMIT_EXCEEDED",
                    f"File size exceeds maximum allowable limit of {self.max_file_size} bytes",
                )

            with open(norm_path, "rb") as f:
                raw_bytes = f.read()

            return self.extract_bytes(raw_bytes, filename=filename)

        except Exception as e:
            return self._error_result("unknown", "UNEXPECTED_ERROR", str(e))

    def extract_bytes(self, raw_bytes: bytes, filename: str) -> ExtractionResult:
        """Extracts text and structure from raw document bytes in memory."""
        if not raw_bytes or len(raw_bytes) == 0:
            return self._error_result("unknown", "FILE_EMPTY", "Provided file content is 0 bytes")

        if len(raw_bytes) > self.max_file_size:
            return self._error_result(
                "unknown",
                "RESOURCE_LIMIT_EXCEEDED",
                f"File size ({len(raw_bytes)} bytes) exceeds maximum allowable limit ({self.max_file_size} bytes)",
            )

        # 1. Determine format from extension
        ext = self._get_extension(filename)
        format_key = self.SUPPORTED_EXTENSIONS.get(ext)

        if not format_key:
            return self._error_result(
                "unsupported",
                "UNSUPPORTED_FORMAT",
                f"Unsupported file format: '{ext or 'unknown'}'. Supported: txt, docx, xlsx, csv",
            )

        # 2. Verify File Signature / Magic Bytes
        signature_error = self._verify_signature(raw_bytes, format_key)
        if signature_error:
            return self._error_result(format_key, signature_error[0], signature_error[1])

        # 3. Dispatch to format extractor
        extractor = self.extractors.get(format_key)
        if not extractor:
            return self._error_result(
                format_key,
                "NO_EXTRACTOR",
                f"No extractor registered for format: {format_key}",
            )

        try:
            return extractor.extract(raw_bytes, filename=filename)
        except ExtractionException as e:
            return self._error_result(format_key, e.error_code, e.sanitized_message)
        except Exception as e:
            return self._error_result(format_key, "EXTRACTION_EXCEPTION", str(e))

    def _get_extension(self, filename: Optional[str]) -> str:
        if not filename:
            return ""
        parts = filename.rsplit(".", 1)
        return parts[1].lower() if len(parts) > 1 else ""

    def _verify_signature(self, raw_bytes: bytes, format_key: str) -> Optional[tuple]:
        """Validates format magic bytes to prevent spoofed or dangerous files."""
        if format_key in ("docx", "xlsx"):
            # Must be a valid zip container
            if not raw_bytes.startswith(self.ZIP_MAGIC):
                return ("INVALID_SIGNATURE", f"File has .{format_key} extension but is not a valid OpenXML Zip archive")
            try:
                with zipfile.ZipFile(io.BytesIO(raw_bytes)) as z:
                    namelist = z.namelist()
                    if format_key == "docx" and "word/document.xml" not in namelist:
                        return ("INVALID_SIGNATURE", "Zip archive does not contain Word document XML (word/document.xml)")
                    if format_key == "xlsx" and "xl/workbook.xml" not in namelist:
                        return ("INVALID_SIGNATURE", "Zip archive does not contain Excel workbook XML (xl/workbook.xml)")
            except zipfile.BadZipFile:
                return ("CORRUPTED_FILE", "Archive container is malformed or corrupted")

        elif format_key in ("txt", "csv"):
            # Check for binary null bytes that characterize executables, ELF, Mach-O, or compressed blobs
            # Text files must not contain multiple null bytes in the opening 1 KB
            sample = raw_bytes[:1024]
            # UTF-16 files legitimately contain null bytes in alternate positions
            if not (raw_bytes.startswith(b"\xff\xfe") or raw_bytes.startswith(b"\xfe\xff")):
                null_count = sample.count(b"\x00")
                if null_count > 2:
                    return ("INVALID_SIGNATURE", "File contains binary null bytes and appears to be a binary executable, not text")

        return None

    def _error_result(self, format_name: str, code: str, message: str) -> ExtractionResult:
        return ExtractionResult(
            status=ExtractionStatus.FAILED,
            format=format_name,
            content="",
            blocks=[],
            metadata={},
            warnings=[],
            error_code=code,
            error_message=sanitize_error_message(message),
            stats={"character_count": 0, "word_count": 0, "block_count": 0},
        )
