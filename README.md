# Document Ingestion Worker (Phase 2A)

This package implements reliable, isolated, format-aware document text and tabular extraction for the Dynamic Business Knowledge Ingestion system. It lives as an independent Python service under `Entrepreneurs_Automation/python-ingestion-worker/`.

## Architecture & Isolation Boundaries
- **Sibling Project**: Located at `Entrepreneurs_Automation/python-ingestion-worker/`, completely isolated from `multi-source-chatbot` (Laravel) and `python-ai-service` (retrieval service).
- **Independent Virtual Environment**: Maintains its own dedicated virtual environment and `requirements.txt`. Does not share or modify packages in `python-ai-service/venv`.
- **Purely Local & Deterministic**: Zero network access, zero database dependencies, zero LLM calls.
- **Strict Scope**: Implements text and tabular extraction for `.txt`, `.docx`, `.xlsx`, and `.csv`. PDF/OCR, chunking, embeddings, and Typesense indexing are handled in subsequent pipeline stages.

## Supported Formats (Phase 2A)
- **Plain Text (`.txt`)**: UTF-8, UTF-8-BOM, legacy encodings (via `charset-normalizer` with fallback to Latin-1/Windows-1252), Bengali Unicode NFC preservation, line/paragraph boundary normalization.
- **Word Document (`.docx`)**: Headings hierarchy (`h1`, `h2`, `h3`, etc.), paragraphs in reading order, structured table extraction with column header associations and row/cell relationships. Supports both `python-docx` and native standard library XML fallback.
- **Excel Spreadsheet (`.xlsx`)**: Read-only extraction via `openpyxl`, multi-sheet traversal, table header preservation, cached formula value extraction, leading zero and code string preservation, hidden sheet detection.
- **Comma-Separated Values (`.csv`)**: Python standard library `csv`, conservative dialect detection (`csv.Sniffer`), delimiter fallback, multiline quoted fields, BOM handling, jagged/uneven row handling.

## Directory Structure
```
python-ingestion-worker/
├── requirements.txt            # Dedicated worker dependencies
├── README.md                   # Environment setup & documentation
├── app/
│   ├── contracts.py            # ExtractionStatus, BlockType, DocumentBlock, TableBlock, ExtractionResult
│   ├── exceptions.py           # Sanitized exceptions (no leaked paths or secrets)
│   ├── service.py              # DocumentExtractionService (mime/magic byte validation, size limits, dispatch)
│   └── extractors/
│       ├── base.py             # BaseExtractor with security limits, path normalization, sanitized stats
│       ├── txt_extractor.py    # TxtExtractor
│       ├── docx_extractor.py   # DocxExtractor
│       ├── xlsx_extractor.py   # XlsxExtractor
│       └── csv_extractor.py    # CsvExtractor
└── tests/                      # Comprehensive test suite covering all 4 formats and edge cases
```

## Virtual Environment & Setup

To run in a dedicated virtual environment:

```bash
# 1. Navigate to the worker directory
cd /Users/zesan/Desktop/Entrepreneurs_Automation/python-ingestion-worker

# 2. Create an isolated virtual environment
python3 -m venv venv

# 3. Activate the environment
source venv/bin/activate

# 4. Install pinned requirements
pip install -r requirements.txt

# 5. Run the test suite
python -m unittest discover -s tests -v
```

## Security & Resource Safeguards
1. **Untrusted Input Handling**: Every file is treated as hostile. Magic byte / signature verification is enforced prior to parsing.
2. **Decompression Bomb Protection**: Archive-based formats (`.docx`, `.xlsx`) enforce a 50 MB uncompressed size ceiling and check decompression ratios.
3. **No Code/Formula Execution**: No macro execution, no dynamic formula calculation; cached formula values are read passively.
4. **Path Sanitization**: Absolute paths are never exposed in user-facing error messages or logged.
5. **No Network Access & No LLM Calls**: Extraction is purely deterministic, local, and isolated.
