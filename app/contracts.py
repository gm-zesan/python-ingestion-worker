"""
Normalized Extraction Output Contracts and Protocols for Document Extraction.
"""

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import List, Dict, Any, Optional, Union, Protocol


class ExtractionStatus(str, Enum):
    SUCCESS = "success"
    SUCCESS_WITH_WARNINGS = "success_with_warnings"
    NEEDS_REVIEW = "needs_review"
    FAILED = "failed"


class BlockType(str, Enum):
    PARAGRAPH = "paragraph"
    HEADING = "heading"
    TABLE = "table"
    LIST_ITEM = "list_item"
    WORKSHEET = "worksheet"


@dataclass
class DocumentBlock:
    """Represents an ordered structural unit of extracted document content."""
    text: str = ""
    order: int = 0
    block_type: BlockType = BlockType.PARAGRAPH
    level: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["block_type"] = self.block_type.value
        return data


@dataclass
class TableBlock(DocumentBlock):
    """Represents a structured table block with headers, rows, and dimensions."""
    block_type: BlockType = BlockType.TABLE
    headers: List[str] = field(default_factory=list)
    rows: List[List[str]] = field(default_factory=list)
    caption: Optional[str] = None

    def __post_init__(self):
        self.block_type = BlockType.TABLE
        if not self.text and (self.headers or self.rows):
            # Generate a structured textual serialization preserving column/row context
            parts = []
            if self.caption:
                parts.append(f"[Table: {self.caption}]")
            if self.headers:
                parts.append(" | ".join(str(h) for h in self.headers))
                parts.append("-" * max(20, sum(len(str(h)) for h in self.headers) + 3 * len(self.headers)))
            for row in self.rows:
                parts.append(" | ".join(str(c) for c in row))
            self.text = "\n".join(parts)

    def to_dict(self) -> Dict[str, Any]:
        data = super().to_dict()
        data["headers"] = self.headers
        data["rows"] = self.rows
        data["caption"] = self.caption
        return data


@dataclass
class ExtractionResult:
    """Normalized result returned by every format extractor."""
    status: ExtractionStatus
    format: str
    content: str = ""
    blocks: List[DocumentBlock] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    stats: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        # Automatically populate stats if missing
        if not self.stats:
            self.stats = {
                "character_count": len(self.content),
                "word_count": len(self.content.split()) if self.content else 0,
                "block_count": len(self.blocks),
            }

    @property
    def is_successful(self) -> bool:
        return self.status in (ExtractionStatus.SUCCESS, ExtractionStatus.SUCCESS_WITH_WARNINGS)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "format": self.format,
            "content": self.content,
            "blocks": [b.to_dict() for b in self.blocks],
            "metadata": self.metadata,
            "warnings": self.warnings,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "stats": self.stats,
        }


class DocumentExtractor(Protocol):
    """Common protocol implemented by all format-specific document extractors."""

    def extract(self, file_source: Union[str, bytes], filename: Optional[str] = None) -> ExtractionResult:
        ...
