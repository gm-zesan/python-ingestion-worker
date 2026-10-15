"""
Word Document (.docx) Extractor.
Extracts headings, paragraphs in reading order, structured tables with cell matrix,
and detects unsupported elements (images, embedded objects).
Supports both python-docx and native standard-library XML fallback.
"""

import io
import re
import zipfile
import xml.etree.ElementTree as ET
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
    # pyrefly: ignore [missing-import]
    import docx
    # pyrefly: ignore [missing-import]
    from docx.table import Table as DocxTable
    # pyrefly: ignore [missing-import]
    from docx.text.paragraph import Paragraph as DocxParagraph
    HAS_PYTHON_DOCX = True
except ImportError:
    HAS_PYTHON_DOCX = False

# OpenXML Namespaces
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS_MAP = {
    "w": W_NS,
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "pic": "http://schemas.openxmlformats.org/drawingml/2006/picture",
}


class DocxExtractor(BaseExtractor):
    """
    Extracts text, headings hierarchy, and table grids from Microsoft Word (.docx) files.
    """

    def extract(self, file_source: Union[str, bytes], filename: Optional[str] = None) -> ExtractionResult:
        try:
            raw_bytes, source_filename = self._read_source_bytes(file_source)
        except EmptyFileException:
            return self._create_failed_result("docx", "FILE_EMPTY", "DOCX file is empty (0 bytes)")
        except ExtractionException as e:
            return self._create_failed_result("docx", e.error_code, e.sanitized_message)
        except Exception as e:
            return self._create_failed_result("docx", "READ_ERROR", f"Error reading file: {str(e)}")

        effective_filename = filename or source_filename or "document.docx"

        # 1. Verify Zip Container and Protect Against Zip Bomb
        try:
            self._check_zip_bomb(raw_bytes)
        except ExtractionException as e:
            return self._create_failed_result("docx", e.error_code, e.sanitized_message)

        # 2. Check for required Word XML entries
        try:
            with zipfile.ZipFile(io.BytesIO(raw_bytes)) as z:
                namelist = z.namelist()
                if "word/document.xml" not in namelist:
                    return self._create_failed_result(
                        "docx",
                        "CORRUPTED_FILE",
                        "Invalid DOCX structure: missing word/document.xml in archive",
                    )
                # Check for images and embedded objects
                image_files = [n for n in namelist if n.startswith("word/media/")]
                embedded_files = [n for n in namelist if n.startswith("word/embeddings/")]
        except zipfile.BadZipFile:
            return self._create_failed_result("docx", "CORRUPTED_FILE", "Malformed DOCX zip archive")

        warnings: List[str] = []
        if image_files:
            warnings.append(f"Document contains {len(image_files)} embedded image(s) which were not OCR processed in this phase")
        if embedded_files:
            warnings.append(f"Document contains {len(embedded_files)} embedded object(s) which were not extracted")

        # 3. Extract Blocks (Headings, Paragraphs, Tables in sequential reading order)
        blocks: List[DocumentBlock] = []
        metadata: Dict[str, Any] = {}

        if HAS_PYTHON_DOCX:
            try:
                blocks, metadata = self._extract_via_python_docx(raw_bytes, warnings)
            except Exception as e:
                warnings.append(f"python-docx encountered an issue ({str(e)}), falling back to XML extraction")
                try:
                    blocks, metadata = self._extract_via_xml(raw_bytes, warnings)
                except (ET.ParseError, CorruptedFileException):
                    return self._create_failed_result("docx", "CORRUPTED_FILE", "Malformed document.xml XML content in DOCX")
        else:
            try:
                blocks, metadata = self._extract_via_xml(raw_bytes, warnings)
            except (ET.ParseError, CorruptedFileException):
                return self._create_failed_result("docx", "CORRUPTED_FILE", "Malformed document.xml XML content in DOCX")

        metadata["image_count"] = len(image_files)
        metadata["embedded_object_count"] = len(embedded_files)
        metadata["filename"] = effective_filename

        # 4. Check for empty document content
        if not blocks or all(not b.text.strip() for b in blocks):
            return self._create_failed_result(
                "docx",
                "FILE_EMPTY",
                "DOCX document contains no readable text or table content",
                warnings=warnings,
                metadata=metadata,
            )

        # 5. Assemble Content and Stats
        content, stats = self._assemble_content_and_stats(
            blocks,
            additional_stats={
                "heading_count": metadata.get("heading_count", 0),
                "paragraph_count": metadata.get("paragraph_count", 0),
                "table_count": metadata.get("table_count", 0),
            },
        )

        status = ExtractionStatus.SUCCESS_WITH_WARNINGS if warnings else ExtractionStatus.SUCCESS

        return ExtractionResult(
            status=status,
            format="docx",
            content=content,
            blocks=blocks,
            metadata=metadata,
            warnings=warnings,
            stats=stats,
        )

    def _extract_via_python_docx(self, raw_bytes: bytes, warnings: List[str]) -> Tuple[List[DocumentBlock], Dict[str, Any]]:
        """Extracts elements in reading order using python-docx."""
        doc = docx.Document(io.BytesIO(raw_bytes))
        blocks: List[DocumentBlock] = []
        order = 0
        heading_count = 0
        paragraph_count = 0
        table_count = 0

        # Traverse body elements in sequential document order (w:p and w:tbl)
        for element in doc.element.body:
            tag = element.tag
            if tag.endswith("p"):
                # Paragraph or Heading
                p = DocxParagraph(element, doc)
                text = p.text.strip()
                if not text:
                    continue

                order += 1
                style_name = p.style.name.lower() if p.style else ""
                heading_level = None

                # Detect heading style
                if "heading" in style_name or "title" in style_name:
                    heading_count += 1
                    match = re.search(r"\d+", style_name)
                    heading_level = int(match.group()) if match else 1
                    blocks.append(
                        DocumentBlock(
                            block_type=BlockType.HEADING,
                            text=text,
                            order=order,
                            level=heading_level,
                            metadata={"style": p.style.name},
                        )
                    )
                else:
                    paragraph_count += 1
                    blocks.append(
                        DocumentBlock(
                            block_type=BlockType.PARAGRAPH,
                            text=text,
                            order=order,
                            metadata={"style": p.style.name if p.style else "Normal"},
                        )
                    )

            elif tag.endswith("tbl"):
                # Table in reading order
                t = DocxTable(element, doc)
                table_matrix = []
                for row in t.rows:
                    row_cells = [cell.text.strip().replace("\n", " ") for cell in row.cells]
                    table_matrix.append(row_cells)

                if table_matrix:
                    order += 1
                    table_count += 1
                    headers = table_matrix[0] if table_matrix else []
                    data_rows = table_matrix[1:] if len(table_matrix) > 1 else []
                    blocks.append(
                        TableBlock(
                            order=order,
                            text="",
                            headers=headers,
                            rows=data_rows,
                            metadata={"row_count": len(table_matrix), "col_count": len(headers)},
                        )
                    )

        metadata = {
            "extractor": "python-docx",
            "heading_count": heading_count,
            "paragraph_count": paragraph_count,
            "table_count": table_count,
        }
        return blocks, metadata

    def _extract_via_xml(self, raw_bytes: bytes, warnings: List[str]) -> Tuple[List[DocumentBlock], Dict[str, Any]]:
        """Fallback extractor using native xml.etree.ElementTree on word/document.xml."""
        try:
            with zipfile.ZipFile(io.BytesIO(raw_bytes)) as z:
                xml_bytes = z.read("word/document.xml")
            root = ET.fromstring(xml_bytes)
        except ET.ParseError as e:
            raise CorruptedFileException("Malformed XML in word/document.xml") from e

        body = root.find(f"{{{W_NS}}}body")
        if body is None:
            return [], {"extractor": "xml_fallback", "heading_count": 0, "paragraph_count": 0, "table_count": 0}

        blocks: List[DocumentBlock] = []
        order = 0
        heading_count = 0
        paragraph_count = 0
        table_count = 0

        for child in body:
            tag = child.tag
            if tag == f"{{{W_NS}}}p":
                # Paragraph or heading
                text_runs = [t.text for t in child.iter(f"{{{W_NS}}}t") if t.text]
                p_text = "".join(text_runs).strip()
                if not p_text:
                    continue

                order += 1
                # Inspect pStyle for headings
                p_style = child.find(f".//{{{W_NS}}}pStyle")
                style_val = p_style.attrib.get(f"{{{W_NS}}}val", "").lower() if p_style is not None else ""
                if "heading" in style_val or "title" in style_val:
                    heading_count += 1
                    match = re.search(r"\d+", style_val)
                    level = int(match.group()) if match else 1
                    blocks.append(
                        DocumentBlock(
                            block_type=BlockType.HEADING,
                            text=p_text,
                            order=order,
                            level=level,
                            metadata={"style": style_val},
                        )
                    )
                else:
                    paragraph_count += 1
                    blocks.append(
                        DocumentBlock(
                            block_type=BlockType.PARAGRAPH,
                            text=p_text,
                            order=order,
                            metadata={"style": style_val or "Normal"},
                        )
                    )

            elif tag == f"{{{W_NS}}}tbl":
                # Table in sequential reading order
                table_matrix = []
                for row_elem in child.findall(f"{{{W_NS}}}tr"):
                    row_cells = []
                    for cell_elem in row_elem.findall(f"{{{W_NS}}}tc"):
                        p_texts = []
                        for p in cell_elem.findall(f"{{{W_NS}}}p"):
                            pt = "".join(t.text for t in p.iter(f"{{{W_NS}}}t") if t.text).strip()
                            if pt:
                                p_texts.append(pt)
                        cell_text = " ".join(p_texts)
                        row_cells.append(cell_text)
                    table_matrix.append(row_cells)

                if table_matrix:
                    order += 1
                    table_count += 1
                    headers = table_matrix[0] if table_matrix else []
                    data_rows = table_matrix[1:] if len(table_matrix) > 1 else []
                    blocks.append(
                        TableBlock(
                            order=order,
                            text="",
                            headers=headers,
                            rows=data_rows,
                            metadata={"row_count": len(table_matrix), "col_count": len(headers)},
                        )
                    )

        metadata = {
            "extractor": "xml_fallback",
            "heading_count": heading_count,
            "paragraph_count": paragraph_count,
            "table_count": table_count,
        }
        return blocks, metadata
