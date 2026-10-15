"""
Plain Text (.txt) Extractor with Encoding Detection, Unicode NFC Normalization,
and Paragraph Structure Preservation.
"""

import re
import unicodedata
from typing import Union, Optional, Tuple, List, Dict, Any

# pyrefly: ignore [missing-import]
from ..contracts import ExtractionResult, ExtractionStatus, DocumentBlock, BlockType
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


class TxtExtractor(BaseExtractor):
    """
    Extracts text from plain text (.txt) files.
    Preserves Bengali conjuncts, diacritics, and ZWJ/ZWNJ characters.
    """

    SUPPORTED_ENCODINGS = ["utf-8", "utf-8-sig", "windows-1252", "iso-8859-1", "utf-16"]

    def extract(self, file_source: Union[str, bytes], filename: Optional[str] = None) -> ExtractionResult:
        try:
            raw_bytes, source_filename = self._read_source_bytes(file_source)
        except EmptyFileException:
            return self._create_failed_result("txt", "FILE_EMPTY", "Text file is empty")
        except ExtractionException as e:
            return self._create_failed_result("txt", e.error_code, e.sanitized_message)
        except Exception as e:
            return self._create_failed_result("txt", "READ_ERROR", f"Error reading file: {str(e)}")

        effective_filename = filename or source_filename or "document.txt"
        warnings: List[str] = []

        # 1. Detect Encoding and Decode
        text, encoding, confidence, has_bom = self._decode_bytes(raw_bytes, warnings)
        if text is None:
            return self._create_failed_result(
                "txt",
                "DECODING_FAILURE",
                f"Failed to decode text file. Checked encodings: {', '.join(self.SUPPORTED_ENCODINGS)}",
                warnings=warnings,
            )

        # 2. Check empty decoded text
        if not text.strip():
            return self._create_failed_result("txt", "FILE_EMPTY", "File contains only whitespace or null bytes")

        # 3. Unicode NFC Normalization (Preserving Bengali ZWJ/ZWNJ)
        text = unicodedata.normalize("NFC", text)
        if text.startswith("\ufeff"):
            text = text.lstrip("\ufeff")
            has_bom = True

        # 4. Check Replacement Character / Mojibake ratio
        mojibake_count = text.count("\ufffd")
        mojibake_ratio = mojibake_count / max(1, len(text))
        status = ExtractionStatus.SUCCESS

        if mojibake_ratio > 0.05:
            # Over 5% replacement characters indicates severe corruption
            warnings.append(f"High mojibake/replacement character ratio ({mojibake_ratio:.1%}) detected")
            status = ExtractionStatus.NEEDS_REVIEW
        elif mojibake_ratio > 0:
            warnings.append(f"Minor mojibake characters detected ({mojibake_count} occurrences)")
            status = ExtractionStatus.SUCCESS_WITH_WARNINGS

        if confidence < 0.70 and encoding not in ("utf-8", "utf-8-sig"):
            warnings.append(f"Encoding '{encoding}' detected with low confidence ({confidence:.0%})")
            if status == ExtractionStatus.SUCCESS:
                status = ExtractionStatus.SUCCESS_WITH_WARNINGS

        # 5. Extract Paragraph Blocks
        blocks, lines_count, para_count = self._extract_blocks(text)

        # 6. Assemble Content and Stats
        content, stats = self._assemble_content_and_stats(
            blocks,
            additional_stats={
                "line_count": lines_count,
                "paragraph_count": para_count,
            },
        )

        metadata = {
            "encoding": encoding,
            "encoding_confidence": confidence,
            "has_bom": has_bom,
            "filename": effective_filename,
            "mojibake_ratio": mojibake_ratio,
        }

        return ExtractionResult(
            status=status,
            format="txt",
            content=content,
            blocks=blocks,
            metadata=metadata,
            warnings=warnings,
            stats=stats,
        )

    def _decode_bytes(self, raw_bytes: bytes, warnings: List[str]) -> Tuple[Optional[str], str, float, bool]:
        """Attempts decoding raw bytes using BOM detection, UTF-8, charset-normalizer, and fallbacks."""
        # Check UTF-8 BOM
        if raw_bytes.startswith(b"\xef\xbb\xbf"):
            try:
                decoded = raw_bytes.decode("utf-8-sig")
                return decoded, "utf-8-sig", 1.0, True
            except UnicodeDecodeError:
                pass

        # Check UTF-16 BOMs
        if raw_bytes.startswith(b"\xff\xfe") or raw_bytes.startswith(b"\xfe\xff"):
            try:
                decoded = raw_bytes.decode("utf-16")
                return decoded, "utf-16", 1.0, True
            except UnicodeDecodeError:
                pass

        # Try strict UTF-8
        try:
            decoded = raw_bytes.decode("utf-8")
            return decoded, "utf-8", 1.0, False
        except UnicodeDecodeError:
            pass

        # Use charset-normalizer if available
        if HAS_CHARSET_NORMALIZER:
            try:
                results = charset_normalizer.from_bytes(raw_bytes)
                best_match = results.best()
                if best_match is not None:
                    confidence = float(best_match.chaos <= 0.20) if hasattr(best_match, "chaos") else 0.85
                    decoded_text = str(best_match)
                    encoding_name = best_match.encoding or "unknown"
                    return decoded_text, encoding_name, confidence, False
            except Exception as e:
                warnings.append(f"charset-normalizer warning: {str(e)}")

        # Fallback candidates
        for enc in ["windows-1252", "iso-8859-1"]:
            try:
                decoded = raw_bytes.decode(enc)
                warnings.append(f"Decoded using legacy fallback encoding '{enc}'")
                return decoded, enc, 0.60, False
            except UnicodeDecodeError:
                continue

        return None, "unknown", 0.0, False

    def _extract_blocks(self, text: str) -> Tuple[List[DocumentBlock], int, int]:
        """Normalizes line endings and extracts distinct paragraph blocks."""
        # Normalize carriage returns
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        raw_lines = normalized.split("\n")
        lines_count = len(raw_lines)

        # Split on double newlines to delineate paragraphs
        paragraphs = re.split(r"\n{2,}", normalized)
        blocks: List[DocumentBlock] = []
        order = 0

        for p in paragraphs:
            cleaned = p.strip()
            if not cleaned:
                continue
            order += 1
            blocks.append(
                DocumentBlock(
                    block_type=BlockType.PARAGRAPH,
                    text=cleaned,
                    order=order,
                    metadata={"char_length": len(cleaned)},
                )
            )

        return blocks, lines_count, len(blocks)
