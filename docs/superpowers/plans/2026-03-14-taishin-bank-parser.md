# Taishin Bank Parser Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add deterministic parsing for Taishin bank-account statements from the provided combined statement PDF.

**Architecture:** Add a dedicated `TaishinBankParser` that parses the TWD and foreign-currency account detail sections from the combined statement. Route Taishin sources in the parser factory to either the existing credit-card parser or the new bank parser based on source hints, then verify against deterministic fixtures and the encrypted sample PDF.

**Tech Stack:** Python, pytest, existing deterministic bank parser framework

---

## Chunk 1: Tests First

### Task 1: Add deterministic Taishin bank parser test

**Files:**
- Modify: `test/test_bank_parsers.py`

- [ ] Step 1: Write a failing test covering TWD + FX Taishin account rows
- [ ] Step 2: Run `venv/bin/pytest -q test/test_bank_parsers.py -k taishin_bank_statement` and verify it fails because parser support is missing

### Task 2: Add encrypted sample PDF regression test

**Files:**
- Modify: `test/test_bank_pdf_samples.py`

- [ ] Step 1: Write a failing test that decrypts `downloads/台新銀行_NhuIh4k=.pdf` and asserts parsed transaction details
- [ ] Step 2: Run `venv/bin/pytest -q test/test_bank_pdf_samples.py -k taishin_bank_sample_pdf` and verify it fails before implementation

## Chunk 2: Minimal Implementation

### Task 3: Implement Taishin bank parser

**Files:**
- Create: `src/parsing/banks/taishin.py`
- Modify: `src/parsing/banks/factory.py`

- [ ] Step 1: Parse the TWD and FX detail sections only
- [ ] Step 2: Support wrapped note lines and attach them to the transaction description
- [ ] Step 3: Populate `cashflow_side` from debit/credit columns and preserve FX currencies
- [ ] Step 4: Route Taishin non-credit-card statements to the new parser

## Chunk 3: Verification

### Task 4: Run focused verification

**Files:**
- Verify: `test/test_bank_parsers.py`
- Verify: `test/test_bank_pdf_samples.py`

- [ ] Step 1: Run `venv/bin/pytest -q test/test_bank_parsers.py -k "taishin"` and confirm green
- [ ] Step 2: Run `venv/bin/pytest -q test/test_bank_pdf_samples.py -k "taishin_bank_sample_pdf"` and confirm green
- [ ] Step 3: Run `venv/bin/pytest -q test/test_bank_parsers.py -k "taishin or fubon"` to check nearby regressions
