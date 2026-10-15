"""
Synthetic Test Fixture Generators for Extraction Tests.
Generates deterministic DOCX, XLSX, CSV, and TXT files in memory.
No real customer or proprietary data used.
"""

import io
import zipfile
from typing import List, Dict, Any, Optional

try:
    import openpyxl
    HAS_OPENPYXL = True
except ImportError:
    HAS_OPENPYXL = False


def create_synthetic_docx_bytes(
    paragraphs: List[str],
    headings: Optional[List[tuple]] = None,
    tables: Optional[List[List[List[str]]]] = None,
) -> bytes:
    """
    Creates a valid in-memory DOCX file with headings, paragraphs, and tables.
    Uses pure OpenXML zip archive generation.
    """
    headings = headings or []
    tables = tables or []

    # Build word/document.xml
    body_xml_parts = []

    # Add headings and paragraphs
    for level, text in headings:
        body_xml_parts.append(
            f'<w:p><w:pPr><w:pStyle w:val="Heading{level}"/></w:pPr><w:r><w:t>{text}</w:t></w:r></w:p>'
        )

    for p in paragraphs:
        body_xml_parts.append(
            f'<w:p><w:r><w:t>{p}</w:t></w:r></w:p>'
        )

    # Add tables
    for tbl in tables:
        body_xml_parts.append('<w:tbl>')
        for row in tbl:
            body_xml_parts.append('<w:tr>')
            for cell in row:
                body_xml_parts.append(
                    f'<w:tc><w:p><w:r><w:t>{cell}</w:t></w:r></w:p></w:tc>'
                )
            body_xml_parts.append('</w:tr>')
        body_xml_parts.append('</w:tbl>')

    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:body>'
        + "".join(body_xml_parts)
        + '</w:body>'
        '</w:document>'
    )

    content_types_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        '</Types>'
    )

    rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
        '</Relationships>'
    )

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types_xml)
        z.writestr("_rels/.rels", rels_xml)
        z.writestr("word/document.xml", document_xml)

    return buf.getvalue()


def create_synthetic_xlsx_bytes(
    sheets: Dict[str, List[List[Any]]],
    hidden_sheets: Optional[List[str]] = None,
) -> bytes:
    """
    Creates a valid in-memory XLSX workbook using openpyxl.
    """
    if not HAS_OPENPYXL:
        raise RuntimeError("openpyxl is required to generate synthetic xlsx fixtures")

    wb = openpyxl.Workbook()
    default_sheet = wb.active
    wb.remove(default_sheet)  # Remove default sheet

    hidden_sheets = hidden_sheets or []

    for name, rows in sheets.items():
        ws = wb.create_sheet(title=name)
        if name in hidden_sheets:
            ws.sheet_state = "hidden"
        for row in rows:
            ws.append(row)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
