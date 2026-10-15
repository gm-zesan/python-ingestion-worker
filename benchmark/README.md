# Document Extraction Benchmark (Phase 2B Baseline)

The Document Extraction Benchmark suite provides an independent, offline, deterministic evaluation harness for verifying the extraction fidelity of `.txt`, `.docx`, `.xlsx`, and `.csv` files against frozen Phase 2A extraction contracts.

---

## 1. Architecture & Components

```
benchmark/
├── __init__.py           # Package exports
├── models.py             # Data models (GroundTruth, FixtureEvaluationResult, BenchmarkReport, FormatSummary)
├── evaluator.py          # Levenshtein distance, CER/CAR, structural checks, warnings, Unicode NFC
├── generator.py          # Deterministic generator for all 45 fixtures and ground-truth expectations
├── harness.py            # Execution harness, manifest validation, aggregate statistics, console formatter
├── run.py                # Command-line entrypoint (`python -m benchmark.run`)
├── fixtures/             # 45 deterministic binary fixtures
├── ground_truth/         # 45 independent ground-truth JSON files
└── README.md             # Baseline documentation and inventory
```

---

## 2. Execution Commands

All commands must be executed using the dedicated worker virtual environment:

```bash
cd /Users/zesan/Desktop/Entrepreneurs_Automation/python-ingestion-worker

# 1. Run the complete benchmark CLI
venv/bin/python -m benchmark.run

# 2. Run the benchmark for a specific format only
venv/bin/python -m benchmark.run --format txt

# 3. Force deterministic regeneration of fixtures and ground truth
venv/bin/python -m benchmark.run --regenerate-fixtures

# 4. Run the full unit test suite (77 tests)
venv/bin/python -m unittest discover -s tests -v

# 5. Check git whitespace / formatting
git diff --check
```

---

## 3. Evaluation Metrics & Policy

### Text Accuracy (CER / CAR)
- **Character Error Rate (CER)**: Computed as `Levenshtein(extracted, expected) / max(len(expected), 1)` after Unicode NFC normalization.
- **Character Accuracy Rate (CAR)**: Computed as `max(0.0, 1.0 - CER)`.
- **Inapplicable Metric Exclusion**: Negative / error fixtures report CER and CAR as `None` (N/A) rather than a dummy `1.0`. Mean CAR and CER are strictly averaged over fixtures where text comparison is applicable (`text_applicable=True`), with the text denominator explicitly reported.
- **Empty Expected Text Defense**: If ground truth expects empty text, any extracted text triggers `CER = 1.0` and immediate failure.

### Unicode & Bengali Preservation Policy
- Normalization applies Unicode Canonical Composition (NFC).
- Line endings are unified (`\r\n` and `\r` -> `\n`).
- Trailing whitespace on lines is trimmed (`line.rstrip()`), but leading indentation (`  Indent`) is preserved.
- Paragraph boundaries (`\n\n`) are preserved.
- Bengali script characters (`U+0980..U+09FF`), Zero-Width Joiner (ZWJ `\u200D`), and Zero-Width Non-Joiner (ZWNJ `\u200C`) are strictly preserved.

### Structural Verification
- **Block Order & Count**: The sequence of document blocks must match the expected block list.
- **Block Types**: Blocks are checked for `heading`, `paragraph`, and `table` matching.
- **Heading Levels**: Heading blocks assert exact hierarchy levels (`level: 1, 2, 3`).
- **Table Integrity**: Tables verify exact header lists, row counts, and cell value matrices.
- **Worksheet Names**: Spreadsheet tables verify sheet names (`metadata["sheet_name"]`).

### Warning Validation
- **Required Warnings**: Documented substrings (e.g., `"embedded image"`, `"is hidden in workbook"`, `"Dialect sniffer uncertain"`) must appear case-insensitively in `result.warnings`.
- **Clean Fixtures**: Clean documents (`expected_status="success"` with no expected warnings) strictly fail if an unexpected warning is emitted.

### Negative & Error Code Enforcement
- Negative fixtures require exact error code matching against Phase 2A contracts (`FILE_EMPTY`, `CORRUPTED_FILE`, `INVALID_SIGNATURE`). Arbitrary error codes are disallowed.

---

## 4. Fixture Inventory (45 Fixtures)

### Plain Text (`txt`) — 9 Fixtures
| Fixture ID | Category | Scenario | Expected Status | Expected Error / Warning |
| :--- | :--- | :--- | :---: | :---: |
| `BENCH-TXT-EN-01` | Standard | Multi-paragraph English policy document | `success` | — |
| `BENCH-TXT-BN-01` | Multilingual | Bengali Unicode with ligatures, ZWJ/ZWNJ, and currency | `success` | — |
| `BENCH-TXT-MIX-01` | Multilingual | Mixed English, Bengali, and Banglish Q&A | `success` | — |
| `BENCH-TXT-BOM-01` | Encoding | UTF-8 with Byte Order Mark (BOM stripped) | `success` | — |
| `BENCH-TXT-CP1252-01` | Encoding | Windows-1252 legacy encoding with typographical quotes | `success` | — |
| `BENCH-TXT-EMPTY-01` | Edge Cases | 0-byte empty file | `failed` | `FILE_EMPTY` |
| `BENCH-TXT-WS-01` | Edge Cases | Whitespace-only file (spaces, tabs, newlines) | `failed` | `FILE_EMPTY` |
| `BENCH-TXT-BINARY-01` | Edge Cases | Disguised binary ELF executable with `.txt` extension | `failed` | `INVALID_SIGNATURE` |
| `BENCH-TXT-MOJIBAKE-01` | Edge Cases | High replacement-character ratio (>5%) | `needs_review` | `mojibake` |

### Word Document (`docx`) — 12 Fixtures
| Fixture ID | Category | Scenario | Expected Status | Expected Error / Warning |
| :--- | :--- | :--- | :---: | :---: |
| `BENCH-DOCX-EN-01` | Standard | English DOCX with headings and paragraphs | `success` | — |
| `BENCH-DOCX-BN-01` | Multilingual | Bengali DOCX with complex conjuncts | `success` | — |
| `BENCH-DOCX-STRUCT-01` | Structure | Deep heading hierarchy (`H1` -> `H2` -> `H3`) | `success` | — |
| `BENCH-DOCX-TBL-01` | Tables | Heading followed by structured table matrix | `success` | — |
| `BENCH-DOCX-INTERLEAVE-01` | Structure | Sequential interleaving of paragraphs and multiple tables | `success` | — |
| `BENCH-DOCX-MULTITBL-01` | Tables | Consecutive tables without intervening text | `success` | — |
| `BENCH-DOCX-MULTIPC-01` | Tables | Multiple paragraph elements inside table cells | `success` | — |
| `BENCH-DOCX-IMG-01` | Edge Cases | Embedded PNG media payload in `word/media/` | `success_with_warnings` | `embedded image` |
| `BENCH-DOCX-EMBED-01` | Edge Cases | Embedded OLE object in `word/embeddings/` | `success_with_warnings` | `embedded object` |
| `BENCH-DOCX-EMPTY-01` | Edge Cases | Valid zip container with empty body tags | `failed` | `FILE_EMPTY` |
| `BENCH-DOCX-CORRUPT-01` | Edge Cases | Malformed zip container | `failed` | `CORRUPTED_FILE` |
| `BENCH-DOCX-SPOOF-01` | Edge Cases | Plain ASCII text renamed to `.docx` | `failed` | `INVALID_SIGNATURE` |

### Excel Spreadsheet (`xlsx`) — 12 Fixtures
| Fixture ID | Category | Scenario | Expected Status | Expected Error / Warning |
| :--- | :--- | :--- | :---: | :---: |
| `BENCH-XLSX-EN-01` | Standard | Single-sheet English catalog | `success` | — |
| `BENCH-XLSX-BN-01` | Multilingual | Bengali catalog with Bengali numerals and script | `success` | — |
| `BENCH-XLSX-MULTI-01` | Structure | Multi-sheet workbook preserving inter-sheet order | `success` | — |
| `BENCH-XLSX-ZERO-01` | Edge Cases | Leading-zero preservation in phone/postal strings | `success` | — |
| `BENCH-XLSX-BLANKCELLS-01` | Structure | Sheet with interspersed empty/blank cells | `success` | — |
| `BENCH-XLSX-BLANKSH-01` | Edge Cases | Populated sheet and one empty sheet | `success_with_warnings` | `empty and contained no data` |
| `BENCH-XLSX-HIDDEN-01` | Edge Cases | Workbook containing a hidden worksheet | `success_with_warnings` | `is hidden in workbook` |
| `BENCH-XLSX-FORMULA-01` | Edge Cases | Cached formula error value (`#VALUE!`) | `needs_review` | `uncalculated formulas or Excel error values` |
| `BENCH-XLSX-UNCACHED-01` | Edge Cases | Uncached formula without pre-calculated `<v>` value | `success` | — |
| `BENCH-XLSX-EMPTY-01` | Edge Cases | Workbook with zero data cells across all sheets | `failed` | `FILE_EMPTY` |
| `BENCH-XLSX-CORRUPT-01` | Edge Cases | Non-zip binary payload with `.xlsx` extension | `failed` | `INVALID_SIGNATURE` |
| `BENCH-XLSX-CORRUPTZIP-01` | Edge Cases | Valid zip archive missing `xl/workbook.xml` | `failed` | `INVALID_SIGNATURE` |

### Comma-Separated Values (`csv`) — 12 Fixtures
| Fixture ID | Category | Scenario | Expected Status | Expected Error / Warning |
| :--- | :--- | :--- | :---: | :---: |
| `BENCH-CSV-COMMA-01` | Standard | Comma-delimited English tabular data | `success` | — |
| `BENCH-CSV-SEMI-01` | Delimiters | Semicolon-delimited European CSV | `success` | — |
| `BENCH-CSV-TAB-01` | Delimiters | Tab-delimited TSV tabular dataset | `success` | — |
| `BENCH-CSV-PIPE-01` | Delimiters | Pipe-delimited tabular file | `success` | — |
| `BENCH-CSV-QUOTED-01` | Quoting | Quoted delimiters and embedded newlines | `success` | — |
| `BENCH-CSV-ESCAPED-01` | Quoting | Escaped double quotes (`""`) inside quoted fields | `success` | — |
| `BENCH-CSV-BN-01` | Multilingual | Bengali CSV encoded in UTF-8 with BOM | `success` | — |
| `BENCH-CSV-NOHEAD-01` | Structure | Headerless numeric CSV requiring synthetic headers | `success_with_warnings` | `generated synthetic column names` |
| `BENCH-CSV-JAGGED-01` | Edge Cases | Ragged / uneven row lengths | `needs_review` | `Inconsistent column counts` |
| `BENCH-CSV-AMBIGUOUS-01` | Delimiters | Conflicting delimiters causing sniffer uncertainty | `needs_review` | `Dialect sniffer uncertain` |
| `BENCH-CSV-EMPTY-01` | Edge Cases | 0-byte empty file | `failed` | `FILE_EMPTY` |
| `BENCH-CSV-BINARY-01` | Edge Cases | Disguised binary ELF file with `.csv` extension | `failed` | `INVALID_SIGNATURE` |

---

## 5. Known Limitations & Documented Behaviors

1. **DOCX Native OpenXML Fallback**:
   - In environments where `python-docx` is not installed, the extractor uses direct OpenXML XML parsing.
   - Multiple paragraphs inside a table cell are merged into a single space-separated string (`"Line 1 Line 2"`).
   - Embedded images and OLE objects trigger warning messages but are not extracted or OCR-processed.
   - Drawing objects, shapes, text boxes, footnotes, and comments are not parsed in this phase.
2. **XLSX Uncached Formulas**:
   - `openpyxl` in `data_only=True` mode does not calculate formulas.
   - If an Excel file is generated without pre-calculated cached values (`<v>` tag missing), the cell value evaluates to `None` (extracted as `""`).
   - The extractor cannot distinguish an uncached formula cell from an empty cell; no formula evaluation warning is emitted.
3. **CSV Dialect Heuristics**:
   - When conflicting delimiters cause `csv.Sniffer` to fail, the extractor falls back to character frequency heuristics, downgrading status to `needs_review`.
   - Ragged rows are padded with trailing empty strings to maintain tabular consistency.

---

## 6. Generated-File Policy

- **Binary Fixtures (`benchmark/fixtures/`)**: Deterministically generated from raw byte payloads or `openpyxl` workbooks with fixed timestamps. SHA-256 hashes are identical across generation runs.
- **Ground Truth (`benchmark/ground_truth/`)**: Deterministically generated JSON files with sorted keys and UTF-8 encoding.
- **Regeneration**: Running `python -m benchmark.run --regenerate-fixtures` regenerates all files bitwise identically.
- **JSON Report (`benchmark_report.json`)**: Machine-readable output generated by `run.py`.
