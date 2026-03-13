# TRD v1: Gmail Expense Parser - All-Income & All-Expense (MVP)

**Author**: Ethan (Developer Agent)  
**Date**: 2026-03-13  
**Status**: Updated (Reflecting Implementation & PRD)  
**Related Issues**: [#9](https://github.com/zhChenOuO/gmail-expense-parser/issues/9), [#19](https://github.com/zhChenOuO/gmail-expense-parser/issues/19), [#22](https://github.com/zhChenOuO/gmail-expense-parser/issues/22), [#23](https://github.com/zhChenOuO/gmail-expense-parser/issues/23), [#24](https://github.com/zhChenOuO/gmail-expense-parser/issues/24)

---

## 1. Overview

This document describes the technical requirements for the **Gmail Expense Parser**, an automated tool to extract **all income and expense transactions** from credit card statements, bank accounts, and third-party payments found in Gmail. It exports structured CSV data for personal finance tracking.

## 2. Technical Stack

- **Language**: Python 3.8+
- **Package Management**: `pip` + `requirements.txt`
- **Authentication**: Gmail API (OAuth2), OpenAI-compatible API (Local/Cloud)
- **PDF Extraction**: `pypdfium2`, `pdfplumber`, `pdftotext` (multi-engine fallback)
- **OCR**: Tesseract (for image-based attachments)

## 3. Core Modules

### 3.1 Authentication & Configuration
- **Gmail API**: OAuth2 flow with token caching.
- **Config**: `.env` for API keys, target senders, and keywords.
- **Bank Passwords**: Encrypted or environment-based password support for protected PDFs.

### 3.2 Email Filtering & Attachment Fetching
- **Multi-criteria Search**: Sender allow-list, subject keywords, date ranges.
- **Attachment Support**: PDF, Images, and Plain Text emails.
- **Deduplication (Fetch Level)**: File-level deduplication using MD5 hashes to avoid redundant processing.

### 3.3 Multi-Strategy Parsing Engine
- **Deterministic Bank Parsers (Priority 1)**: 
  - Regex/Pattern-based parsers for known formats: HSBC (TW), Fubon (Bank/Card), E.SUN (Card), DBS.
  - 100% accuracy for supported formats.
- **LLM-Based Parser (Priority 2)**:
  - Adaptive parser for unknown formats (OpenAI GPT-4o-mini or local Qwen-3.5).
  - **Intelligent Chunking**: Splits large statements (30+ transactions) into smaller segments to handle context window limits.
  - **JSON Repair**: Stack-based mechanism to fix truncated JSON from LLM outputs.
- **Heuristic Fallback (Priority 3)**: Basic regex extraction if LLM is unavailable.

### 3.4 Data Schema & Normalization
Each transaction record includes:
- `Date` (YYYY-MM-DD)
- `Amount` (Numeric, normalized)
- `Currency` (TWD, USD, etc.)
- `Category` (Income / Expense)
- `Description` / `Expense Name`
- `Transaction Type` (Withdrawal, Deposit, Payment, etc.)
- `Source` (Bank/Card name)
- `Source File` (Filename)
- `Confidence` (0.0 to 1.0)

### 3.5 Deduplication & Quality Control
- **Dual-Layer Deduplication**:
  - **File Level**: Skip previously processed PDF MD5s.
  - **Transaction Level**: Deduplicate using a composite key `(Date, Amount, Currency, Description, Source)`.
- **Validation**: Strict mode (`STRICT_BANK_PARSER`) to ensure high-quality extraction from known formats.

### 3.6 Output & Delivery
- **CSV Export**: Grouped by month (`YYYY-MM_expenses.csv`).
- **Group Delivery**: (Planned) Automated sync to designated group chat via Webhook.

## 4. Execution Flow

1. **Initialize**: Load `.env`, validate config, and authenticate.
2. **Fetch**: Search Gmail for target emails within the date range.
3. **Download**: Save unique attachments (deduped by MD5).
4. **Extract**: Convert PDF/Images to text (using OCR if needed).
5. **Parse**: Execute parsing strategy (Bank Factory -> LLM -> Heuristics).
6. **Deduplicate**: Filter redundant transactions.
7. **Export**: Generate monthly CSV files and report statistics.

## 5. Testing & Validation

- **Unit Tests**: For each bank parser in `test/test_bank_parsers.py`.
- **Integration Tests**: Mocking Gmail/LLM APIs to verify end-to-end pipeline.
- **Confidence Scoring**: Records with low confidence (LLM-based) are flagged for manual review.

## 6. Maintenance Note

Current implementation work targets `main.py` and `src/`. Files under `legacy/` are retained for reference and migration history only.

---

**Approval Status**  
Updated to reflect current codebase (March 2026).
