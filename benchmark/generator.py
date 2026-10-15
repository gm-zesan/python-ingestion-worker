"""
Deterministic fixture generator for the Document Extraction Benchmark Suite.
Generates 32 real file fixtures across TXT, DOCX, XLSX, and CSV with matching GroundTruth.
"""

import os
import io
import csv
import zipfile
from typing import Dict, Tuple, List
import openpyxl

from .models import BenchmarkFixture, GroundTruth


def _create_docx_bytes(
    paragraphs: List[Tuple[str, str]] = None,
    tables: List[List[List[str]]] = None,
    include_image: bool = False,
    empty_body: bool = False,
) -> bytes:
    """Helper to build a valid OpenXML DOCX package in memory."""
    paragraphs = paragraphs or []
    tables = tables or []

    doc_xml_parts = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">',
        '<w:body>',
    ]

    if not empty_body:
        # Add paragraphs / headings
        for style, text in paragraphs:
            p_style = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
            doc_xml_parts.append(f'<w:p>{p_style}<w:r><w:t>{text}</w:t></w:r></w:p>')

        # Add tables
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
            # Add a dummy PNG image payload into word/media/
            zf.writestr("word/media/image1.png", b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" + b"\x00" * 30)

    return buf.getvalue()


def generate_all_fixtures() -> List[Tuple[BenchmarkFixture, GroundTruth]]:
    """Generates all 32 fixtures and their corresponding ground truth expectations."""
    fixtures_with_gt: List[Tuple[BenchmarkFixture, GroundTruth]] = []

    # ==========================================
    # 1. TXT FIXTURES (7)
    # ==========================================

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
                {"block_type": "paragraph"},
                {"block_type": "paragraph"},
                {"block_type": "paragraph"},
            ],
            expected_metadata={"encoding": "utf-8", "line_count": 5},
            provisional_thresholds={"max_cer": 0.0, "min_car": 1.0, "require_exact_structure": True},
        )
    ))

    # 1.2 Bengali Unicode with Ligatures & Currency
    bn_txt = (
        "ডেলিভারি পলিসি ও শর্তাবলী\n\n"
        "ঢাকা সিটির ভিতরে ডেলিভারি চার্জ ৬০৳ এবং ২ কার্যদিবসের মধ্যে ডেলিভারি সম্পন্ন হবে।\n\n"
        "অগ্রিম পেমেন্ট বিকাশ বা নগদ এর মাধ্যমে পরিশোধ করা যাবে।"
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
                {"block_type": "paragraph"},
                {"block_type": "paragraph"},
                {"block_type": "paragraph"},
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
                {"block_type": "paragraph"},
                {"block_type": "paragraph"},
                {"block_type": "paragraph"},
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
                {"block_type": "paragraph"},
                {"block_type": "paragraph"},
                {"block_type": "paragraph"},
            ],
            expected_metadata={"encoding": "utf-8-sig"},
            provisional_thresholds={"max_cer": 0.0, "min_car": 1.0, "require_exact_structure": True},
        )
    ))

    # 1.5 Windows-1252 (CP1252)
    cp_text = "Copyright (c) 2026 Entrepreneurs Automation.\n\nAll prices in EUR (100 €) including standard VAT."
    cp_bytes = cp_text.encode("cp1252")
    fixtures_with_gt.append((
        BenchmarkFixture(
            fixture_id="BENCH-TXT-CP1252-01",
            filename="BENCH-TXT-CP1252-01.txt",
            format="txt",
            category="encoding",
            scenario="Windows-1252 (CP1252) legacy encoding with euro currency symbol",
            raw_bytes=cp_bytes,
        ),
        GroundTruth(
            fixture_id="BENCH-TXT-CP1252-01",
            filename="BENCH-TXT-CP1252-01.txt",
            format="txt",
            category="encoding",
            scenario="Windows-1252 (CP1252) legacy encoding with euro currency symbol",
            expected_status="success",
            accepted_statuses=["success"],
            expected_text=cp_text,
            expected_blocks=[
                {"block_type": "paragraph"},
                {"block_type": "paragraph"},
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

    # 1.7 Disguised Binary File
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
            expected_error_code="CORRUPT_DOCUMENT",
            expected_text="",
            expected_blocks=[],
            provisional_thresholds={"max_cer": 0.0, "min_car": 1.0, "require_exact_structure": True},
        )
    ))

    # ==========================================
    # 2. DOCX FIXTURES (8)
    # ==========================================

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
                {"block_type": "heading", "level": 1},
                {"block_type": "paragraph"},
                {"block_type": "heading", "level": 2},
                {"block_type": "paragraph"},
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
                {"block_type": "heading", "level": 1},
                {"block_type": "paragraph"},
                {"block_type": "paragraph"},
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
                {"block_type": "heading", "level": 1},
                {"block_type": "paragraph"},
                {"block_type": "heading", "level": 2},
                {"block_type": "paragraph"},
                {"block_type": "heading", "level": 3},
                {"block_type": "paragraph"},
            ],
            provisional_thresholds={"max_cer": 0.0, "min_car": 1.0, "require_exact_structure": True},
        )
    ))

    # 2.4 Table in Reading Order
    docx_tbl_bytes = _create_docx_bytes(
        paragraphs=[
            ("Heading1", "Delivery Rates Overview"),
        ],
        tables=[
            [
                ["Zone", "Charge", "Duration"],
                ["Inside Dhaka", "60 BDT", "24-48 Hours"],
                ["Outside Dhaka", "130 BDT", "3-5 Days"],
            ]
        ]
    )
    docx_tbl_text = (
        "Delivery Rates Overview\n\n"
        "Zone | Charge | Duration\n"
        "--------------------\n"
        "Inside Dhaka | 60 BDT | 24-48 Hours\n"
        "Outside Dhaka | 130 BDT | 3-5 Days"
    )
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
                {"block_type": "heading"},
                {"block_type": "table", "headers": ["Zone", "Charge", "Duration"], "row_count": 2},
            ],
            provisional_thresholds={"max_cer": 0.0, "min_car": 1.0, "require_exact_structure": True},
        )
    ))

    # 2.5 Table with Multi-row & Multi-line Cells
    docx_nest_bytes = _create_docx_bytes(
        paragraphs=[
            ("Heading1", "Product Specifications"),
        ],
        tables=[
            [
                ["Parameter", "Details"],
                ["Material", "100% Organic Combed Cotton"],
                ["Care Instructions", "Machine wash cold. Do not tumble dry."],
            ]
        ]
    )
    docx_nest_text = (
        "Product Specifications\n\n"
        "Parameter | Details\n"
        "--------------------\n"
        "Material | 100% Organic Combed Cotton\n"
        "Care Instructions | Machine wash cold. Do not tumble dry."
    )
    fixtures_with_gt.append((
        BenchmarkFixture(
            fixture_id="BENCH-DOCX-NEST-01",
            filename="BENCH-DOCX-NEST-01.docx",
            format="docx",
            category="tables",
            scenario="Table with multi-word and descriptive cell contents",
            raw_bytes=docx_nest_bytes,
        ),
        GroundTruth(
            fixture_id="BENCH-DOCX-NEST-01",
            filename="BENCH-DOCX-NEST-01.docx",
            format="docx",
            category="tables",
            scenario="Table with multi-word and descriptive cell contents",
            expected_status="success",
            accepted_statuses=["success"],
            expected_text=docx_nest_text,
            expected_blocks=[
                {"block_type": "heading"},
                {"block_type": "table", "headers": ["Parameter", "Details"], "row_count": 2},
            ],
            provisional_thresholds={"max_cer": 0.0, "min_car": 1.0, "require_exact_structure": True},
        )
    ))

    # 2.6 Embedded Images
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
                {"block_type": "heading"},
                {"block_type": "paragraph"},
            ],
            expected_metadata={"image_count": 1},
            provisional_thresholds={"max_cer": 0.0, "min_car": 1.0, "require_exact_structure": True},
        )
    ))

    # 2.7 Valid Empty DOCX
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
            expected_error_code="EMPTY_DOCUMENT",
            expected_text="",
            expected_blocks=[],
            provisional_thresholds={"max_cer": 0.0, "min_car": 1.0, "require_exact_structure": True},
        )
    ))

    # 2.8 Corrupted DOCX (Invalid Zip)
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
            expected_error_code="CORRUPT_DOCUMENT",
            expected_text="",
            expected_blocks=[],
            provisional_thresholds={"max_cer": 0.0, "min_car": 1.0, "require_exact_structure": True},
        )
    ))

    # ==========================================
    # 3. XLSX FIXTURES (9)
    # ==========================================

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
    xlsx_en_text = (
        "--- Sheet: Inventory ---\n"
        "SKU | Item Name | Price | Stock\n"
        "--------------------\n"
        "SKU-101 | Wireless Mouse | 25.00 | 50\n"
        "SKU-102 | Mechanical Keyboard | 85.00 | 20"
    )
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
                {"block_type": "table", "headers": ["SKU", "Item Name", "Price", "Stock"], "row_count": 2},
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
    xlsx_bn_text = (
        "--- Sheet: পণ্য_তালিকা ---\n"
        "আইডি | পণ্যের নাম | মূল্য | স্ট্যাটাস\n"
        "--------------------\n"
        "P-01 | সুতি পাঞ্জাবি | ১২৫০ | ইন স্টক\n"
        "P-02 | সিল্ক শাড়ি | ৩৫০০ | স্টক শেষ"
    )
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
                {"block_type": "table", "headers": ["আইডি", "পণ্যের নাম", "মূল্য", "স্ট্যাটাস"], "row_count": 2},
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
    xlsx_multi_text = (
        "--- Sheet: Catalog ---\n"
        "Code | Title\n"
        "--------------------\n"
        "C-1 | T-Shirt\n\n"
        "--- Sheet: Shipping ---\n"
        "Zone | Cost\n"
        "--------------------\n"
        "Metro | 60"
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
                {"block_type": "table", "headers": ["Code", "Title"], "row_count": 1},
                {"block_type": "table", "headers": ["Zone", "Cost"], "row_count": 1},
            ],
            expected_metadata={"sheet_names": ["Catalog", "Shipping"], "sheet_count": 2},
            provisional_thresholds={"max_cer": 0.0, "min_car": 1.0, "require_exact_structure": True},
        )
    ))

    # 3.4 Leading Zeros Preservation (Phone Numbers / Postal Codes)
    wb_zero = openpyxl.Workbook()
    ws_zero = wb_zero.active
    ws_zero.title = "Customers"
    ws_zero.append(["Customer", "Phone", "PostalCode"])
    # Write as explicit string type to ensure leading zero preserved
    ws_zero.append(["Customer A", "01712345678", "0800"])
    ws_zero.append(["Customer B", "01898765432", "0120"])
    buf_zero = io.BytesIO()
    wb_zero.save(buf_zero)
    xlsx_zero_bytes = buf_zero.getvalue()
    xlsx_zero_text = (
        "--- Sheet: Customers ---\n"
        "Customer | Phone | PostalCode\n"
        "--------------------\n"
        "Customer A | 01712345678 | 0800\n"
        "Customer B | 01898765432 | 0120"
    )
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
                {"block_type": "table", "headers": ["Customer", "Phone", "PostalCode"], "row_count": 2},
            ],
            provisional_thresholds={"max_cer": 0.0, "min_car": 1.0, "require_exact_structure": True},
        )
    ))

    # 3.5 Completely Empty XLSX
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
            expected_error_code="EMPTY_DOCUMENT",
            expected_text="",
            expected_blocks=[],
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
    xlsx_bsh_text = (
        "--- Sheet: ActiveData ---\n"
        "Key | Val\n"
        "--------------------\n"
        "K1 | V1"
    )
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
                {"block_type": "table", "headers": ["Key", "Val"], "row_count": 1},
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
    xlsx_hid_text = (
        "--- Sheet: PublicNotes ---\n"
        "Topic | Status\n"
        "--------------------\n"
        "Launch | Ready\n\n"
        "--- Sheet: Internal_Costs ---\n"
        "Component | Budget\n"
        "--------------------\n"
        "Hosting | 500"
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
                {"block_type": "table", "headers": ["Topic", "Status"], "row_count": 1},
                {"block_type": "table", "headers": ["Component", "Budget"], "row_count": 1},
            ],
            expected_metadata={"hidden_sheets": ["Internal_Costs"]},
            provisional_thresholds={"max_cer": 0.0, "min_car": 1.0, "require_exact_structure": True},
        )
    ))

    # 3.8 Formula Error (#VALUE!, #REF!)
    wb_err = openpyxl.Workbook()
    ws_err = wb_err.active
    ws_err.title = "Financials"
    ws_err.append(["Metric", "Calculation"])
    ws_err.append(["Net Margin", "#VALUE!"])
    buf_err = io.BytesIO()
    wb_err.save(buf_err)
    xlsx_err_bytes = buf_err.getvalue()
    xlsx_err_text = (
        "--- Sheet: Financials ---\n"
        "Metric | Calculation\n"
        "--------------------\n"
        "Net Margin | #VALUE!"
    )
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
                {"block_type": "table", "headers": ["Metric", "Calculation"], "row_count": 1},
            ],
            expected_metadata={"has_formula_errors": True},
            provisional_thresholds={"max_cer": 0.0, "min_car": 1.0, "require_exact_structure": True},
        )
    ))

    # 3.9 Corrupted XLSX
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
            expected_error_code="CORRUPT_DOCUMENT",
            expected_text="",
            expected_blocks=[],
            provisional_thresholds={"max_cer": 0.0, "min_car": 1.0, "require_exact_structure": True},
        )
    ))

    # ==========================================
    # 4. CSV FIXTURES (8)
    # ==========================================

    # 4.1 Comma-delimited English
    csv_comma_text = "SKU,Product,Price,Quantity\nA101,Desk Lamp,15.99,10\nB202,Office Chair,89.50,4"
    csv_comma_expected = (
        "SKU | Product | Price | Quantity\n"
        "--------------------\n"
        "A101 | Desk Lamp | 15.99 | 10\n"
        "B202 | Office Chair | 89.50 | 4"
    )
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
                {"block_type": "table", "headers": ["SKU", "Product", "Price", "Quantity"], "row_count": 2},
            ],
            expected_metadata={"delimiter": ","},
            provisional_thresholds={"max_cer": 0.0, "min_car": 1.0, "require_exact_structure": True},
        )
    ))

    # 4.2 Semicolon-delimited European CSV
    csv_semi_text = "SKU;Product;Price;Quantity\nC303;Espresso Mug;8.00;25\nD404;Coffee Beans;12.50;50"
    csv_semi_expected = (
        "SKU | Product | Price | Quantity\n"
        "--------------------\n"
        "C303 | Espresso Mug | 8.00 | 25\n"
        "D404 | Coffee Beans | 12.50 | 50"
    )
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
                {"block_type": "table", "headers": ["SKU", "Product", "Price", "Quantity"], "row_count": 2},
            ],
            expected_metadata={"delimiter": ";"},
            provisional_thresholds={"max_cer": 0.0, "min_car": 1.0, "require_exact_structure": True},
        )
    ))

    # 4.3 Tab-delimited TSV
    csv_tab_text = "Item_Code\tItem_Name\tLocation\tUnits\nT-01\tLaptop Stand\tWarehouse-A\t15\nT-02\tUSB Cable\tWarehouse-B\t100"
    csv_tab_expected = (
        "Item_Code | Item_Name | Location | Units\n"
        "--------------------\n"
        "T-01 | Laptop Stand | Warehouse-A | 15\n"
        "T-02 | USB Cable | Warehouse-B | 100"
    )
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
                {"block_type": "table", "headers": ["Item_Code", "Item_Name", "Location", "Units"], "row_count": 2},
            ],
            expected_metadata={"delimiter": "\t"},
            provisional_thresholds={"max_cer": 0.0, "min_car": 1.0, "require_exact_structure": True},
        )
    ))

    # 4.4 Pipe-delimited CSV
    csv_pipe_text = "Service|Tier|Monthly_Fee|SLA_Hours\nCloud Backup|Standard|29.99|24\nCloud Backup|Enterprise|149.99|4"
    csv_pipe_expected = (
        "Service | Tier | Monthly_Fee | SLA_Hours\n"
        "--------------------\n"
        "Cloud Backup | Standard | 29.99 | 24\n"
        "Cloud Backup | Enterprise | 149.99 | 4"
    )
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
                {"block_type": "table", "headers": ["Service", "Tier", "Monthly_Fee", "SLA_Hours"], "row_count": 2},
            ],
            expected_metadata={"delimiter": "|"},
            provisional_thresholds={"max_cer": 0.0, "min_car": 1.0, "require_exact_structure": True},
        )
    ))

    # 4.5 Complex Quoting with Commas and Embedded Newlines
    # Notice: In CSV, cell containing newline:
    # "Desk, Wood\nSolid Oak"
    # When extractor parses, newlines inside cells are preserved or converted into space
    # Let's check how csv_extractor renders cells:
    # In csv_extractor:
    #   row_cells = [str(c) if c is not None else "" for c in row]
    #   row_text = " | ".join(row_cells)
    # Let's verify how csv.reader reads embedded newlines!
    # In csv.reader, cell value is: 'Desk, Wood\nSolid Oak'
    csv_quoted_buf = io.StringIO()
    writer = csv.writer(csv_quoted_buf)
    writer.writerow(["ID", "Title", "Description", "Price"])
    writer.writerow(["101", "Gaming Chair", "Ergonomic, High-Back, Reclining", "180"])
    writer.writerow(["102", "Standing Desk", "Adjustable height\nSolid bamboo top", "350"])
    csv_quoted_str = csv_quoted_buf.getvalue()

    csv_quoted_expected = (
        "ID | Title | Description | Price\n"
        "--------------------\n"
        "101 | Gaming Chair | Ergonomic, High-Back, Reclining | 180\n"
        "102 | Standing Desk | Adjustable height\nSolid bamboo top | 350"
    )
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
                {"block_type": "table", "headers": ["ID", "Title", "Description", "Price"], "row_count": 2},
            ],
            provisional_thresholds={"max_cer": 0.0, "min_car": 1.0, "require_exact_structure": True},
        )
    ))

    # 4.6 Bengali CSV with UTF-8 BOM
    csv_bn_text = "পণ্যের আইডি,পণ্যের নাম,মূল্য,স্ট্যাটাস\nBN-01,পাঞ্জাবি,১২০০,উপলব্ধ\nBN-02,পায়জামা,৪৫০,উপলব্ধ"
    csv_bn_bytes = b"\xef\xbb\xbf" + csv_bn_text.encode("utf-8")
    csv_bn_expected = (
        "পণ্যের আইডি | পণ্যের নাম | মূল্য | স্ট্যাটাস\n"
        "--------------------\n"
        "BN-01 | পাঞ্জাবি | ১২০০ | উপলব্ধ\n"
        "BN-02 | পায়জামা | ৪৫০ | উপলব্ধ"
    )
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
                {"block_type": "table", "headers": ["পণ্যের আইডি", "পণ্যের নাম", "মূল্য", "স্ট্যাটাস"], "row_count": 2},
            ],
            expected_metadata={"encoding": "utf-8-sig"},
            provisional_thresholds={"max_cer": 0.0, "min_car": 1.0, "require_exact_structure": True},
        )
    ))

    # 4.7 Headerless Numeric CSV
    csv_nohead_text = "101,45.50,1\n102,99.00,2\n103,15.25,3"
    csv_nohead_expected = (
        "column_1 | column_2 | column_3\n"
        "--------------------\n"
        "101 | 45.50 | 1\n"
        "102 | 99.00 | 2\n"
        "103 | 15.25 | 3"
    )
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
                {"block_type": "table", "headers": ["column_1", "column_2", "column_3"], "row_count": 3},
            ],
            provisional_thresholds={"max_cer": 0.0, "min_car": 1.0, "require_exact_structure": True},
        )
    ))

    # 4.8 Jagged / Ragged Rows CSV
    csv_jagged_text = "H1,H2,H3,H4\nA,B,C,D\nE,F\nG,H,I\nJ,K,L,M"
    # Extractor normalizes jagged rows to 4 columns by padding empty strings:
    # row 3: E | F |  | 
    # row 4: G | H | I | 
    csv_jagged_expected = (
        "H1 | H2 | H3 | H4\n"
        "--------------------\n"
        "A | B | C | D\n"
        "E | F |  | \n"
        "G | H | I | \n"
        "J | K | L | M"
    )
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
                {"block_type": "table", "headers": ["H1", "H2", "H3", "H4"], "row_count": 4},
            ],
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
        # Write binary fixture
        file_path = os.path.join(fixtures_dir, fix.filename)
        with open(file_path, "wb") as f:
            f.write(fix.raw_bytes)
        fix.file_path = file_path

        # Write ground truth JSON
        gt_path = os.path.join(gt_dir, f"{fix.fixture_id}.json")
        with open(gt_path, "w", encoding="utf-8") as f:
            json.dump(gt.to_dict(), f, indent=2, ensure_ascii=False)

        saved_items.append((fix, gt))

    return saved_items


if __name__ == "__main__":
    items = save_fixtures_to_disk()
    print(f"Successfully generated and wrote {len(items)} fixtures to benchmark/fixtures and benchmark/ground_truth.")
