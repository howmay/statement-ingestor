# Developer Guide - Gmail Expense Parser (AI Agents)

## Project Overview
This tool automates extraction of financial transactions from Gmail. It uses a **Research -> Strategy -> Execution** lifecycle, where Execution follows a strict **TDD (Test-Driven Development)** cycle.

## Supported Runtime Path
The supported execution path is:

`main.py` -> `src/runtime/app.py` -> active modules under `src/`

`legacy/` is reference-only and should not receive feature work.

## Core Mandate: TDD for All Agents
As an AI agent, you **MUST** follow the TDD skill for every code change.

### 1. The Red-Green-Refactor Cycle
1.  **RED**: Write a failing test in `test/` that reproduces the bug or defines the new feature.
2.  **Verify RED**: Run `pytest` and confirm the test fails with the expected error. **DO NOT** skip this.
3.  **GREEN**: Write the *minimal* production code in `src/` to make the test pass.
4.  **Verify GREEN**: Run `pytest` again to confirm all tests pass.
5.  **REFACTOR**: Clean up the code while keeping tests green.

### 2. No Production Code Without a Failing Test
If you write production code before a test, you must delete it and start over.

---

## Architecture for Agents

### 1. Gmail Fetching (`src/integrations/gmail/`)
- Uses Gmail API to search and download attachments.
- **TDD Tip**: Mock `googleapiclient` or use sample base64 email data in tests.

### 2. PDF Extraction (`src/parsing/pdf/`)
- Multi-engine fallback: `pypdfium2` -> `pdftotext` -> `pdfplumber`.
- **TDD Tip**: Place small sample PDFs in `test/data/` (or use `test_dummy.pdf`) to verify text extraction logic.

### 3. Bank Parsers (`src/parsing/banks/`)
- **Deterministic Parsers**: Regex-based classes in `src/parsing/banks/` (e.g., `hsbc.py`, `fubon.py`).
- **Base Class**: `BaseBankParser` provides utilities for date normalization and transaction building.
- **Factory**: `ParserFactory` matches text patterns to the correct parser.

### 4. LLM Parser (`src/parsing/llm/`)
- Used for unknown formats or as a fallback.
- Features: Intelligent chunking and JSON repair.

---

## Implementation Workflow: Adding a New Bank

When asked to "Add support for Bank X":

1.  **Brainstorm**: Analyze the bank statement format (use `grep` or `read_file` on sample text).
2.  **RED (Test)**:
    - Create `test/test_bank_bankx.py`.
    - Define a test case with a sample snippet of the bank's text.
    - Assert that `BankXParser(text).parse()` returns the expected transactions.
3.  **Verify RED**: Run `pytest test/test_bank_bankx.py`. It should fail (ImportError or NotImplementedError).
4.  **GREEN (Code)**:
    - Create `src/parsing/banks/bankx.py` inheriting from `BaseBankParser`.
    - Implement the `parse()` method using Regex.
5.  **Verify GREEN**: Run the test again.
6.  **Integrate**: Register the parser in `src/parsing/banks/factory.py` (requires its own TDD cycle if logic is complex).

---

## Testing Standards
- **File Naming**: `test/test_<module>_<feature>.py`.
- **Coverage**: Aim for 100% logic coverage in parsers.
- **Tools**:
    - `python -m pytest`: Run all tests.
    - `python -m pytest <path_to_test>`: Run specific test (faster).
    - `python -m pytest --cov=src`: Check coverage.

## Prohibited Actions
- **No Manual Testing Only**: "I tested it manually" is not a valid completion state.
- **No Skip TDD**: Do not rationalize skipping tests for "simple" fixes.
- **No Mocking Everything**: Prefer testing real parsing logic with real text snippets.

---
*Last Updated: 2026-03-13*
