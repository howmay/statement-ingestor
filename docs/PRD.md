# Product Requirements Document (PRD)
## Gmail Receipt & Invoice Extractor (MVP)

**Author**: Julian (PM Agent)  
**Date**: 2026-03-11  
**Status**: Draft (Pending Review)  
**Related Issues**: [#19](https://github.com/zhChenOuO/gmail-expense-parser/issues/19), [#22](https://github.com/zhChenOuO/gmail-expense-parser/issues/22), [#23](https://github.com/zhChenOuO/gmail-expense-parser/issues/23), [#24](https://github.com/zhChenOuO/gmail-expense-parser/issues/24)

---

## 1. Overview

A single-run Python utility that scans specified Gmail accounts, filters receipt/invoice emails, extracts PDF attachments, parses billing information using LLM with fallback mechanisms, and exports structured data to CSV.

**Primary Goal**: Automate expense data extraction from Gmail receipts and bank statements for financial tracking and reporting.

---

## 2. Core Features

### 2.1 Authentication & Configuration
- **Multi-Account Support**: Scan multiple Gmail accounts via API keys or OAuth credentials
- **Configuration**: Sensitive credentials stored in `.env` file with templates provided
- **Account Management**: Predefined list of target email addresses/accounts

### 2.2 Email Filtering
- **Sender Filtering**: Filter by specific sender email addresses (allow-list)
- **Keyword Search**: Match keywords in subject or email body
- **Attachment Filter**: Only process emails with PDF attachments
- **Gmail API**: Use `service.users().messages().list()` and `service.users().messages().get()` for retrieval

### 2.3 PDF Processing
- **Text Extraction**: Use `pdfplumber` (primary) or `PyPDF2` (fallback) for text extraction
- **PDF Constraint**: MVP supports **text-based PDFs only**; scanned/image-based PDFs (requiring OCR) are out of scope
- **Download**: PDFs downloaded to local temporary directory during processing
- **Cleanup**: Automatic cleanup of temporary files after processing

### 2.4 Data Extraction (Hybrid Approach)

#### LLM-Based Parsing (Primary)
- **Parser**: OpenAI GPT-4/GPT-3.5 or compatible model via Python `openai` SDK
- **Prompt Engineering**: Carefully crafted prompt for consistent JSON output
- **Output Fields**:
  - `Date` (日期)
  - `Amount` (金額)
  - `Expense Name / Item` (消費名目)
  - `Type` (類型)
  - `Source` (來源)
  - `Currency` (幣別)
  - `Confidence` (解析信心度)
  - `Raw Text Snippet` (原始文本片段)
  - `Parsing Method` (解析方式)
  - `Parser Name` (解析器名稱)

#### Deterministic Bank Parsers (Fallback)
- **Purpose**: Handle common bank statement formats without LLM overhead
- **Supported Banks**:
  - **HSBC Taiwan**: `src/bank_parsers/hsbc.py`
  - **台北富邦銀行**: `src/bank_parsers/fubon.py`
  - **玉山銀行**: `src/bank_parsers/esun.py`
- **Factory Pattern**: `src/bank_parsers/factory.py` routes to appropriate parser based on sender/subject analysis
- **Benefits**: Faster execution, no API cost, deterministic output

#### Adaptive Strategy (LLM)
- **Intelligent Chunking**: For large transaction lists (e.g., 30+ transactions), automatically split text based on transaction boundaries
- **JSON Repair**: Enhanced stack-based mechanism to fix truncated JSON responses from LLM
- **Dynamic Parameter Tuning**: Adjust `max_tokens` based on input text length
- **Result Merging**: Merge transactions from multiple chunks with deduplication
- **Retry Logic**: Multi-stage retry strategies with exponential backoff

### 2.5 Large Transaction Handling (Issue #24 Solution)
- **Problem**: OpenAI API truncates JSON responses at ~6000 characters for large HSBC transaction lists
- **Solution**:
  1. **Enhanced JSON Repair** (`_fix_truncated_json_enhanced`): Stack-based mechanism to recover truncated JSON
  2. **Intelligent Chunking** (`_chunk_text_by_transactions`): Split text at transaction boundaries (dates)
  3. **Adaptive Strategy** (`_parse_with_adaptive_strategy`): Decide when to enable chunking based on document characteristics
  4. **Result Merging** (`_merge_transaction_results`): Merge and deduplicate results from chunks
  5. **Multi-stage Retry**: Retry logic supports multiple recovery attempts
- **Success Rate**: Increased from ~60% to ~95% for large transaction lists
- **Configuration**:
  ```
  ENABLE_ADAPTIVE_CHUNKING=true
  MAX_CHUNK_SIZE=3500
  MIN_TRANSACTIONS_PER_CHUNK=5
  ```

### 2.6 Output Generation
- **Format**: CSV (comma-separated values) with header row
- **Fields**: Date, Amount, Expense Name, Type, Source, Currency
- **File Name**: `output.csv` (configurable)
- **Delivery**: Send resulting CSV to designated group chat for review

### 2.7 Error Handling & Logging
- **Logging**: Python `logging` module with INFO level by default
- **Error Categories**:
  - Network failures (Gmail API, LLM API)
  - Malformed PDFs
  - Missing credentials
  - LLM parsing failures
  - Bank parser mismatches
- **Progress Reporting**: Console output for each major step (email count, PDFs downloaded, records parsed)
- **Graceful Degradation**: Fallback to regex/heuristic parsing when LLM fails

---

## 3. Technical Architecture

### 3.1 Directory Structure
```
gmail-expense-parser/
├── src/
│   ├── auth/
│   │   └── gmail_auth.py
│   ├── fetch/
│   │   ├── fetch_emails.py
│   │   └── download_pdfs.py
│   ├── pdf/
│   │   └── pdf_to_text.py
│   ├── bank_parsers/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── factory.py
│   │   ├── hsbc.py
│   │   ├── fubon.py
│   │   └── esun.py
│   ├── llm/
│   │   ├── parse_receipt.py
│   │   └── retry.py
│   ├── output/
│   │   └── csv_writer.py
│   └── parser_factory.py
├── config/
├── tests/
├── docs/
│   ├── SPEC_MVP.md
│   ├── TRD_v1.md
│   └── ISSUE_*_REPORT.md
├── .env.example
├── requirements.txt
├── README.md
└── main.py
```

### 3.2 Module Responsibilities

| Module | Responsibility |
|--------|---------------|
| `auth/gmail_auth.py` | Gmail API authentication and service object creation |
| `fetch/fetch_emails.py` | Search and retrieve emails matching criteria |
| `fetch/download_pdfs.py` | Download PDF attachments to temporary directory |
| `pdf/pdf_to_text.py` | Extract text from PDF files |
| `bank_parsers/base.py` | Base class for deterministic bank parsers |
| `bank_parsers/factory.py` | Factory pattern to route to appropriate bank parser |
| `bank_parsers/hsbc.py` | HSBC Taiwan bank statement parser |
| `bank_parsers/fubon.py` | Taipei Fubon bank statement parser |
| `bank_parsers/esun.py` | E-Sun bank statement parser |
| `llm/parse_receipt.py` | LLM-based receipt parsing with adaptive strategy |
| `llm/retry.py` | Multi-stage retry logic for API calls |
| `output/csv_writer.py` | Generate CSV output files |
| `parser_factory.py` | Central parsing dispatcher (LLM or Bank Parser) |

### 3.3 Execution Flow
```
1. Load Configuration (.env)
   ↓
2. Authenticate (Gmail API)
   ↓
3. Search & Fetch Emails
   - Filter by: sender + keywords + PDF attachment
   ↓
4. Process Each PDF
   - Extract text (pdfplumber)
   - Determine parser type (Bank Parser or LLM)
   - Parse using appropriate method
   - Handle chunking for large documents
   ↓
5. Merge & Deduplicate Results
   ↓
6. Generate CSV
   ↓
7. Cleanup & Report
```

---

## 4. Implementation Progress

### ✅ Completed Features
- **Issue #19**: Multi-transaction parsing for bank statements
- **Issue #22**: Python dependency setup and virtual environment
- **Issue #23**: Comprehensive error handling and logging
- **Issue #24**: Enhanced JSON repair and intelligent chunking for large transaction lists
- **Bank Parsers**: Deterministic parsers for HSBC, Fubon, and E-Sun
- **Parser Factory**: Centralized routing logic for LLM vs. Bank Parser
- **PDF Download**: Enhanced download_pdfs.py with sender-based naming
- **Test Coverage**: Unit tests for bank parsers and LLM parsing

### 🔄 In Progress
- **Branch**: `fix-issue-24-large-transactions`
- **Pending**: Code review and merge to main
- **Next Step**: Integration testing with real Gmail accounts

### ⏳ Pending Features
- **Step 1**: Gmail API/IMAP connection module (if not yet implemented)
- **Step 2**: PDF text extraction (if not yet implemented)
- **Step 3**: Email filtering and PDF download (if not yet implemented)
- **Step 4**: PDF text extraction refinement (if not yet implemented)
- **Step 5**: LLM parsing integration (if not yet implemented)
- **Step 6**: CSV export and group chat delivery (if not yet implemented)

---

## 5. Assumptions & Constraints

### Assumptions
1. **PDF Type**: Only text-based PDFs are supported; scanned PDFs will be logged as errors
2. **LLM Cost**: LLM API calls incur cost; budget should be monitored
3. **Gmail Quotas**: Gmail API daily quotas must be respected; batch size may need limiting
4. **Single-Run**: No scheduling or daemon; manual execution only
5. **Transaction Format**: Bank statements follow predictable line-based formats with date delimiters

### Constraints
1. **Language**: Python 3.8+ (single-run script)
2. **Environment**: Local execution, no cloud hosting required
3. **Dependencies**: Managed via `pip` + `requirements.txt`
4. **Version Control**: Git + GitHub with proper commit authorship tracking
5. **API Rate Limits**: Must respect Gmail API and LLM API quotas

---

## 6. Testing Strategy

| Module | Test Method |
|--------|-------------|
| Authentication | Mock credentials; verify service object creation |
| Email Filtering | Unit test with mocked Gmail API responses |
| PDF Extraction | Test with known text-based PDF samples |
| Bank Parsers | Test with real bank statement samples (HSBC, Fubon, E-Sun) |
| LLM Parsing | Unit test with sample receipt text, mock LLM response |
| Chunking Logic | Test with large transaction lists (30+ entries) |
| CSV Output | Verify CSV file contains correct headers and data |
| End-to-End | Run script with test Gmail account & dummy PDFs |
| Error Handling | Test with malformed PDFs, missing credentials, network failures |

### Test Files
- `test_bank_parsers.py`: Bank parser unit tests
- `test_issue_24_large_transactions.py`: Large transaction handling tests
- `test_chunking.py`: Chunking logic tests

---

## 7. Deliverables

1. **Source Code** in `src/` directory:
   - All modules as listed in Technical Architecture
2. **Configuration Templates**:
   - `.env.example`
3. **Documentation**:
   - `README.md` (setup & usage)
   - `requirements.txt`
   - `docs/SPEC_MVP.md`
   - `docs/TRD_v1.md`
   - This PRD (`docs/PRD.md`)
   - Issue-specific reports (`ISSUE_*_REPORT.md`)
4. **Output**: CSV file with extracted data
5. **Tests**: Comprehensive test suite with coverage for all modules

---

## 8. Approval & Review

### Review Checklist
- [ ] All specifications documented and agreed upon
- [ ] Technical architecture reviewed by Developer (Ethan)
- [ ] Bank parser implementations tested with real samples
- [ ] Large transaction handling validated (Issue #24)
- [ ] Error handling and logging verified
- [ ] Test coverage meets requirements
- [ ] README and documentation complete

### Approval Process
1. This PRD requires review and approval via Pull Request before any new implementation begins
2. Developer (Ethan) to implement pending features
3. PM (Julian) to review and verify against specifications
4. Merge to main branch upon successful review

---

**Approvals**

| Role | Signature | Date |
|------|-----------|------|
| Developer (Ethan) | ___________________ | __________ |
| PM (Julian) | ___________________ | __________ |
| Owner (zh) | ___________________ | __________ |

---

*Last Updated*: 2026-03-11  
*Document Version*: 1.0