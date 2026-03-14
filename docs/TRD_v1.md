# TRD v1: Gmail Expense Parser - All-Income & All-Expense (MVP)

**Author**: Ethan (Developer Agent)  
**Date**: 2026-03-13  
**Status**: Updated (Reflecting Implementation & PRD)  
**Related Issues**: [#9](https://github.com/zhChenOuO/gmail-expense-parser/issues/9), [#19](https://github.com/zhChenOuO/gmail-expense-parser/issues/19), [#22](https://github.com/zhChenOuO/gmail-expense-parser/issues/22), [#23](https://github.com/zhChenOuO/gmail-expense-parser/issues/23), [#24](https://github.com/zhChenOuO/gmail-expense-parser/issues/24)

---

## 1. Overview

This document describes the technical requirements for the **Gmail Expense Parser**, an automated tool to extract income and expense transactions from **monthly credit-card statements and bank statements** found in Gmail. Merchant receipts are intentionally excluded from the primary search path to reduce duplicate counting.

## 2. Technical Stack

- **Language**: Python 3.8+
- **Package Management**: `pip` + `requirements.txt`
- **Authentication**: Gmail API (OAuth2), OpenAI-compatible API (Local/Cloud)
- **PDF Extraction**: `pypdfium2`, `pdfplumber`, `pdftotext` (multi-engine fallback)
- **OCR**: Tesseract (for image-based attachments)

## 3. Core Modules

### 3.1 Authentication & Configuration
- **Gmail API**: OAuth2 flow with token caching.
- **Config**: `.env` for API keys and statement search profiles.
- **Bank Passwords**: Encrypted or environment-based password support for protected PDFs.
- **Active Paths**: `src/core/`, `src/support/`, and `src/integrations/gmail/`.

### 3.2 Email Filtering & Attachment Fetching
- **Statement-Only Search**: Gmail query generation is driven by `STATEMENT_SEARCH_PROFILES`, with each profile defining sender constraints, statement subject keywords, optional exclusion keywords, and PDF attachment requirements.
- **Legacy Fallback**: `TARGET_SENDERS` and `TARGET_KEYWORDS` remain available only as compatibility fallback when statement profiles are absent.
- **Attachment Support**: Statement emails with PDF attachments are the primary target.
- **Deduplication (Fetch Level)**: File-level deduplication using MD5 hashes to avoid redundant processing.

### 3.3 Multi-Strategy Parsing Engine
- **Deterministic Bank Parsers (Priority 1)**: 
  - Regex/Pattern-based parsers under `src/parsing/banks/` for known formats: HSBC (TW), Fubon (Bank/Card), E.SUN (Card), DBS.
  - 100% accuracy for supported formats.
- **LLM-Based Parser (Priority 2)**:
  - Adaptive parser under `src/parsing/llm/` for unknown formats (OpenAI GPT-4o-mini or local Qwen-3.5).
  - **Intelligent Chunking**: Splits large statements (30+ transactions) into smaller segments to handle context window limits.
  - **JSON Repair**: Stack-based mechanism to fix truncated JSON from LLM outputs.
- **Heuristic Fallback (Priority 3)**: Basic regex extraction if LLM is unavailable.

### 3.4 Data Schema & Normalization
Each transaction record includes:
- `Date` (YYYY-MM-DD)
- `收入` (Populated only when the exported row is classified as income)
- `支出` (Populated only when the exported row is classified as expense)
- `Currency` (TWD, USD, etc.)
- `Description` / `Expense Name`
- `Transaction Type` (Withdrawal, Deposit, Payment, etc.)
- `Source` (Bank/Card name)
- `Source File` (Filename)
- `Confidence` (0.0 to 1.0)

### 3.5 Deduplication & Quality Control
- **Dual-Layer Deduplication**:
  - **File Level**: Skip previously processed PDF MD5s.
  - **Transaction Level**: Deduplicate using a composite key `(Date, 收入, 支出, Currency, Description, Source)`.
- **Validation**: Strict mode (`STRICT_BANK_PARSER`) to ensure high-quality extraction from known formats.

### 3.6 Output & Delivery
- **CSV Export**: Grouped by month (`YYYY-MM_expenses.csv`).
- **Classification Rule**:
  - Credit-card statements: negative signed amounts export to `收入`, positive signed amounts export to `支出`
  - Bank statements: positive signed amounts export to `收入`, negative signed amounts export to `支出`
- **Group Delivery**: (Planned) Automated sync to designated group chat via Webhook.

## 4. Execution Flow

1. **Initialize**: Enter through `main.py`, load `.env`, validate config, and authenticate via `src/runtime/app.py`.
2. **Fetch**: Search Gmail for target monthly statement emails within the date range.
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

Current implementation work targets `main.py`, `src/runtime/`, and the responsibility-based packages under `src/`. Files under `legacy/` are retained for reference and migration history only.

---

**Approval Status**  
Updated to reflect current codebase (March 2026).
