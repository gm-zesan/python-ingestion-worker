"""
Deterministic fixture generator for the Document Extraction Benchmark Suite.
Generates 45 real file fixtures across TXT, DOCX, XLSX, and CSV with matching GroundTruth.
All byte payloads are deterministic and offline.
"""

import os
import io
import csv
import zipfile
from typing import Dict, Tuple, List, Any, Optional
import openpyxl

from .models import BenchmarkFixture, GroundTruth


def format_expected_table_text(
    headers: List[str],
    rows: List[List[str]],
    caption: Optional[str] = None,
) -> str:
    """Helper implementing exact TableBlock serialization per app/contracts.py."""
    parts = []
    if caption:
        parts.append(f"[Table: {caption}]")
    if headers:
        parts.append(" | ".join(str(h) for h in headers))
        parts.append("-" * max(20, sum(len(str(h)) for h in headers) + 3 * len(headers)))
    for row in rows:
        parts.append(" | ".join(str(c) for c in row))
    return "\n".join(parts)


def _create_docx_bytes(
    paragraphs: Optional[List[Tuple[str, str]]] = None,
    tables: Optional[List[List[List[str]]]] = None,
    elements: Optional[List[Tuple[str, Any]]] = None,
    include_image: bool = False,
    include_embedded: bool = False,
    empty_body: bool = False,
) -> bytes:
    """Helper to build a valid OpenXML DOCX package in memory with deterministic timestamps."""
    doc_xml_parts = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">',
        '<w:body>',
    ]

    if not empty_body:
        if elements:
            for elem_type, data in elements:
                if elem_type == "paragraph":
                    style, text = data
                    p_style = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
                    doc_xml_parts.append(f'<w:p>{p_style}<w:r><w:t>{text}</w:t></w:r></w:p>')
                elif elem_type == "table":
                    doc_xml_parts.append('<w:tbl>')
                    for row in data:
                        doc_xml_parts.append('<w:tr>')
                        for cell in row:
                            doc_xml_parts.append(f'<w:tc><w:p><w:r><w:t>{cell}</w:t></w:r></w:p></w:tc>')
                        doc_xml_parts.append('</w:tr>')
                    doc_xml_parts.append('</w:tbl>')
                elif elem_type == "multiparagraph_table":
                    doc_xml_parts.append('<w:tbl>')
                    for row in data:
                        doc_xml_parts.append('<w:tr>')
                        for cell_paras in row:
                            doc_xml_parts.append('<w:tc>')
                            for p_text in cell_paras:
                                doc_xml_parts.append(f'<w:p><w:r><w:t>{p_text}</w:t></w:r></w:p>')
                            doc_xml_parts.append('</w:tc>')
                        doc_xml_parts.append('</w:tr>')
                    doc_xml_parts.append('</w:tbl>')
        else:
            paragraphs = paragraphs or []
            tables = tables or []
            for style, text in paragraphs:
                p_style = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
                doc_xml_parts.append(f'<w:p>{p_style}<w:r><w:t>{text}</w:t></w:r></w:p>')
            for tbl in tables:
                doc_xml_parts.append('<w:tbl>')
                for row in tbl:
                    doc_xml_parts.append('<w:tr>')
                    for cell in row:
                        doc_xml_parts.append(f'<w:tc><w:p><w:r><w:t>{cell}</w:t></w:r></w:p></w:tc>')
                    doc_xml_parts.append('</w:tr>')
                doc_xml_parts.append('</w:tbl>')

    doc_xml_parts.append('</w:body></w:document>')
    doc_xml = "".join(doc_xml_parts)

    content_types = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">',
        '  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>',
        '  <Default Extension="xml" ContentType="application/xml"/>',
    ]
    if include_image:
        content_types.append('  <Default Extension="png" ContentType="image/png"/>')
    if include_embedded:
        content_types.append('  <Default Extension="bin" ContentType="application/vnd.openxmlformats-officedocument.oleObject"/>')
    content_types.append('  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>')
    content_types.append('</Types>')

    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">\n'
        '  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>\n'
        '</Relationships>'
    )

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", "\n".join(content_types))
        zf.writestr("_rels/.rels", rels)
        zf.writestr("word/document.xml", doc_xml)
        if include_image:
            zf.writestr("word/media/image1.png", b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" + b"\x00" * 30)
        if include_embedded:
            zf.writestr("word/embeddings/oleObject1.bin", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 32)

    return buf.getvalue()


def generate_all_fixtures() -> List[Tuple[BenchmarkFixture, GroundTruth]]:
    """Generates all 45 fixtures and their corresponding ground truth expectations."""
    fixtures_with_gt: List[Tuple[BenchmarkFixture, GroundTruth]] = []

    # =========================================================================
    # 1. TXT FIXTURES (9)
    # =========================================================================

    # 1.1 Standard English
    en_txt = (
        "Customer Support Policy\n\n"
        "Orders placed before 3:00 PM are processed same day.\n\n"
        "Return requests are accepted within 7 business days."
    )
    fixtures_with_gt.append((
        BenchmarkFixture(
            fixture_id="BENCH-TXT-EN-01",
            filename="BENCH-TXT-EN-01.txt",
            format="txt",
            category="standard",
            scenario="Standard English multi-paragraph policy",
            raw_bytes=en_txt.encode("utf-8"),
        ),
        GroundTruth(
            fixture_id="BENCH-TXT-EN-01",
            filename="BENCH-TXT-EN-01.txt",
            format="txt",
            category="standard",
            scenario="Standard English multi-paragraph policy",
            expected_status="success",
            accepted_statuses=["success"],
            expected_text=en_txt,
            expected_blocks=[
                {"block_type": "paragraph", "text": "Customer Support Policy"},
                {"block_type": "paragraph", "text": "Orders placed before 3:00 PM are processed same day."},
                {"block_type": "paragraph", "text": "Return requests are accepted within 7 business days."},
            ],
            expected_metadata={"encoding": "utf-8"},
            provisional_thresholds={"max_cer": 0.0, "min_car": 1.0, "require_exact_structure": True},
        )
    ))

    # 1.2 Bengali Unicode with Ligatures, ZWJ/ZWNJ, and Currency
    bn_zwj = "র\u200d্যাপিড"  # ya-phala with ZWJ
    bn_zwnj = "ক্\u200cষ"    # explicit non-ligature with ZWNJ
    bn_txt = (
        f"ডেলিভারি পলিসি ও শর্তাবলী\n\n"
        f"ঢাকা সিটির ভিতরে {bn_zwj} সার্ভিস চার্জ ৬০৳ এবং ২ কার্যদিবসের মধ্যে ডেলিভারি সম্পন্ন হবে।\n\n"
        f"অগ্রিম পেমেন্ট বিকাশ বা নগদ এর মাধ্যমে পরিশোধ করা যাবে ({bn_zwnj})।"
    )
    fixtures_with_gt.append((
        BenchmarkFixture(
            fixture_id="BENCH-TXT-BN-01",
            filename="BENCH-TXT-BN-01.txt",
            format="txt",
            category="multilingual",
            scenario="Bengali Unicode with ligatures, ZWJ/ZWNJ, and currency",
            raw_bytes=bn_txt.encode("utf-8"),
        ),
        GroundTruth(
            fixture_id="BENCH-TXT-BN-01",
            filename="BENCH-TXT-BN-01.txt",
            format="txt",
            category="multilingual",
            scenario="Bengali Unicode with ligatures, ZWJ/ZWNJ, and currency",
            expected_status="success",
            accepted_statuses=["success"],
            expected_text=bn_txt,
            expected_blocks=[
                {"block_type": "paragraph", "text": "ডেলিভারি পলিসি ও শর্তাবলী"},
                {"block_type": "paragraph", "text": f"ঢাকা সিটির ভিতরে {bn_zwj} সার্ভিস চার্জ ৬০৳ এবং ২ কার্যদিবসের মধ্যে ডেলিভারি সম্পন্ন হবে।"},
                {"block_type": "paragraph", "text": f"অগ্রিম পেমেন্ট বিকাশ বা নগদ এর মাধ্যমে পরিশোধ করা যাবে ({bn_zwnj})।"},
            ],
            expected_metadata={"encoding": "utf-8"},
            provisional_thresholds={"max_cer": 0.0, "min_car": 1.0, "require_exact_structure": True},
        )
    ))

    # 1.3 Mixed English / Bengali / Banglish
    mix_txt = (
        "Q: Order kivabe confirm korbo?\n\n"
        "A: Add to cart kore checkout korun. Cash on Delivery (COD) available ache.\n\n"
        "Dhaka te 2 days er moddhe delivery hoye jabe."
    )
    fixtures_with_gt.append((
        BenchmarkFixture(
            fixture_id="BENCH-TXT-MIX-01",
            filename="BENCH-TXT-MIX-01.txt",
            format="txt",
            category="multilingual",
            scenario="Mixed English, Bengali, and Banglish Q&A",
            raw_bytes=mix_txt.encode("utf-8"),
        ),
        GroundTruth(
            fixture_id="BENCH-TXT-MIX-01",
            filename="BENCH-TXT-MIX-01.txt",
            format="txt",
            category="multilingual",
            scenario="Mixed English, Bengali, and Banglish Q&A",
            expected_status="success",
            accepted_statuses=["success"],
            expected_text=mix_txt,
            expected_blocks=[
                {"block_type": "paragraph", "text": "Q: Order kivabe confirm korbo?"},
                {"block_type": "paragraph", "text": "A: Add to cart kore checkout korun. Cash on Delivery (COD) available ache."},
                {"block_type": "paragraph", "text": "Dhaka te 2 days er moddhe delivery hoye jabe."},
            ],
            expected_metadata={"encoding": "utf-8"},
            provisional_thresholds={"max_cer": 0.0, "min_car": 1.0, "require_exact_structure": True},
        )
    ))

    # 1.4 UTF-8 with BOM
    bom_raw = b"\xef\xbb\xbf" + en_txt.encode("utf-8")
    fixtures_with_gt.append((
        BenchmarkFixture(
            fixture_id="BENCH-TXT-BOM-01",
            filename="BENCH-TXT-BOM-01.txt",
            format="txt",
            category="encoding",
            scenario="UTF-8 with Byte Order Mark (BOM)",
            raw_bytes=bom_raw,
        ),
        GroundTruth(
            fixture_id="BENCH-TXT-BOM-01",
            filename="BENCH-TXT-BOM-01.txt",
            format="txt",
            category="encoding",
            scenario="UTF-8 with Byte Order Mark (BOM)",
            expected_status="success",
            accepted_statuses=["success"],
            expected_text=en_txt,  # BOM must be stripped
            expected_blocks=[
                {"block_type": "paragraph", "text": "Customer Support Policy"},
                {"block_type": "paragraph", "text": "Orders placed before 3:00 PM are processed same day."},
                {"block_type": "paragraph", "text": "Return requests are accepted within 7 business days."},
            ],
            expected_metadata={"encoding": "utf-8-sig", "has_bom": True},
            provisional_thresholds={"max_cer": 0.0, "min_car": 1.0, "require_exact_structure": True},
        )
    ))

    # 1.5 Windows-1252 Legacy Encoding with smart quotes and em-dash
    cp_text = "Special “quoted” term — café résumé legacy policy.\n\nAll contractual agreements remain binding."
    cp_bytes = cp_text.encode("cp1252")
    fixtures_with_gt.append((
        BenchmarkFixture(
            fixture_id="BENCH-TXT-CP1252-01",
            filename="BENCH-TXT-CP1252-01.txt",
            format="txt",
            category="encoding",
            scenario="Windows-1252 (CP1252) legacy encoding with smart quotes and em-dash",
            raw_bytes=cp_bytes,
        ),
        GroundTruth(
            fixture_id="BENCH-TXT-CP1252-01",
            filename="BENCH-TXT-CP1252-01.txt",
            format="txt",
            category="encoding",
            scenario="Windows-1252 (CP1252) legacy encoding with smart quotes and em-dash",
            expected_status="success",
            accepted_statuses=["success"],
            expected_text=cp_text,
            expected_blocks=[
                {"block_type": "paragraph", "text": "Special “quoted” term — café résumé legacy policy."},
                {"block_type": "paragraph", "text": "All contractual agreements remain binding."},
            ],
            provisional_thresholds={"max_cer": 0.0, "min_car": 1.0, "require_exact_structure": True},
        )
    ))

    # 1.6 0-byte Empty File
    fixtures_with_gt.append((
        BenchmarkFixture(
            fixture_id="BENCH-TXT-EMPTY-01",
            filename="BENCH-TXT-EMPTY-01.txt",
            format="txt",
            category="edge_cases",
            scenario="Zero-byte empty text document",
            raw_bytes=b"",
        ),
        GroundTruth(
            fixture_id="BENCH-TXT-EMPTY-01",
            filename="BENCH-TXT-EMPTY-01.txt",
            format="txt",
            category="edge_cases",
            scenario="Zero-byte empty text document",
            expected_status="failed",
            accepted_statuses=["failed"],
            expected_error_code="FILE_EMPTY",
            expected_text="",
            expected_blocks=[],
            provisional_thresholds={"max_cer": 0.0, "min_car": 1.0, "require_exact_structure": True},
        )
    ))

    # 1.7 Whitespace-only Text File
    fixtures_with_gt.append((
        BenchmarkFixture(
            fixture_id="BENCH-TXT-WS-01",
            filename="BENCH-TXT-WS-01.txt",
            format="txt",
            category="edge_cases",
            scenario="Whitespace-only text document containing tabs and newlines",
            raw_bytes=b"   \t\n  \r\n   \n\t  ",
        ),
        GroundTruth(
            fixture_id="BENCH-TXT-WS-01",
            filename="BENCH-TXT-WS-01.txt",
            format="txt",
            category="edge_cases",
            scenario="Whitespace-only text document containing tabs and newlines",
            expected_status="failed",
            accepted_statuses=["failed"],
            expected_error_code="FILE_EMPTY",
            expected_text="",
            expected_blocks=[],
            provisional_thresholds={"max_cer": 0.0, "min_car": 1.0, "require_exact_structure": True},
        )
    ))

    # 1.8 Disguised Binary File
    binary_payload = b"\x7fELF\x02\x01\x01\x00" + b"\x00" * 32 + b"\xff\xfe\x00\x00\xaa\xbb"
    fixtures_with_gt.append((
        BenchmarkFixture(
            fixture_id="BENCH-TXT-BINARY-01",
            filename="BENCH-TXT-BINARY-01.txt",
            format="txt",
            category="edge_cases",
            scenario="Disguised binary ELF executable with .txt extension",
            raw_bytes=binary_payload,
        ),
        GroundTruth(
            fixture_id="BENCH-TXT-BINARY-01",
            filename="BENCH-TXT-BINARY-01.txt",
            format="txt",
            category="edge_cases",
            scenario="Disguised binary ELF executable with .txt extension",
            expected_status="failed",
            accepted_statuses=["failed"],
            expected_error_code="INVALID_SIGNATURE",
            expected_text="",
            expected_blocks=[],
            provisional_thresholds={"max_cer": 0.0, "min_car": 1.0, "require_exact_structure": True},
        )
    ))

    # 1.9 High Mojibake Text File
    mojibake_text = "Primary English header.\n\n" + ("\ufffd" * 30) + "\n\nTrailing valid paragraph text."
    fixtures_with_gt.append((
        BenchmarkFixture(
            fixture_id="BENCH-TXT-MOJIBAKE-01",
            filename="BENCH-TXT-MOJIBAKE-01.txt",
            format="txt",
            category="edge_cases",
            scenario="Text document with excessive replacement characters triggering needs_review",
            raw_bytes=mojibake_text.encode("utf-8"),
        ),
        GroundTruth(
            fixture_id="BENCH-TXT-MOJIBAKE-01",
            filename="BENCH-TXT-MOJIBAKE-01.txt",
            format="txt",
            category="edge_cases",
            scenario="Text document with excessive replacement characters triggering needs_review",
            expected_status="needs_review",
            accepted_statuses=["needs_review"],
            expected_warnings=["mojibake"],
            expected_text=mojibake_text,
            expected_blocks=[
                {"block_type": "paragraph"},
                {"block_type": "paragraph"},
                {"block_type": "paragraph"},
            ],
            provisional_thresholds={"max_cer": 0.0, "min_car": 1.0, "require_exact_structure": True},
        )
    ))

    # =========================================================================
    # 2. DOCX FIXTURES (12)
    # =========================================================================

    # 2.1 Standard English DOCX
    docx_en_bytes = _create_docx_bytes(
        paragraphs=[
            ("Heading1", "Store Operations Guide"),
            ("", "Our fulfillment center operates seven days a week."),
            ("Heading2", "Shipping Windows"),
            ("", "Orders placed before 2:00 PM ship on the same calendar day."),
        ]
    )
    docx_en_text = (
        "Store Operations Guide\n\n"
        "Our fulfillment center operates seven days a week.\n\n"
        "Shipping Windows\n\n"
        "Orders placed before 2:00 PM ship on the same calendar day."
    )
    fixtures_with_gt.append((
        BenchmarkFixture(
            fixture_id="BENCH-DOCX-EN-01",
            filename="BENCH-DOCX-EN-01.docx",
            format="docx",
            category="standard",
            scenario="Standard English DOCX with headings and body paragraphs",
            raw_bytes=docx_en_bytes,
        ),
        GroundTruth(
            fixture_id="BENCH-DOCX-EN-01",
            filename="BENCH-DOCX-EN-01.docx",
            format="docx",
            category="standard",
            scenario="Standard English DOCX with headings and body paragraphs",
            expected_status="success",
            accepted_statuses=["success"],
            expected_text=docx_en_text,
            expected_blocks=[
                {"block_type": "heading", "level": 1, "text": "Store Operations Guide"},
                {"block_type": "paragraph", "text": "Our fulfillment center operates seven days a week."},
                {"block_type": "heading", "level": 2, "text": "Shipping Windows"},
                {"block_type": "paragraph", "text": "Orders placed before 2:00 PM ship on the same calendar day."},
            ],
            provisional_thresholds={"max_cer": 0.0, "min_car": 1.0, "require_exact_structure": True},
        )
    ))

    # 2.2 Bengali DOCX
    docx_bn_bytes = _create_docx_bytes(
        paragraphs=[
            ("Heading1", "পণ্য ফেরত ও রিফান্ড নীতিমালা"),
            ("", "পণ্য হাতে পাওয়ার ৭ দিনের মধ্যে ফেরত পাঠানোর অনুরোধ জানাতে হবে।"),
            ("", "ত্রুটিপূর্ণ পণ্যের ক্ষেত্রে সম্পূর্ণ মূল্য ফেরত প্রদান করা হবে।"),
        ]
    )
    docx_bn_text = (
        "পণ্য ফেরত ও রিফান্ড নীতিমালা\n\n"
        "পণ্য হাতে পাওয়ার ৭ দিনের মধ্যে ফেরত পাঠানোর অনুরোধ জানাতে হবে।\n\n"
        "ত্রুটিপূর্ণ পণ্যের ক্ষেত্রে সম্পূর্ণ মূল্য ফেরত প্রদান করা হবে।"
    )
    fixtures_with_gt.append((
        BenchmarkFixture(
            fixture_id="BENCH-DOCX-BN-01",
            filename="BENCH-DOCX-BN-01.docx",
            format="docx",
            category="multilingual",
            scenario="Bengali DOCX policy with complex Bengali script",
            raw_bytes=docx_bn_bytes,
        ),
        GroundTruth(
            fixture_id="BENCH-DOCX-BN-01",
            filename="BENCH-DOCX-BN-01.docx",
            format="docx",
            category="multilingual",
            scenario="Bengali DOCX policy with complex Bengali script",
            expected_status="success",
            accepted_statuses=["success"],
            expected_text=docx_bn_text,
            expected_blocks=[
                {"block_type": "heading", "level": 1, "text": "পণ্য ফেরত ও রিফান্ড নীতিমালা"},
                {"block_type": "paragraph", "text": "পণ্য হাতে পাওয়ার ৭ দিনের মধ্যে ফেরত পাঠানোর অনুরোধ জানাতে হবে।"},
                {"block_type": "paragraph", "text": "ত্রুটিপূর্ণ পণ্যের ক্ষেত্রে সম্পূর্ণ মূল্য ফেরত প্রদান করা হবে।"},
            ],
            provisional_thresholds={"max_cer": 0.0, "min_car": 1.0, "require_exact_structure": True},
        )
    ))

    # 2.3 Hierarchical Document Structure (H1, H2, H3)
    docx_struct_bytes = _create_docx_bytes(
        paragraphs=[
            ("Heading1", "Section 1: General Information"),
            ("", "Introductory overview paragraph."),
            ("Heading2", "Section 1.1: Eligibility Criteria"),
            ("", "Detailed criteria guidelines."),
            ("Heading3", "Section 1.1.1: Verification Steps"),
            ("", "Final step-by-step checklist."),
        ]
    )
    docx_struct_text = (
        "Section 1: General Information\n\n"
        "Introductory overview paragraph.\n\n"
        "Section 1.1: Eligibility Criteria\n\n"
        "Detailed criteria guidelines.\n\n"
        "Section 1.1.1: Verification Steps\n\n"
        "Final step-by-step checklist."
    )
    fixtures_with_gt.append((
        BenchmarkFixture(
            fixture_id="BENCH-DOCX-STRUCT-01",
            filename="BENCH-DOCX-STRUCT-01.docx",
            format="docx",
            category="structure",
            scenario="Deep heading hierarchy (H1 -> H2 -> H3) with intervening text",
            raw_bytes=docx_struct_bytes,
        ),
        GroundTruth(
            fixture_id="BENCH-DOCX-STRUCT-01",
            filename="BENCH-DOCX-STRUCT-01.docx",
            format="docx",
            category="structure",
            scenario="Deep heading hierarchy (H1 -> H2 -> H3) with intervening text",
            expected_status="success",
            accepted_statuses=["success"],
            expected_text=docx_struct_text,
            expected_blocks=[
                {"block_type": "heading", "level": 1, "text": "Section 1: General Information"},
                {"block_type": "paragraph", "text": "Introductory overview paragraph."},
                {"block_type": "heading", "level": 2, "text": "Section 1.1: Eligibility Criteria"},
                {"block_type": "paragraph", "text": "Detailed criteria guidelines."},
                {"block_type": "heading", "level": 3, "text": "Section 1.1.1: Verification Steps"},
                {"block_type": "paragraph", "text": "Final step-by-step checklist."},
            ],
            provisional_thresholds={"max_cer": 0.0, "min_car": 1.0, "require_exact_structure": True},
        )
    ))

    # 2.4 Table in Reading Order
    docx_tbl_headers = ["Zone", "Charge", "Duration"]
    docx_tbl_rows = [
        ["Inside Dhaka", "60 BDT", "24-48 Hours"],
        ["Outside Dhaka", "130 BDT", "3-5 Days"],
    ]
    docx_tbl_bytes = _create_docx_bytes(
        paragraphs=[("Heading1", "Delivery Rates Overview")],
        tables=[[docx_tbl_headers] + docx_tbl_rows],
    )
    docx_tbl_expected_str = format_expected_table_text(docx_tbl_headers, docx_tbl_rows)
    docx_tbl_text = f"Delivery Rates Overview\n\n{docx_tbl_expected_str}"
    fixtures_with_gt.append((
        BenchmarkFixture(
            fixture_id="BENCH-DOCX-TBL-01",
            filename="BENCH-DOCX-TBL-01.docx",
            format="docx",
            category="tables",
            scenario="Heading followed by structured tabular matrix",
            raw_bytes=docx_tbl_bytes,
        ),
        GroundTruth(
            fixture_id="BENCH-DOCX-TBL-01",
            filename="BENCH-DOCX-TBL-01.docx",
            format="docx",
            category="tables",
            scenario="Heading followed by structured tabular matrix",
            expected_status="success",
            accepted_statuses=["success"],
            expected_text=docx_tbl_text,
            expected_blocks=[
                {"block_type": "heading", "level": 1, "text": "Delivery Rates Overview"},
                {"block_type": "table", "headers": docx_tbl_headers, "rows": docx_tbl_rows, "row_count": 2},
            ],
            provisional_thresholds={"max_cer": 0.0, "min_car": 1.0, "require_exact_structure": True},
        )
    ))

    # 2.5 Interleaved Paragraphs and Tables
    it_t1_headers = ["Metric", "Q1"]
    it_t1_rows = [["Revenue", "100k"]]
    it_t2_headers = ["Channel", "Share"]
    it_t2_rows = [["Online", "80%"]]

    it_elements = [
        ("paragraph", ("Heading1", "Executive Summary")),
        ("paragraph", ("", "Overview of preliminary quarter financials.")),
        ("table", [it_t1_headers] + it_t1_rows),
        ("paragraph", ("", "Detailed revenue distribution by source.")),
        ("table", [it_t2_headers] + it_t2_rows),
        ("paragraph", ("", "Final outlook is positive.")),
    ]
    docx_interleave_bytes = _create_docx_bytes(elements=it_elements)
    docx_interleave_text = (
        "Executive Summary\n\n"
        "Overview of preliminary quarter financials.\n\n"
        f"{format_expected_table_text(it_t1_headers, it_t1_rows)}\n\n"
        "Detailed revenue distribution by source.\n\n"
        f"{format_expected_table_text(it_t2_headers, it_t2_rows)}\n\n"
        "Final outlook is positive."
    )
    fixtures_with_gt.append((
        BenchmarkFixture(
            fixture_id="BENCH-DOCX-INTERLEAVE-01",
            filename="BENCH-DOCX-INTERLEAVE-01.docx",
            format="docx",
            category="structure",
            scenario="Sequential interleaving of headings, paragraphs, and multiple tables",
            raw_bytes=docx_interleave_bytes,
        ),
        GroundTruth(
            fixture_id="BENCH-DOCX-INTERLEAVE-01",
            filename="BENCH-DOCX-INTERLEAVE-01.docx",
            format="docx",
            category="structure",
            scenario="Sequential interleaving of headings, paragraphs, and multiple tables",
            expected_status="success",
            accepted_statuses=["success"],
            expected_text=docx_interleave_text,
            expected_blocks=[
                {"block_type": "heading", "level": 1, "text": "Executive Summary"},
                {"block_type": "paragraph", "text": "Overview of preliminary quarter financials."},
                {"block_type": "table", "headers": it_t1_headers, "rows": it_t1_rows, "row_count": 1},
                {"block_type": "paragraph", "text": "Detailed revenue distribution by source."},
                {"block_type": "table", "headers": it_t2_headers, "rows": it_t2_rows, "row_count": 1},
                {"block_type": "paragraph", "text": "Final outlook is positive."},
            ],
            provisional_thresholds={"max_cer": 0.0, "min_car": 1.0, "require_exact_structure": True},
        )
    ))

    # 2.6 Multiple Consecutive Tables
    mt1_h = ["A", "B"]
    mt1_r = [["1", "2"]]
    mt2_h = ["C", "D"]
    mt2_r = [["3", "4"]]
    docx_multitbl_bytes = _create_docx_bytes(
        tables=[[mt1_h] + mt1_r, [mt2_h] + mt2_r]
    )
    docx_multitbl_text = f"{format_expected_table_text(mt1_h, mt1_r)}\n\n{format_expected_table_text(mt2_h, mt2_r)}"
    fixtures_with_gt.append((
        BenchmarkFixture(
            fixture_id="BENCH-DOCX-MULTITBL-01",
            filename="BENCH-DOCX-MULTITBL-01.docx",
            format="docx",
            category="tables",
            scenario="Multiple consecutive tables without intervening text",
            raw_bytes=docx_multitbl_bytes,
        ),
        GroundTruth(
            fixture_id="BENCH-DOCX-MULTITBL-01",
            filename="BENCH-DOCX-MULTITBL-01.docx",
            format="docx",
            category="tables",
            scenario="Multiple consecutive tables without intervening text",
            expected_status="success",
            accepted_statuses=["success"],
            expected_text=docx_multitbl_text,
            expected_blocks=[
                {"block_type": "table", "headers": mt1_h, "rows": mt1_r, "row_count": 1},
                {"block_type": "table", "headers": mt2_h, "rows": mt2_r, "row_count": 1},
            ],
            provisional_thresholds={"max_cer": 0.0, "min_car": 1.0, "require_exact_structure": True},
        )
    ))

    # 2.7 Multiple Paragraphs in Table Cells
    mp_headers = ["Field", "Instructions"]
    mp_rows = [
        ["Address", "Line 1: Street\nLine 2: City"],
    ]
    # In OpenXML fallback XML extractor, multiple <w:p> in a <w:tc> are joined by space
    mp_extracted_rows = [["Address", "Line 1: Street Line 2: City"]]
    mp_elements = [
        ("multiparagraph_table", [
            [["Field"], ["Instructions"]],
            [["Address"], ["Line 1: Street", "Line 2: City"]],
        ])
    ]
    docx_multipc_bytes = _create_docx_bytes(elements=mp_elements)
    docx_multipc_text = format_expected_table_text(mp_headers, mp_extracted_rows)
    fixtures_with_gt.append((
        BenchmarkFixture(
            fixture_id="BENCH-DOCX-MULTIPC-01",
            filename="BENCH-DOCX-MULTIPC-01.docx",
            format="docx",
            category="tables",
            scenario="Table with multiple paragraph elements inside individual cells",
            raw_bytes=docx_multipc_bytes,
        ),
        GroundTruth(
            fixture_id="BENCH-DOCX-MULTIPC-01",
            filename="BENCH-DOCX-MULTIPC-01.docx",
            format="docx",
            category="tables",
            scenario="Table with multiple paragraph elements inside individual cells",
            expected_status="success",
            accepted_statuses=["success"],
            expected_text=docx_multipc_text,
            expected_blocks=[
                {"block_type": "table", "headers": mp_headers, "rows": mp_extracted_rows, "row_count": 1},
            ],
            known_unsupported_content="OpenXML fallback flattens intra-cell paragraphs into single-space delimited string",
            provisional_thresholds={"max_cer": 0.0, "min_car": 1.0, "require_exact_structure": True},
        )
    ))

    # 2.8 Embedded Image Warning
    docx_img_bytes = _create_docx_bytes(
        paragraphs=[
            ("Heading1", "Hardware Architecture"),
            ("", "The network connectivity diagram is illustrated below."),
        ],
        include_image=True,
    )
    docx_img_text = (
        "Hardware Architecture\n\n"
        "The network connectivity diagram is illustrated below."
    )
    fixtures_with_gt.append((
        BenchmarkFixture(
            fixture_id="BENCH-DOCX-IMG-01",
            filename="BENCH-DOCX-IMG-01.docx",
            format="docx",
            category="edge_cases",
            scenario="DOCX with embedded non-text media (images)",
            raw_bytes=docx_img_bytes,
        ),
        GroundTruth(
            fixture_id="BENCH-DOCX-IMG-01",
            filename="BENCH-DOCX-IMG-01.docx",
            format="docx",
            category="edge_cases",
            scenario="DOCX with embedded non-text media (images)",
            expected_status="success_with_warnings",
            accepted_statuses=["success_with_warnings"],
            expected_warnings=["embedded image"],
            expected_text=docx_img_text,
            expected_blocks=[
                {"block_type": "heading", "level": 1, "text": "Hardware Architecture"},
                {"block_type": "paragraph", "text": "The network connectivity diagram is illustrated below."},
            ],
            expected_metadata={"image_count": 1},
            provisional_thresholds={"max_cer": 0.0, "min_car": 1.0, "require_exact_structure": True},
        )
    ))

    # 2.9 Embedded OLE Object Warning
    docx_embed_bytes = _create_docx_bytes(
        paragraphs=[
            ("Heading1", "Attached Financial Worksheet"),
            ("", "Double click the embedded sheet to activate."),
        ],
        include_embedded=True,
    )
    docx_embed_text = (
        "Attached Financial Worksheet\n\n"
        "Double click the embedded sheet to activate."
    )
    fixtures_with_gt.append((
        BenchmarkFixture(
            fixture_id="BENCH-DOCX-EMBED-01",
            filename="BENCH-DOCX-EMBED-01.docx",
            format="docx",
            category="edge_cases",
            scenario="DOCX with embedded unsupported OLE objects",
            raw_bytes=docx_embed_bytes,
        ),
        GroundTruth(
            fixture_id="BENCH-DOCX-EMBED-01",
            filename="BENCH-DOCX-EMBED-01.docx",
            format="docx",
            category="edge_cases",
            scenario="DOCX with embedded unsupported OLE objects",
            expected_status="success_with_warnings",
            accepted_statuses=["success_with_warnings"],
            expected_warnings=["embedded object"],
            expected_text=docx_embed_text,
            expected_blocks=[
                {"block_type": "heading", "level": 1, "text": "Attached Financial Worksheet"},
                {"block_type": "paragraph", "text": "Double click the embedded sheet to activate."},
            ],
            expected_metadata={"embedded_object_count": 1},
            provisional_thresholds={"max_cer": 0.0, "min_car": 1.0, "require_exact_structure": True},
        )
    ))

    # 2.10 Valid Empty DOCX
    docx_empty_bytes = _create_docx_bytes(empty_body=True)
    fixtures_with_gt.append((
        BenchmarkFixture(
            fixture_id="BENCH-DOCX-EMPTY-01",
            filename="BENCH-DOCX-EMPTY-01.docx",
            format="docx",
            category="edge_cases",
            scenario="Valid DOCX zip package with empty body tags",
            raw_bytes=docx_empty_bytes,
        ),
        GroundTruth(
            fixture_id="BENCH-DOCX-EMPTY-01",
            filename="BENCH-DOCX-EMPTY-01.docx",
            format="docx",
            category="edge_cases",
            scenario="Valid DOCX zip package with empty body tags",
            expected_status="failed",
            accepted_statuses=["failed"],
            expected_error_code="FILE_EMPTY",
            expected_text="",
            expected_blocks=[],
            provisional_thresholds={"max_cer": 0.0, "min_car": 1.0, "require_exact_structure": True},
        )
    ))

    # 2.11 Corrupted DOCX (Invalid Zip Archive)
    docx_corrupt_bytes = b"PK\x03\x04\x14\x00\x00\x00\x08\x00CorruptedPayloadNotAZipPackage"
    fixtures_with_gt.append((
        BenchmarkFixture(
            fixture_id="BENCH-DOCX-CORRUPT-01",
            filename="BENCH-DOCX-CORRUPT-01.docx",
            format="docx",
            category="edge_cases",
            scenario="Malformed DOCX with corrupted zip archive payload",
            raw_bytes=docx_corrupt_bytes,
        ),
        GroundTruth(
            fixture_id="BENCH-DOCX-CORRUPT-01",
            filename="BENCH-DOCX-CORRUPT-01.docx",
            format="docx",
            category="edge_cases",
            scenario="Malformed DOCX with corrupted zip archive payload",
            expected_status="failed",
            accepted_statuses=["failed"],
            expected_error_code="CORRUPTED_FILE",
            expected_text="",
            expected_blocks=[],
            provisional_thresholds={"max_cer": 0.0, "min_car": 1.0, "require_exact_structure": True},
        )
    ))

    # 2.12 Spoofed Non-Zip File Disguised as DOCX
    docx_spoof_bytes = b"Plain text file contents not a zip container."
    fixtures_with_gt.append((
        BenchmarkFixture(
            fixture_id="BENCH-DOCX-SPOOF-01",
            filename="BENCH-DOCX-SPOOF-01.docx",
            format="docx",
            category="edge_cases",
            scenario="Spoofed document: plain ASCII text named with .docx extension",
            raw_bytes=docx_spoof_bytes,
        ),
        GroundTruth(
            fixture_id="BENCH-DOCX-SPOOF-01",
            filename="BENCH-DOCX-SPOOF-01.docx",
            format="docx",
            category="edge_cases",
            scenario="Spoofed document: plain ASCII text named with .docx extension",
            expected_status="failed",
            accepted_statuses=["failed"],
            expected_error_code="INVALID_SIGNATURE",
            expected_text="",
            expected_blocks=[],
            provisional_thresholds={"max_cer": 0.0, "min_car": 1.0, "require_exact_structure": True},
        )
    ))

    # =========================================================================
    # 3. XLSX FIXTURES (12)
    # =========================================================================

    # 3.1 Single Sheet English Catalog
    wb_en = openpyxl.Workbook()
    ws_en = wb_en.active
    ws_en.title = "Inventory"
    ws_en.append(["SKU", "Item Name", "Price", "Stock"])
    ws_en.append(["SKU-101", "Wireless Mouse", "25.00", "50"])
    ws_en.append(["SKU-102", "Mechanical Keyboard", "85.00", "20"])
    buf_en = io.BytesIO()
    wb_en.save(buf_en)
    xlsx_en_bytes = buf_en.getvalue()
    xlsx_en_headers = ["SKU", "Item Name", "Price", "Stock"]
    xlsx_en_rows = [
        ["SKU-101", "Wireless Mouse", "25.00", "50"],
        ["SKU-102", "Mechanical Keyboard", "85.00", "20"],
    ]
    xlsx_en_text = format_expected_table_text(xlsx_en_headers, xlsx_en_rows, caption="Sheet: Inventory")
    fixtures_with_gt.append((
        BenchmarkFixture(
            fixture_id="BENCH-XLSX-EN-01",
            filename="BENCH-XLSX-EN-01.xlsx",
            format="xlsx",
            category="standard",
            scenario="Single worksheet product catalog in English",
            raw_bytes=xlsx_en_bytes,
        ),
        GroundTruth(
            fixture_id="BENCH-XLSX-EN-01",
            filename="BENCH-XLSX-EN-01.xlsx",
            format="xlsx",
            category="standard",
            scenario="Single worksheet product catalog in English",
            expected_status="success",
            accepted_statuses=["success"],
            expected_text=xlsx_en_text,
            expected_blocks=[
                {
                    "block_type": "table",
                    "sheet_name": "Inventory",
                    "caption": "Sheet: Inventory",
                    "headers": xlsx_en_headers,
                    "rows": xlsx_en_rows,
                    "row_count": 2,
                },
            ],
            expected_metadata={"sheet_names": ["Inventory"], "sheet_count": 1},
            provisional_thresholds={"max_cer": 0.0, "min_car": 1.0, "require_exact_structure": True},
        )
    ))

    # 3.2 Bengali Product Catalog
    wb_bn = openpyxl.Workbook()
    ws_bn = wb_bn.active
    ws_bn.title = "পণ্য_তালিকা"
    ws_bn.append(["আইডি", "পণ্যের নাম", "মূল্য", "স্ট্যাটাস"])
    ws_bn.append(["P-01", "সুতি পাঞ্জাবি", "১২৫০", "ইন স্টক"])
    ws_bn.append(["P-02", "সিল্ক শাড়ি", "৩৫০০", "স্টক শেষ"])
    buf_bn = io.BytesIO()
    wb_bn.save(buf_bn)
    xlsx_bn_bytes = buf_bn.getvalue()
    xlsx_bn_headers = ["আইডি", "পণ্যের নাম", "মূল্য", "স্ট্যাটাস"]
    xlsx_bn_rows = [
        ["P-01", "সুতি পাঞ্জাবি", "১২৫০", "ইন স্টক"],
        ["P-02", "সিল্ক শাড়ি", "৩৫০০", "স্টক শেষ"],
    ]
    xlsx_bn_text = format_expected_table_text(xlsx_bn_headers, xlsx_bn_rows, caption="Sheet: পণ্য_তালিকা")
    fixtures_with_gt.append((
        BenchmarkFixture(
            fixture_id="BENCH-XLSX-BN-01",
            filename="BENCH-XLSX-BN-01.xlsx",
            format="xlsx",
            category="multilingual",
            scenario="Bengali product catalog spreadsheet with Bengali numerals and script",
            raw_bytes=xlsx_bn_bytes,
        ),
        GroundTruth(
            fixture_id="BENCH-XLSX-BN-01",
            filename="BENCH-XLSX-BN-01.xlsx",
            format="xlsx",
            category="multilingual",
            scenario="Bengali product catalog spreadsheet with Bengali numerals and script",
            expected_status="success",
            accepted_statuses=["success"],
            expected_text=xlsx_bn_text,
            expected_blocks=[
                {
                    "block_type": "table",
                    "sheet_name": "পণ্য_তালিকা",
                    "caption": "Sheet: পণ্য_তালিকা",
                    "headers": xlsx_bn_headers,
                    "rows": xlsx_bn_rows,
                    "row_count": 2,
                },
            ],
            expected_metadata={"sheet_names": ["পণ্য_তালিকা"]},
            provisional_thresholds={"max_cer": 0.0, "min_car": 1.0, "require_exact_structure": True},
        )
    ))

    # 3.3 Multi-sheet Workbook
    wb_multi = openpyxl.Workbook()
    ws_m1 = wb_multi.active
    ws_m1.title = "Catalog"
    ws_m1.append(["Code", "Title"])
    ws_m1.append(["C-1", "T-Shirt"])
    ws_m2 = wb_multi.create_sheet(title="Shipping")
    ws_m2.append(["Zone", "Cost"])
    ws_m2.append(["Metro", "60"])
    buf_multi = io.BytesIO()
    wb_multi.save(buf_multi)
    xlsx_multi_bytes = buf_multi.getvalue()
    m1_h, m1_r = ["Code", "Title"], [["C-1", "T-Shirt"]]
    m2_h, m2_r = ["Zone", "Cost"], [["Metro", "60"]]
    xlsx_multi_text = (
        f"{format_expected_table_text(m1_h, m1_r, caption='Sheet: Catalog')}\n\n"
        f"{format_expected_table_text(m2_h, m2_r, caption='Sheet: Shipping')}"
    )
    fixtures_with_gt.append((
        BenchmarkFixture(
            fixture_id="BENCH-XLSX-MULTI-01",
            filename="BENCH-XLSX-MULTI-01.xlsx",
            format="xlsx",
            category="structure",
            scenario="Multi-sheet workbook preserving inter-sheet ordering",
            raw_bytes=xlsx_multi_bytes,
        ),
        GroundTruth(
            fixture_id="BENCH-XLSX-MULTI-01",
            filename="BENCH-XLSX-MULTI-01.xlsx",
            format="xlsx",
            category="structure",
            scenario="Multi-sheet workbook preserving inter-sheet ordering",
            expected_status="success",
            accepted_statuses=["success"],
            expected_text=xlsx_multi_text,
            expected_blocks=[
                {"block_type": "table", "sheet_name": "Catalog", "headers": m1_h, "rows": m1_r, "row_count": 1},
                {"block_type": "table", "sheet_name": "Shipping", "headers": m2_h, "rows": m2_r, "row_count": 1},
            ],
            expected_metadata={"sheet_names": ["Catalog", "Shipping"], "sheet_count": 2},
            provisional_thresholds={"max_cer": 0.0, "min_car": 1.0, "require_exact_structure": True},
        )
    ))

    # 3.4 Leading Zeros Preservation
    wb_zero = openpyxl.Workbook()
    ws_zero = wb_zero.active
    ws_zero.title = "Customers"
    ws_zero.append(["Customer", "Phone", "PostalCode"])
    ws_zero.append(["Customer A", "01712345678", "0800"])
    ws_zero.append(["Customer B", "01898765432", "0120"])
    buf_zero = io.BytesIO()
    wb_zero.save(buf_zero)
    xlsx_zero_bytes = buf_zero.getvalue()
    z_h, z_r = ["Customer", "Phone", "PostalCode"], [
        ["Customer A", "01712345678", "0800"],
        ["Customer B", "01898765432", "0120"],
    ]
    xlsx_zero_text = format_expected_table_text(z_h, z_r, caption="Sheet: Customers")
    fixtures_with_gt.append((
        BenchmarkFixture(
            fixture_id="BENCH-XLSX-ZERO-01",
            filename="BENCH-XLSX-ZERO-01.xlsx",
            format="xlsx",
            category="edge_cases",
            scenario="Preservation of leading zeros in string phone and postal codes",
            raw_bytes=xlsx_zero_bytes,
        ),
        GroundTruth(
            fixture_id="BENCH-XLSX-ZERO-01",
            filename="BENCH-XLSX-ZERO-01.xlsx",
            format="xlsx",
            category="edge_cases",
            scenario="Preservation of leading zeros in string phone and postal codes",
            expected_status="success",
            accepted_statuses=["success"],
            expected_text=xlsx_zero_text,
            expected_blocks=[
                {"block_type": "table", "sheet_name": "Customers", "headers": z_h, "rows": z_r, "row_count": 2},
            ],
            provisional_thresholds={"max_cer": 0.0, "min_car": 1.0, "require_exact_structure": True},
        )
    ))

    # 3.5 Sheet with Blank / Empty Intermediate Cells
    wb_bc = openpyxl.Workbook()
    ws_bc = wb_bc.active
    ws_bc.title = "SparseData"
    ws_bc.append(["ColA", "ColB", "ColC"])
    ws_bc.append(["ValA1", None, "ValC1"])
    ws_bc.append([None, "ValB2", None])
    buf_bc = io.BytesIO()
    wb_bc.save(buf_bc)
    xlsx_bc_bytes = buf_bc.getvalue()
    bc_h = ["ColA", "ColB", "ColC"]
    bc_r = [
        ["ValA1", "", "ValC1"],
        ["", "ValB2", ""],
    ]
    xlsx_bc_text = format_expected_table_text(bc_h, bc_r, caption="Sheet: SparseData")
    fixtures_with_gt.append((
        BenchmarkFixture(
            fixture_id="BENCH-XLSX-BLANKCELLS-01",
            filename="BENCH-XLSX-BLANKCELLS-01.xlsx",
            format="xlsx",
            category="structure",
            scenario="Worksheet containing interspersed empty/blank cells within rows",
            raw_bytes=xlsx_bc_bytes,
        ),
        GroundTruth(
            fixture_id="BENCH-XLSX-BLANKCELLS-01",
            filename="BENCH-XLSX-BLANKCELLS-01.xlsx",
            format="xlsx",
            category="structure",
            scenario="Worksheet containing interspersed empty/blank cells within rows",
            expected_status="success",
            accepted_statuses=["success"],
            expected_text=xlsx_bc_text,
            expected_blocks=[
                {"block_type": "table", "sheet_name": "SparseData", "headers": bc_h, "rows": bc_r, "row_count": 2},
            ],
            provisional_thresholds={"max_cer": 0.0, "min_car": 1.0, "require_exact_structure": True},
        )
    ))

    # 3.6 Multi-sheet with One Blank Sheet
    wb_bsh = openpyxl.Workbook()
    ws_b1 = wb_bsh.active
    ws_b1.title = "ActiveData"
    ws_b1.append(["Key", "Val"])
    ws_b1.append(["K1", "V1"])
    ws_b2 = wb_bsh.create_sheet(title="BlankSheet")
    buf_bsh = io.BytesIO()
    wb_bsh.save(buf_bsh)
    xlsx_bsh_bytes = buf_bsh.getvalue()
    bsh_h, bsh_r = ["Key", "Val"], [["K1", "V1"]]
    xlsx_bsh_text = format_expected_table_text(bsh_h, bsh_r, caption="Sheet: ActiveData")
    fixtures_with_gt.append((
        BenchmarkFixture(
            fixture_id="BENCH-XLSX-BLANKSH-01",
            filename="BENCH-XLSX-BLANKSH-01.xlsx",
            format="xlsx",
            category="edge_cases",
            scenario="Workbook containing one populated sheet and one empty sheet",
            raw_bytes=xlsx_bsh_bytes,
        ),
        GroundTruth(
            fixture_id="BENCH-XLSX-BLANKSH-01",
            filename="BENCH-XLSX-BLANKSH-01.xlsx",
            format="xlsx",
            category="edge_cases",
            scenario="Workbook containing one populated sheet and one empty sheet",
            expected_status="success_with_warnings",
            accepted_statuses=["success_with_warnings"],
            expected_warnings=["empty and contained no data"],
            expected_text=xlsx_bsh_text,
            expected_blocks=[
                {"block_type": "table", "sheet_name": "ActiveData", "headers": bsh_h, "rows": bsh_r, "row_count": 1},
            ],
            expected_metadata={"sheet_names": ["ActiveData", "BlankSheet"], "sheet_count": 2},
            provisional_thresholds={"max_cer": 0.0, "min_car": 1.0, "require_exact_structure": True},
        )
    ))

    # 3.7 Hidden Worksheet
    wb_hid = openpyxl.Workbook()
    ws_h1 = wb_hid.active
    ws_h1.title = "PublicNotes"
    ws_h1.append(["Topic", "Status"])
    ws_h1.append(["Launch", "Ready"])
    ws_h2 = wb_hid.create_sheet(title="Internal_Costs")
    ws_h2.sheet_state = "hidden"
    ws_h2.append(["Component", "Budget"])
    ws_h2.append(["Hosting", "500"])
    buf_hid = io.BytesIO()
    wb_hid.save(buf_hid)
    xlsx_hid_bytes = buf_hid.getvalue()
    h1_h, h1_r = ["Topic", "Status"], [["Launch", "Ready"]]
    h2_h, h2_r = ["Component", "Budget"], [["Hosting", "500"]]
    xlsx_hid_text = (
        f"{format_expected_table_text(h1_h, h1_r, caption='Sheet: PublicNotes')}\n\n"
        f"{format_expected_table_text(h2_h, h2_r, caption='Sheet: Internal_Costs')}"
    )
    fixtures_with_gt.append((
        BenchmarkFixture(
            fixture_id="BENCH-XLSX-HIDDEN-01",
            filename="BENCH-XLSX-HIDDEN-01.xlsx",
            format="xlsx",
            category="edge_cases",
            scenario="Workbook containing a hidden worksheet",
            raw_bytes=xlsx_hid_bytes,
        ),
        GroundTruth(
            fixture_id="BENCH-XLSX-HIDDEN-01",
            filename="BENCH-XLSX-HIDDEN-01.xlsx",
            format="xlsx",
            category="edge_cases",
            scenario="Workbook containing a hidden worksheet",
            expected_status="success_with_warnings",
            accepted_statuses=["success_with_warnings"],
            expected_warnings=["is hidden in workbook"],
            expected_text=xlsx_hid_text,
            expected_blocks=[
                {"block_type": "table", "sheet_name": "PublicNotes", "headers": h1_h, "rows": h1_r, "row_count": 1},
                {"block_type": "table", "sheet_name": "Internal_Costs", "headers": h2_h, "rows": h2_r, "row_count": 1},
            ],
            expected_metadata={"hidden_sheets": ["Internal_Costs"]},
            provisional_thresholds={"max_cer": 0.0, "min_car": 1.0, "require_exact_structure": True},
        )
    ))

    # 3.8 Formula Error (#VALUE!)
    wb_err = openpyxl.Workbook()
    ws_err = wb_err.active
    ws_err.title = "Financials"
    ws_err.append(["Metric", "Calculation"])
    ws_err.append(["Net Margin", "#VALUE!"])
    buf_err = io.BytesIO()
    wb_err.save(buf_err)
    xlsx_err_bytes = buf_err.getvalue()
    err_h, err_r = ["Metric", "Calculation"], [["Net Margin", "#VALUE!"]]
    xlsx_err_text = format_expected_table_text(err_h, err_r, caption="Sheet: Financials")
    fixtures_with_gt.append((
        BenchmarkFixture(
            fixture_id="BENCH-XLSX-FORMULA-01",
            filename="BENCH-XLSX-FORMULA-01.xlsx",
            format="xlsx",
            category="edge_cases",
            scenario="Worksheet containing uncalculated formula error tokens",
            raw_bytes=xlsx_err_bytes,
        ),
        GroundTruth(
            fixture_id="BENCH-XLSX-FORMULA-01",
            filename="BENCH-XLSX-FORMULA-01.xlsx",
            format="xlsx",
            category="edge_cases",
            scenario="Worksheet containing uncalculated formula error tokens",
            expected_status="needs_review",
            accepted_statuses=["needs_review"],
            expected_warnings=["uncalculated formulas or Excel error values"],
            expected_text=xlsx_err_text,
            expected_blocks=[
                {"block_type": "table", "sheet_name": "Financials", "headers": err_h, "rows": err_r, "row_count": 1},
            ],
            expected_metadata={"has_formula_errors": True},
            provisional_thresholds={"max_cer": 0.0, "min_car": 1.0, "require_exact_structure": True},
        )
    ))

    # 3.9 Uncached Formula Cell (openpyxl data_only mode limitations)
    wb_unc = openpyxl.Workbook()
    ws_unc = wb_unc.active
    ws_unc.title = "UncachedFormulas"
    ws_unc.append(["Item", "FormulaVal"])
    ws_unc['A2'] = "Total"
    ws_unc['B2'] = "=SUM(1, 2)"  # Without saved cached <v>, openpyxl reads None
    buf_unc = io.BytesIO()
    wb_unc.save(buf_unc)
    xlsx_unc_bytes = buf_unc.getvalue()
    unc_h = ["Item", "FormulaVal"]
    unc_r = [["Total", ""]]  # None formatted as empty string
    xlsx_unc_text = format_expected_table_text(unc_h, unc_r, caption="Sheet: UncachedFormulas")
    fixtures_with_gt.append((
        BenchmarkFixture(
            fixture_id="BENCH-XLSX-UNCACHED-01",
            filename="BENCH-XLSX-UNCACHED-01.xlsx",
            format="xlsx",
            category="edge_cases",
            scenario="Uncalculated Excel formula without pre-cached evaluated value in file",
            raw_bytes=xlsx_unc_bytes,
        ),
        GroundTruth(
            fixture_id="BENCH-XLSX-UNCACHED-01",
            filename="BENCH-XLSX-UNCACHED-01.xlsx",
            format="xlsx",
            category="edge_cases",
            scenario="Uncalculated Excel formula without pre-cached evaluated value in file",
            expected_status="success",
            accepted_statuses=["success"],
            expected_text=xlsx_unc_text,
            expected_blocks=[
                {"block_type": "table", "sheet_name": "UncachedFormulas", "headers": unc_h, "rows": unc_r, "row_count": 1},
            ],
            known_unsupported_content="openpyxl read-only data-only mode does not execute formulas; uncached formulas yield empty cell",
            provisional_thresholds={"max_cer": 0.0, "min_car": 1.0, "require_exact_structure": True},
        )
    ))

    # 3.10 Completely Empty XLSX
    wb_emp = openpyxl.Workbook()
    ws_emp = wb_emp.active
    ws_emp.title = "EmptySheet"
    buf_emp = io.BytesIO()
    wb_emp.save(buf_emp)
    xlsx_emp_bytes = buf_emp.getvalue()
    fixtures_with_gt.append((
        BenchmarkFixture(
            fixture_id="BENCH-XLSX-EMPTY-01",
            filename="BENCH-XLSX-EMPTY-01.xlsx",
            format="xlsx",
            category="edge_cases",
            scenario="XLSX workbook where all sheets contain zero cells",
            raw_bytes=xlsx_emp_bytes,
        ),
        GroundTruth(
            fixture_id="BENCH-XLSX-EMPTY-01",
            filename="BENCH-XLSX-EMPTY-01.xlsx",
            format="xlsx",
            category="edge_cases",
            scenario="XLSX workbook where all sheets contain zero cells",
            expected_status="failed",
            accepted_statuses=["failed"],
            expected_error_code="FILE_EMPTY",
            expected_text="",
            expected_blocks=[],
            provisional_thresholds={"max_cer": 0.0, "min_car": 1.0, "require_exact_structure": True},
        )
    ))

    # 3.11 Malformed XLSX Non-Zip Binary
    xlsx_corrupt_bytes = b"CorruptedXLSXNotValidZipStructure"
    fixtures_with_gt.append((
        BenchmarkFixture(
            fixture_id="BENCH-XLSX-CORRUPT-01",
            filename="BENCH-XLSX-CORRUPT-01.xlsx",
            format="xlsx",
            category="edge_cases",
            scenario="Malformed XLSX with non-zip binary content",
            raw_bytes=xlsx_corrupt_bytes,
        ),
        GroundTruth(
            fixture_id="BENCH-XLSX-CORRUPT-01",
            filename="BENCH-XLSX-CORRUPT-01.xlsx",
            format="xlsx",
            category="edge_cases",
            scenario="Malformed XLSX with non-zip binary content",
            expected_status="failed",
            accepted_statuses=["failed"],
            expected_error_code="INVALID_SIGNATURE",
            expected_text="",
            expected_blocks=[],
            provisional_thresholds={"max_cer": 0.0, "min_car": 1.0, "require_exact_structure": True},
        )
    ))

    # 3.12 Valid Zip Missing xl/workbook.xml
    buf_no_wb = io.BytesIO()
    with zipfile.ZipFile(buf_no_wb, "w") as z:
        z.writestr("dummy.txt", "not an excel workbook")
    xlsx_no_wb_bytes = buf_no_wb.getvalue()
    fixtures_with_gt.append((
        BenchmarkFixture(
            fixture_id="BENCH-XLSX-CORRUPTZIP-01",
            filename="BENCH-XLSX-CORRUPTZIP-01.xlsx",
            format="xlsx",
            category="edge_cases",
            scenario="Zip archive missing required xl/workbook.xml structure",
            raw_bytes=xlsx_no_wb_bytes,
        ),
        GroundTruth(
            fixture_id="BENCH-XLSX-CORRUPTZIP-01",
            filename="BENCH-XLSX-CORRUPTZIP-01.xlsx",
            format="xlsx",
            category="edge_cases",
            scenario="Zip archive missing required xl/workbook.xml structure",
            expected_status="failed",
            accepted_statuses=["failed"],
            expected_error_code="INVALID_SIGNATURE",
            expected_text="",
            expected_blocks=[],
            provisional_thresholds={"max_cer": 0.0, "min_car": 1.0, "require_exact_structure": True},
        )
    ))

    # =========================================================================
    # 4. CSV FIXTURES (12)
    # =========================================================================

    # 4.1 Comma-delimited English
    csv_comma_text = "SKU,Product,Price,Quantity\nA101,Desk Lamp,15.99,10\nB202,Office Chair,89.50,4"
    c_h = ["SKU", "Product", "Price", "Quantity"]
    c_r = [
        ["A101", "Desk Lamp", "15.99", "10"],
        ["B202", "Office Chair", "89.50", "4"],
    ]
    csv_comma_expected = format_expected_table_text(c_h, c_r, caption="BENCH-CSV-COMMA-01.csv")
    fixtures_with_gt.append((
        BenchmarkFixture(
            fixture_id="BENCH-CSV-COMMA-01",
            filename="BENCH-CSV-COMMA-01.csv",
            format="csv",
            category="standard",
            scenario="Standard comma-delimited English CSV",
            raw_bytes=csv_comma_text.encode("utf-8"),
        ),
        GroundTruth(
            fixture_id="BENCH-CSV-COMMA-01",
            filename="BENCH-CSV-COMMA-01.csv",
            format="csv",
            category="standard",
            scenario="Standard comma-delimited English CSV",
            expected_status="success",
            accepted_statuses=["success"],
            expected_text=csv_comma_expected,
            expected_blocks=[
                {"block_type": "table", "headers": c_h, "rows": c_r, "row_count": 2},
            ],
            expected_metadata={"delimiter": ","},
            provisional_thresholds={"max_cer": 0.0, "min_car": 1.0, "require_exact_structure": True},
        )
    ))

    # 4.2 Semicolon-delimited European CSV
    csv_semi_text = "SKU;Product;Price;Quantity\nC303;Espresso Mug;8.00;25\nD404;Coffee Beans;12.50;50"
    s_h = ["SKU", "Product", "Price", "Quantity"]
    s_r = [
        ["C303", "Espresso Mug", "8.00", "25"],
        ["D404", "Coffee Beans", "12.50", "50"],
    ]
    csv_semi_expected = format_expected_table_text(s_h, s_r, caption="BENCH-CSV-SEMI-01.csv")
    fixtures_with_gt.append((
        BenchmarkFixture(
            fixture_id="BENCH-CSV-SEMI-01",
            filename="BENCH-CSV-SEMI-01.csv",
            format="csv",
            category="delimiters",
            scenario="European semicolon-delimited CSV",
            raw_bytes=csv_semi_text.encode("utf-8"),
        ),
        GroundTruth(
            fixture_id="BENCH-CSV-SEMI-01",
            filename="BENCH-CSV-SEMI-01.csv",
            format="csv",
            category="delimiters",
            scenario="European semicolon-delimited CSV",
            expected_status="success",
            accepted_statuses=["success"],
            expected_text=csv_semi_expected,
            expected_blocks=[
                {"block_type": "table", "headers": s_h, "rows": s_r, "row_count": 2},
            ],
            expected_metadata={"delimiter": ";"},
            provisional_thresholds={"max_cer": 0.0, "min_car": 1.0, "require_exact_structure": True},
        )
    ))

    # 4.3 Tab-delimited TSV
    csv_tab_text = "Item_Code\tItem_Name\tLocation\tUnits\nT-01\tLaptop Stand\tWarehouse-A\t15\nT-02\tUSB Cable\tWarehouse-B\t100"
    t_h = ["Item_Code", "Item_Name", "Location", "Units"]
    t_r = [
        ["T-01", "Laptop Stand", "Warehouse-A", "15"],
        ["T-02", "USB Cable", "Warehouse-B", "100"],
    ]
    csv_tab_expected = format_expected_table_text(t_h, t_r, caption="BENCH-CSV-TAB-01.csv")
    fixtures_with_gt.append((
        BenchmarkFixture(
            fixture_id="BENCH-CSV-TAB-01",
            filename="BENCH-CSV-TAB-01.csv",
            format="csv",
            category="delimiters",
            scenario="Tab-delimited TSV tabular dataset",
            raw_bytes=csv_tab_text.encode("utf-8"),
        ),
        GroundTruth(
            fixture_id="BENCH-CSV-TAB-01",
            filename="BENCH-CSV-TAB-01.csv",
            format="csv",
            category="delimiters",
            scenario="Tab-delimited TSV tabular dataset",
            expected_status="success",
            accepted_statuses=["success"],
            expected_text=csv_tab_expected,
            expected_blocks=[
                {"block_type": "table", "headers": t_h, "rows": t_r, "row_count": 2},
            ],
            expected_metadata={"delimiter": "\t"},
            provisional_thresholds={"max_cer": 0.0, "min_car": 1.0, "require_exact_structure": True},
        )
    ))

    # 4.4 Pipe-delimited CSV
    csv_pipe_text = "Service|Tier|Monthly_Fee|SLA_Hours\nCloud Backup|Standard|29.99|24\nCloud Backup|Enterprise|149.99|4"
    p_h = ["Service", "Tier", "Monthly_Fee", "SLA_Hours"]
    p_r = [
        ["Cloud Backup", "Standard", "29.99", "24"],
        ["Cloud Backup", "Enterprise", "149.99", "4"],
    ]
    csv_pipe_expected = format_expected_table_text(p_h, p_r, caption="BENCH-CSV-PIPE-01.csv")
    fixtures_with_gt.append((
        BenchmarkFixture(
            fixture_id="BENCH-CSV-PIPE-01",
            filename="BENCH-CSV-PIPE-01.csv",
            format="csv",
            category="delimiters",
            scenario="Pipe-delimited enterprise log or inventory file",
            raw_bytes=csv_pipe_text.encode("utf-8"),
        ),
        GroundTruth(
            fixture_id="BENCH-CSV-PIPE-01",
            filename="BENCH-CSV-PIPE-01.csv",
            format="csv",
            category="delimiters",
            scenario="Pipe-delimited enterprise log or inventory file",
            expected_status="success",
            accepted_statuses=["success"],
            expected_text=csv_pipe_expected,
            expected_blocks=[
                {"block_type": "table", "headers": p_h, "rows": p_r, "row_count": 2},
            ],
            expected_metadata={"delimiter": "|"},
            provisional_thresholds={"max_cer": 0.0, "min_car": 1.0, "require_exact_structure": True},
        )
    ))

    # 4.5 Complex Quoting with Internal Commas and Embedded Newlines
    q_buf = io.StringIO()
    writer = csv.writer(q_buf)
    writer.writerow(["ID", "Title", "Description", "Price"])
    writer.writerow(["101", "Gaming Chair", "Ergonomic, High-Back, Reclining", "180"])
    writer.writerow(["102", "Standing Desk", "Adjustable height\nSolid bamboo top", "350"])
    csv_quoted_str = q_buf.getvalue()

    q_h = ["ID", "Title", "Description", "Price"]
    q_r = [
        ["101", "Gaming Chair", "Ergonomic, High-Back, Reclining", "180"],
        ["102", "Standing Desk", "Adjustable height\nSolid bamboo top", "350"],
    ]
    csv_quoted_expected = format_expected_table_text(q_h, q_r, caption="BENCH-CSV-QUOTED-01.csv")
    fixtures_with_gt.append((
        BenchmarkFixture(
            fixture_id="BENCH-CSV-QUOTED-01",
            filename="BENCH-CSV-QUOTED-01.csv",
            format="csv",
            category="quoting",
            scenario="Quoted CSV with internal commas and multiline cell content",
            raw_bytes=csv_quoted_str.encode("utf-8"),
        ),
        GroundTruth(
            fixture_id="BENCH-CSV-QUOTED-01",
            filename="BENCH-CSV-QUOTED-01.csv",
            format="csv",
            category="quoting",
            scenario="Quoted CSV with internal commas and multiline cell content",
            expected_status="success",
            accepted_statuses=["success"],
            expected_text=csv_quoted_expected,
            expected_blocks=[
                {"block_type": "table", "headers": q_h, "rows": q_r, "row_count": 2},
            ],
            provisional_thresholds={"max_cer": 0.0, "min_car": 1.0, "require_exact_structure": True},
        )
    ))

    # 4.6 Escaped Quotes inside Quoted Fields
    esc_buf = io.StringIO()
    esc_writer = csv.writer(esc_buf)
    esc_writer.writerow(["Item", "Notes"])
    esc_writer.writerow(["Monitor", '27" 4K "Ultra" Display'])
    esc_writer.writerow(["Keypad", 'Custom "Mechanical" Switches'])
    csv_esc_str = esc_buf.getvalue()
    esc_h = ["Item", "Notes"]
    esc_r = [
        ["Monitor", '27" 4K "Ultra" Display'],
        ["Keypad", 'Custom "Mechanical" Switches'],
    ]
    csv_esc_expected = format_expected_table_text(esc_h, esc_r, caption="BENCH-CSV-ESCAPED-01.csv")
    fixtures_with_gt.append((
        BenchmarkFixture(
            fixture_id="BENCH-CSV-ESCAPED-01",
            filename="BENCH-CSV-ESCAPED-01.csv",
            format="csv",
            category="quoting",
            scenario="CSV with escaped double quotes inside quoted fields",
            raw_bytes=csv_esc_str.encode("utf-8"),
        ),
        GroundTruth(
            fixture_id="BENCH-CSV-ESCAPED-01",
            filename="BENCH-CSV-ESCAPED-01.csv",
            format="csv",
            category="quoting",
            scenario="CSV with escaped double quotes inside quoted fields",
            expected_status="success",
            accepted_statuses=["success"],
            expected_text=csv_esc_expected,
            expected_blocks=[
                {"block_type": "table", "headers": esc_h, "rows": esc_r, "row_count": 2},
            ],
            provisional_thresholds={"max_cer": 0.0, "min_car": 1.0, "require_exact_structure": True},
        )
    ))

    # 4.7 Bengali CSV with UTF-8 BOM
    csv_bn_text = "পণ্যের আইডি,পণ্যের নাম,মূল্য,স্ট্যাটাস\nBN-01,পাঞ্জাবি,১২০০,উপলব্ধ\nBN-02,পায়জামা,৪৫০,উপলব্ধ"
    csv_bn_bytes = b"\xef\xbb\xbf" + csv_bn_text.encode("utf-8")
    bn_h = ["পণ্যের আইডি", "পণ্যের নাম", "মূল্য", "স্ট্যাটাস"]
    bn_r = [
        ["BN-01", "পাঞ্জাবি", "১২০০", "উপলব্ধ"],
        ["BN-02", "পায়জামা", "৪৫০", "উপলব্ধ"],
    ]
    csv_bn_expected = format_expected_table_text(bn_h, bn_r, caption="BENCH-CSV-BN-01.csv")
    fixtures_with_gt.append((
        BenchmarkFixture(
            fixture_id="BENCH-CSV-BN-01",
            filename="BENCH-CSV-BN-01.csv",
            format="csv",
            category="multilingual",
            scenario="Bengali CSV encoded in UTF-8 with Byte Order Mark",
            raw_bytes=csv_bn_bytes,
        ),
        GroundTruth(
            fixture_id="BENCH-CSV-BN-01",
            filename="BENCH-CSV-BN-01.csv",
            format="csv",
            category="multilingual",
            scenario="Bengali CSV encoded in UTF-8 with Byte Order Mark",
            expected_status="success",
            accepted_statuses=["success"],
            expected_text=csv_bn_expected,
            expected_blocks=[
                {"block_type": "table", "headers": bn_h, "rows": bn_r, "row_count": 2},
            ],
            expected_metadata={"encoding": "utf-8-sig", "has_bom": True},
            provisional_thresholds={"max_cer": 0.0, "min_car": 1.0, "require_exact_structure": True},
        )
    ))

    # 4.8 Headerless Numeric CSV
    csv_nohead_text = "101,45.50,1\n102,99.00,2\n103,15.25,3"
    nh_h = ["column_1", "column_2", "column_3"]
    nh_r = [
        ["101", "45.50", "1"],
        ["102", "99.00", "2"],
        ["103", "15.25", "3"],
    ]
    csv_nohead_expected = format_expected_table_text(nh_h, nh_r, caption="BENCH-CSV-NOHEAD-01.csv")
    fixtures_with_gt.append((
        BenchmarkFixture(
            fixture_id="BENCH-CSV-NOHEAD-01",
            filename="BENCH-CSV-NOHEAD-01.csv",
            format="csv",
            category="structure",
            scenario="Headerless numeric CSV requiring synthetic header generation",
            raw_bytes=csv_nohead_text.encode("utf-8"),
        ),
        GroundTruth(
            fixture_id="BENCH-CSV-NOHEAD-01",
            filename="BENCH-CSV-NOHEAD-01.csv",
            format="csv",
            category="structure",
            scenario="Headerless numeric CSV requiring synthetic header generation",
            expected_status="success_with_warnings",
            accepted_statuses=["success_with_warnings"],
            expected_warnings=["generated synthetic column names"],
            expected_text=csv_nohead_expected,
            expected_blocks=[
                {"block_type": "table", "headers": nh_h, "rows": nh_r, "row_count": 3},
            ],
            provisional_thresholds={"max_cer": 0.0, "min_car": 1.0, "require_exact_structure": True},
        )
    ))

    # 4.9 Jagged / Ragged Rows CSV
    csv_jagged_text = "H1,H2,H3,H4\nA,B,C,D\nE,F\nG,H,I\nJ,K,L,M"
    jg_h = ["H1", "H2", "H3", "H4"]
    jg_r = [
        ["A", "B", "C", "D"],
        ["E", "F", "", ""],
        ["G", "H", "I", ""],
        ["J", "K", "L", "M"],
    ]
    csv_jagged_expected = format_expected_table_text(jg_h, jg_r, caption="BENCH-CSV-JAGGED-01.csv")
    fixtures_with_gt.append((
        BenchmarkFixture(
            fixture_id="BENCH-CSV-JAGGED-01",
            filename="BENCH-CSV-JAGGED-01.csv",
            format="csv",
            category="edge_cases",
            scenario="Jagged CSV with inconsistent column counts per row",
            raw_bytes=csv_jagged_text.encode("utf-8"),
        ),
        GroundTruth(
            fixture_id="BENCH-CSV-JAGGED-01",
            filename="BENCH-CSV-JAGGED-01.csv",
            format="csv",
            category="edge_cases",
            scenario="Jagged CSV with inconsistent column counts per row",
            expected_status="needs_review",
            accepted_statuses=["needs_review"],
            expected_warnings=["Inconsistent column counts"],
            expected_text=csv_jagged_expected,
            expected_blocks=[
                {"block_type": "table", "headers": jg_h, "rows": jg_r, "row_count": 4},
            ],
            provisional_thresholds={"max_cer": 0.0, "min_car": 1.0, "require_exact_structure": True},
        )
    ))

    # 4.10 Ambiguous Multiline Conflicting Delimiter CSV
    amb_text = "A,B,C\nD;E;F\nG;H;I"
    amb_h = ["column_1", "column_2", "column_3"]
    amb_r = [
        ["A,B,C", "", ""],
        ["D", "E", "F"],
        ["G", "H", "I"],
    ]
    amb_expected = format_expected_table_text(amb_h, amb_r, caption="BENCH-CSV-AMBIGUOUS-01.csv")
    fixtures_with_gt.append((
        BenchmarkFixture(
            fixture_id="BENCH-CSV-AMBIGUOUS-01",
            filename="BENCH-CSV-AMBIGUOUS-01.csv",
            format="csv",
            category="delimiters",
            scenario="Ambiguous CSV containing conflicting delimiters causing sniffer uncertainty",
            raw_bytes=amb_text.encode("utf-8"),
        ),
        GroundTruth(
            fixture_id="BENCH-CSV-AMBIGUOUS-01",
            filename="BENCH-CSV-AMBIGUOUS-01.csv",
            format="csv",
            category="delimiters",
            scenario="Ambiguous CSV containing conflicting delimiters causing sniffer uncertainty",
            expected_status="needs_review",
            accepted_statuses=["needs_review"],
            expected_warnings=["Dialect sniffer uncertain"],
            expected_text=amb_expected,
            expected_blocks=[
                {"block_type": "table", "headers": amb_h, "rows": amb_r, "row_count": 3},
            ],
            provisional_thresholds={"max_cer": 0.0, "min_car": 1.0, "require_exact_structure": True},
        )
    ))

    # 4.11 0-byte Empty CSV
    fixtures_with_gt.append((
        BenchmarkFixture(
            fixture_id="BENCH-CSV-EMPTY-01",
            filename="BENCH-CSV-EMPTY-01.csv",
            format="csv",
            category="edge_cases",
            scenario="Zero-byte empty CSV file",
            raw_bytes=b"",
        ),
        GroundTruth(
            fixture_id="BENCH-CSV-EMPTY-01",
            filename="BENCH-CSV-EMPTY-01.csv",
            format="csv",
            category="edge_cases",
            scenario="Zero-byte empty CSV file",
            expected_status="failed",
            accepted_statuses=["failed"],
            expected_error_code="FILE_EMPTY",
            expected_text="",
            expected_blocks=[],
            provisional_thresholds={"max_cer": 0.0, "min_car": 1.0, "require_exact_structure": True},
        )
    ))

    # 4.12 Disguised Binary File as CSV
    fixtures_with_gt.append((
        BenchmarkFixture(
            fixture_id="BENCH-CSV-BINARY-01",
            filename="BENCH-CSV-BINARY-01.csv",
            format="csv",
            category="edge_cases",
            scenario="Disguised binary ELF file with .csv extension",
            raw_bytes=binary_payload,
        ),
        GroundTruth(
            fixture_id="BENCH-CSV-BINARY-01",
            filename="BENCH-CSV-BINARY-01.csv",
            format="csv",
            category="edge_cases",
            scenario="Disguised binary ELF file with .csv extension",
            expected_status="failed",
            accepted_statuses=["failed"],
            expected_error_code="INVALID_SIGNATURE",
            expected_text="",
            expected_blocks=[],
            provisional_thresholds={"max_cer": 0.0, "min_car": 1.0, "require_exact_structure": True},
        )
    ))

    return fixtures_with_gt


def save_fixtures_to_disk(
    output_dir: str = "benchmark",
) -> List[Tuple[BenchmarkFixture, GroundTruth]]:
    """Generates and writes all fixtures and ground truth JSON files to disk."""
    fixtures_dir = os.path.join(output_dir, "fixtures")
    gt_dir = os.path.join(output_dir, "ground_truth")
    os.makedirs(fixtures_dir, exist_ok=True)
    os.makedirs(gt_dir, exist_ok=True)

    items = generate_all_fixtures()
    import json

    saved_items: List[Tuple[BenchmarkFixture, GroundTruth]] = []
    for fix, gt in items:
        file_path = os.path.join(fixtures_dir, fix.filename)
        with open(file_path, "wb") as f:
            f.write(fix.raw_bytes)
        fix.file_path = file_path

        gt_path = os.path.join(gt_dir, f"{fix.fixture_id}.json")
        with open(gt_path, "w", encoding="utf-8") as f:
            json.dump(gt.to_dict(), f, indent=2, ensure_ascii=False)

        saved_items.append((fix, gt))

    return saved_items


if __name__ == "__main__":
    items = save_fixtures_to_disk()
    print(f"Successfully generated and wrote {len(items)} fixtures to benchmark/fixtures and benchmark/ground_truth.")
