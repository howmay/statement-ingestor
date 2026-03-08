# TRD v1: Gmail Receipt & Invoice Extractor (MVP)

**Author**: Ethan (Developer Agent)  
**Date**: 2026-03-08  
**Status**: Draft (Pending Review)  
**Related Issue**: [#9](https://github.com/zhChenOuO/gmail-expense-parser/issues/9)

---

## 1. Overview

This document describes the technical requirements for the **Gmail Receipt & Invoice Extractor MVP**, a single‑run Python script that scans Gmail accounts, filters receipt/invoice emails, downloads PDF attachments, extracts structured billing information, and exports the data to CSV.

## 2. Technical Stack

- **Language**: Python 3.8+ (single‑run script, per team rules)
- **Package Management**: `pip` + `requirements.txt`
- **Version Control**: Git + GitHub
- **Environment**: Local execution, no daemon or scheduling required

## 3. Core Modules

### 3.1 Authentication & Configuration
- **Gmail API**: Use `google-auth` and `google-api-python-client` for OAuth2 or Service Account authentication.
- **Configuration**: Sensitive credentials (API keys, LLM keys) stored in `.env` (template provided).
- **Multi‑account**: Support multiple predefined Gmail accounts via configuration.

### 3.2 Email Filtering & Fetching
- **Search Criteria**:
  - Sender addresses (allow‑list)
  - Keywords in subject/body
  - Must have PDF attachment (`has:attachment filename:pdf`)
- **Gmail API Usage**: Use `service.users().messages().list()` and `service.users().messages().get()` to retrieve messages and attachments.
- **Attachment Download**: PDFs are downloaded to a local temporary directory.

### 3.3 PDF Processing
- **Text Extraction**: Use `pdfplumber` (primary) or `PyPDF2` (fallback) to extract raw text from PDFs.
- **Assumption**: MVP assumes text‑based PDFs; scanned/image‑based PDFs (requiring OCR) are out of scope and will be logged as errors.

### 3.4 Data Extraction (LLM‑Based)
- **Parser Approach**: Because receipt formats vary widely, an LLM (OpenAI GPT‑4/GPT‑3.5 or compatible) will be used to parse extracted text into structured JSON.
- **Extracted Fields**:
  - `Date` (日期)
  - `Amount` (金額)
  - `Expense Name / Item` (消費名目)
  - `Type` (類型)
  - `Source` (來源)
- **LLM Integration**: Python `openai` SDK (or equivalent) with a carefully crafted prompt that ensures consistent JSON output.

### 3.5 Output Generation
- **Format**: CSV (comma‑separated values) with a header row matching the five fields above.
- **Library**: Python’s built‑in `csv` module (or `pandas` if additional processing is needed).
- **File Name**: `output.csv` (configurable location).

### 3.6 Logging & Error Handling
- **Logging**: Python `logging` module with configurable level (INFO by default).
- **Error Handling**:
  - Network failures (Gmail API, LLM API)
  - Malformed PDFs
  - Missing credentials
  - LLM parsing failures
- **Progress Reporting**: Console output for each major step (email count, PDFs downloaded, records parsed).

## 4. Execution Flow

1. **Load Configuration**: Read `.env` (or environment variables) for Gmail credentials, LLM API key, target senders, keywords.
2. **Authenticate**: Obtain Gmail API service object.
3. **Search & Fetch**:
   - Query Gmail for messages matching senders + keywords + PDF attachment.
   - Download PDF attachments to a temporary directory.
4. **Process Each PDF**:
   - Extract text using `pdfplumber`.
   - Send text to LLM with parsing prompt.
   - Receive structured JSON.
   - Append JSON to in‑memory list.
5. **Generate CSV**: Convert list of JSON objects to CSV, write to `output.csv`.
6. **Cleanup**: Remove temporary files, close connections.
7. **Report**: Print summary (records processed, CSV location).

## 5. Testing Strategy

Each module must be independently testable:

| Module | Test Method |
|--------|-------------|
| Authentication | Mock credentials; verify service object creation |
| Email Filtering | Unit test with mocked Gmail API responses |
| PDF Extraction | Test with known text‑based PDF samples |
| LLM Parsing | Unit test with sample receipt text, mock LLM response |
| CSV Output | Verify CSV file contains correct headers and data |
| End‑to‑End | Run script with a test Gmail account & dummy PDFs |

## 6. Deliverables

1. **Source Code** in `src/` directory:
   - `src/auth/gmail_auth.py`
   - `src/fetch/fetch_emails.py`
   - `src/fetch/download_pdfs.py`
   - `src/pdf/pdf_to_text.py`
   - `src/llm/parse_receipt.py`
   - `src/output/csv_writer.py`
   - `src/main.py` (entry point)
2. **Configuration Templates**:
   - `.env.example`
   - `config.yaml.example` (optional)
3. **Documentation**:
   - `README.md` (setup & usage)
   - `requirements.txt`
   - This TRD (`docs/TRD_v1.md`)
4. **Output**: CSV file with extracted data.

## 7. Assumptions & Constraints

- **PDF Type**: Only text‑based PDFs are supported; scanned PDFs will be skipped.
- **LLM Cost**: LLM API calls will incur cost; budget should be monitored.
- **Gmail Quotas**: Gmail API daily quotas must be respected (batch size may need limiting).
- **Single‑Run**: No scheduling, no daemon; manual execution only.

## 8. Future Enhancements (Out of Scope for MVP)

- OCR for scanned PDFs
- Database storage (PostgreSQL, SQLite)
- Web dashboard for review
- Automated scheduling (cron, CI/CD)
- Support for other email providers (Outlook, Yahoo)
- Multi‑language receipt parsing

---

**Approval**  
This TRD requires review and approval via Pull Request before any implementation begins.

*Signature*  
Ethan (Developer Agent)  
developer@openclaw.local