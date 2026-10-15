"""
Base Extractor Class with Resource Limits, Zip Bomb Defense, and Result Assembly.
"""

import os
import io
import zipfile
from typing import Union, Optional, Tuple, List, Dict, Any

# pyrefly: ignore [missing-import]
from ..contracts import ExtractionResult, ExtractionStatus, DocumentBlock, BlockType
# pyrefly: ignore [missing-import]
from ..exceptions import (
    ExtractionException,
    ResourceLimitException,
    SecurityException,
    EmptyFileException,
    CorruptedFileException,
    sanitize_error_message,
)


class BaseExtractor:
    """Base class providing security checks, limit enforcement, and result helpers."""

    DEFAULT_MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
    DEFAULT_MAX_UNCOMPRESSED_SIZE = 50 * 1024 * 1024  # 50 MB
    DEFAULT_MAX_TEXT_LENGTH = 10 * 1024 * 1024  # 10M characters

    def __init__(
        self,
        max_file_size: int = DEFAULT_MAX_FILE_SIZE,
        max_uncompressed_size: int = DEFAULT_MAX_UNCOMPRESSED_SIZE,
        max_text_length: int = DEFAULT_MAX_TEXT_LENGTH,
    ):
        self.max_file_size = max_file_size
        self.max_uncompressed_size = max_uncompressed_size
        self.max_text_length = max_text_length

    def _read_source_bytes(self, file_source: Union[str, bytes]) -> Tuple[bytes, Optional[str]]:
        """Safely reads file source (path or bytes) into memory while checking size limits."""
        if isinstance(file_source, bytes):
            if len(file_source) == 0:
                raise EmptyFileException()
            if len(file_source) > self.max_file_size:
                raise ResourceLimitException(f"File size ({len(file_source)} bytes) exceeds limit ({self.max_file_size} bytes)")
            return file_source, None

        if isinstance(file_source, str):
            # Check path traversal
            normalized_path = os.path.normpath(file_source)
            if not os.path.exists(normalized_path):
                raise ExtractionException("Specified file does not exist", error_code="FILE_NOT_FOUND")
            if not os.path.isfile(normalized_path):
                raise ExtractionException("Specified path is not a file", error_code="INVALID_PATH")

            size = os.path.getsize(normalized_path)
            if size == 0:
                raise EmptyFileException()
            if size > self.max_file_size:
                raise ResourceLimitException(f"File size ({size} bytes) exceeds limit ({self.max_file_size} bytes)")

            with open(normalized_path, "rb") as f:
                data = f.read()
            return data, os.path.basename(normalized_path)

        raise ExtractionException("file_source must be a file path string or raw bytes", error_code="INVALID_INPUT")

    def _check_zip_bomb(self, raw_bytes: bytes) -> None:
        """Inspects zip archive entries to protect against zip/decompression bombs."""
        try:
            with zipfile.ZipFile(io.BytesIO(raw_bytes)) as z:
                total_uncompressed = 0
                for info in z.infolist():
                    total_uncompressed += info.file_size
                    if total_uncompressed > self.max_uncompressed_size:
                        raise ResourceLimitException(
                            f"Uncompressed archive size exceeds safety threshold ({self.max_uncompressed_size} bytes)"
                        )
                    # Check suspicious compression ratio (>100:1) on files larger than 100 KB
                    if info.file_size > 100_000 and info.compress_size > 0:
                        ratio = info.file_size / info.compress_size
                        if ratio > 100:
                            raise SecurityException(f"Suspicious compression ratio ({ratio:.1f}:1) detected")
        except zipfile.BadZipFile as e:
            raise CorruptedFileException("Invalid or malformed zip container") from e

    def _create_failed_result(
        self,
        format_name: str,
        error_code: str,
        error_message: str,
        warnings: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ExtractionResult:
        """Constructs a normalized FAILED extraction result."""
        return ExtractionResult(
            status=ExtractionStatus.FAILED,
            format=format_name,
            content="",
            blocks=[],
            metadata=metadata or {},
            warnings=warnings or [],
            error_code=error_code,
            error_message=sanitize_error_message(error_message),
            stats={"character_count": 0, "word_count": 0, "block_count": 0},
        )

    def _assemble_content_and_stats(
        self,
        blocks: List[DocumentBlock],
        additional_stats: Optional[Dict[str, Any]] = None,
    ) -> Tuple[str, Dict[str, Any]]:
        """Assembles ordered blocks into a cohesive text string and computes extraction statistics."""
        content_parts = []
        for block in blocks:
            if block.text and block.text.strip():
                content_parts.append(block.text.strip())

        full_content = "\n\n".join(content_parts)
        if len(full_content) > self.max_text_length:
            full_content = full_content[: self.max_text_length]

        stats = {
            "character_count": len(full_content),
            "word_count": len(full_content.split()),
            "block_count": len(blocks),
        }
        if additional_stats:
            stats.update(additional_stats)

        return full_content, stats
