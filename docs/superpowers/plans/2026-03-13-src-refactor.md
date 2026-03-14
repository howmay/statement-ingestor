# Src Refactor Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reorganize the active `src/` tree into clearer responsibility-based packages, remove stale artifacts from active source, and complete a full import-path cutover across code, tests, and active docs.

**Architecture:** Execute the refactor in dependency order so low-risk foundational modules move first and orchestration moves last. The plan preserves behavior by updating imports incrementally, running focused tests after each layer, and removing temporary compatibility only before the final verification pass.

**Tech Stack:** Python, pytest, git, Markdown documentation

---

## Chunk 1: Create The Destination Package Skeleton

### Task 1: Add the new top-level package layout and import surfaces

**Files:**
- Create: `src/core/__init__.py`
- Create: `src/support/__init__.py`
- Create: `src/integrations/__init__.py`
- Create: `src/integrations/gmail/__init__.py`
- Create: `src/parsing/__init__.py`
- Create: `src/parsing/banks/__init__.py`
- Create: `src/parsing/llm/__init__.py`
- Create: `src/parsing/ocr/__init__.py`
- Create: `src/parsing/pdf/__init__.py`
- Create: `src/export/__init__.py`
- Create: `src/runtime/__init__.py`
- Test: `test/test_app.py`

- [ ] **Step 1: Write a failing package-shape test**

Add a small test in `test/test_app.py` or a new focused test module:

```python
def test_new_src_packages_exist():
    import importlib

    for name in [
        "src.core",
        "src.support",
        "src.integrations",
        "src.integrations.gmail",
        "src.parsing",
        "src.parsing.banks",
        "src.parsing.llm",
        "src.parsing.ocr",
        "src.parsing.pdf",
        "src.export",
        "src.runtime",
    ]:
        assert importlib.import_module(name) is not None
```

- [ ] **Step 2: Run the targeted test to verify it fails**

Run: `./venv/bin/pytest test/test_app.py -k new_src_packages_exist -q`
Expected: FAIL because the new packages do not exist yet.

- [ ] **Step 3: Create the destination packages with minimal `__init__.py` files**

Example:

```python
"""Core configuration and shared internal contracts."""
```

- [ ] **Step 4: Run the targeted test to verify it passes**

Run: `./venv/bin/pytest test/test_app.py -k new_src_packages_exist -q`
Expected: PASS

- [ ] **Step 5: Commit the new package skeleton**

```bash
git add src/core src/support src/integrations src/parsing src/export src/runtime test/test_app.py
git commit -m "refactor: add src package skeleton"
```

## Chunk 2: Move Core And Support Modules

### Task 2: Move config and shared support modules into stable foundational packages

**Files:**
- Create: `src/core/config.py`
- Create: `src/support/cache.py`
- Create: `src/support/config_validator.py`
- Create: `src/support/logger.py`
- Create: `src/support/progress.py`
- Create: `src/support/retry.py`
- Create: `src/support/retry_enhanced.py`
- Modify: `src/app.py`
- Modify: `src/auth/gmail_auth.py`
- Modify: `src/fetch/fetch_emails.py`
- Modify: `src/fetch/download_pdfs.py`
- Modify: `src/llm/parse_receipt.py`
- Modify: `src/ocr/hsbc_ocr.py`
- Modify: `test/test_utils_cache.py`
- Modify: `test/test_utils_config_validator.py`
- Modify: `test/test_utils_logger.py`
- Modify: `test/test_utils_progress.py`
- Modify: `test/test_utils_retry.py`
- Modify: `test/test_retry_comprehensive.py`
- Modify: `test/test_retry_enhanced_comprehensive.py`
- Test: `test/test_utils_cache.py`
- Test: `test/test_utils_config_validator.py`
- Test: `test/test_utils_logger.py`
- Test: `test/test_utils_progress.py`
- Test: `test/test_utils_retry.py`

- [ ] **Step 1: Write or update failing tests to import from the target core/support paths**

Example:

```python
from src.core.config import get_bank_password
from src.support.retry import retry_gmail
from src.support.logger import get_logger
```

- [ ] **Step 2: Run the focused support test subset to verify it fails on missing modules**

Run: `./venv/bin/pytest test/test_utils_cache.py test/test_utils_config_validator.py test/test_utils_logger.py test/test_utils_progress.py test/test_utils_retry.py -q`
Expected: FAIL with import errors referencing `src.core` or `src.support`.

- [ ] **Step 3: Move `src/config.py` to `src/core/config.py` and move utility modules to `src/support/`**

Target module mapping:

```text
src/config.py -> src/core/config.py
src/utils/cache.py -> src/support/cache.py
src/utils/config_validator.py -> src/support/config_validator.py
src/utils/logger.py -> src/support/logger.py
src/utils/progress.py -> src/support/progress.py
src/utils/retry.py -> src/support/retry.py
src/utils/retry_enhanced.py -> src/support/retry_enhanced.py
```

- [ ] **Step 4: Update active imports to the new paths**

Representative replacements:

```python
from src.core.config import TARGET_SENDERS, TARGET_KEYWORDS, DOWNLOAD_DIR, get_bank_password
from src.support.retry import retry_gmail, retry_openai
from src.support.config_validator import ConfigValidator
from src.support.cache import ResultCache
```

- [ ] **Step 5: Run the focused support test subset to verify it passes**

Run: `./venv/bin/pytest test/test_utils_cache.py test/test_utils_config_validator.py test/test_utils_logger.py test/test_utils_progress.py test/test_utils_retry.py -q`
Expected: PASS, or pre-existing failures unrelated to the path migration.

- [ ] **Step 6: Search for stale imports from old core/support locations**

Run: `rg -n "src\\.(config|utils)\\." main.py src test docs -S`
Expected: no active-code/test hits outside archived docs or temporary migration shims.

- [ ] **Step 7: Commit the foundational module move**

```bash
git add src/core src/support src/app.py src/auth/gmail_auth.py src/fetch/fetch_emails.py src/fetch/download_pdfs.py src/llm/parse_receipt.py src/ocr/hsbc_ocr.py test
git commit -m "refactor: move config and support modules"
```

## Chunk 3: Move Integrations And Export Modules

### Task 3: Collapse Gmail auth/fetch under integrations and rename output to export

**Files:**
- Create: `src/integrations/gmail/auth.py`
- Create: `src/integrations/gmail/fetch.py`
- Create: `src/integrations/gmail/downloads.py`
- Create: `src/export/csv_writer.py`
- Modify: `main.py`
- Modify: `src/app.py`
- Modify: `test/test_gmail_auth.py`
- Modify: `test/test_gmail_auth_simple.py`
- Modify: `test/test_gmail_auth_comprehensive.py`
- Modify: `test/test_fetch_emails.py`
- Modify: `test/test_fetch_emails_comprehensive.py`
- Modify: `test/test_download_pdfs.py`
- Modify: `test/test_download_pdfs_comprehensive.py`
- Modify: `test/test_download_pdfs_enhanced.py`
- Modify: `test/test_csv_writer.py`
- Modify: `test/test_csv_writer_comprehensive.py`
- Test: `test/test_gmail_auth.py`
- Test: `test/test_fetch_emails.py`
- Test: `test/test_download_pdfs.py`
- Test: `test/test_csv_writer.py`

- [ ] **Step 1: Update a focused test slice to import the new integration/export paths**

Example:

```python
from src.integrations.gmail.auth import get_gmail_service
from src.integrations.gmail.fetch import search_emails
from src.integrations.gmail.downloads import batch_download_pdfs
from src.export.csv_writer import export_receipts_to_csv
```

- [ ] **Step 2: Run the focused integration/export test slice to verify it fails**

Run: `./venv/bin/pytest test/test_gmail_auth.py test/test_fetch_emails.py test/test_download_pdfs.py test/test_csv_writer.py -q`
Expected: FAIL with import errors for the new modules.

- [ ] **Step 3: Move the active modules into their new integration/export locations**

Target mapping:

```text
src/auth/gmail_auth.py -> src/integrations/gmail/auth.py
src/fetch/fetch_emails.py -> src/integrations/gmail/fetch.py
src/fetch/download_pdfs.py -> src/integrations/gmail/downloads.py
src/output/csv_writer.py -> src/export/csv_writer.py
```

- [ ] **Step 4: Update all active imports and patch targets**

Representative replacements:

```python
from src.integrations.gmail.auth import get_gmail_service
from src.integrations.gmail.fetch import search_emails, list_attachments
from src.integrations.gmail.downloads import batch_download_pdfs
from src.export.csv_writer import export_receipts_to_csv, export_extracted_texts_to_csv
```

- [ ] **Step 5: Run the focused integration/export test slice to verify it passes**

Run: `./venv/bin/pytest test/test_gmail_auth.py test/test_fetch_emails.py test/test_download_pdfs.py test/test_csv_writer.py -q`
Expected: PASS, or only known unrelated baseline failures.

- [ ] **Step 6: Search for stale imports from `src.auth`, `src.fetch`, and `src.output`**

Run: `rg -n "src\\.(auth|fetch|output)\\." main.py src test docs -S`
Expected: no active-code/test hits outside archived docs or temporary shims.

- [ ] **Step 7: Commit the integrations/export move**

```bash
git add main.py src/integrations src/export src/app.py test
git commit -m "refactor: move gmail integrations and export modules"
```

## Chunk 4: Move Parsing Modules

### Task 4: Consolidate bank, OCR, PDF, and LLM parsing code under `src/parsing/`

**Files:**
- Create: `src/parsing/banks/base.py`
- Create: `src/parsing/banks/factory.py`
- Create: `src/parsing/banks/hsbc.py`
- Create: `src/parsing/banks/fubon.py`
- Create: `src/parsing/banks/esun.py`
- Create: `src/parsing/banks/dbs.py`
- Create: `src/parsing/llm/chunking.py`
- Create: `src/parsing/llm/json_repair.py`
- Create: `src/parsing/llm/parse_receipt.py`
- Create: `src/parsing/ocr/hsbc_ocr.py`
- Create: `src/parsing/pdf/pdf_to_text.py`
- Modify: `src/app.py`
- Modify: `test/test_bank_parsers.py`
- Modify: `test/test_bank_parsers_comprehensive.py`
- Modify: `test/test_chunking.py`
- Modify: `test/test_llm_chunking_unit.py`
- Modify: `test/test_llm_json_repair_unit.py`
- Modify: `test/test_parse_receipt_helpers_unit.py`
- Modify: `test/test_parse_receipt_comprehensive.py`
- Modify: `test/test_multiple_transactions.py`
- Modify: `test/test_issue_24_large_transactions.py`
- Modify: `test/test_issue_24_comprehensive.py`
- Modify: `test/test_pdf_to_text.py`
- Modify: `test/test_pdf_to_text_comprehensive.py`
- Modify: `test/test_pdf_to_text_edge_cases.py`
- Modify: `test/test_ocr.py`
- Modify: `test/test_ocr_comprehensive.py`
- Test: `test/test_bank_parsers.py`
- Test: `test/test_chunking.py`
- Test: `test/test_pdf_to_text.py`
- Test: `test/test_ocr.py`

- [ ] **Step 1: Update parsing tests to use the new package layout**

Example:

```python
from src.parsing.banks.factory import parse_with_bank_factory
from src.parsing.llm.parse_receipt import parse_receipt_text
from src.parsing.pdf.pdf_to_text import extract_text_from_pdf
from src.parsing.ocr.hsbc_ocr import enrich_hsbc_transactions_with_ocr
```

- [ ] **Step 2: Run the focused parsing test slice to verify it fails**

Run: `./venv/bin/pytest test/test_bank_parsers.py test/test_chunking.py test/test_pdf_to_text.py test/test_ocr.py -q`
Expected: FAIL on missing parsing modules.

- [ ] **Step 3: Move parsing modules into the new subpackages**

Target mapping:

```text
src/bank_parsers/*.py -> src/parsing/banks/*.py
src/llm/chunking.py -> src/parsing/llm/chunking.py
src/llm/json_repair.py -> src/parsing/llm/json_repair.py
src/llm/parse_receipt.py -> src/parsing/llm/parse_receipt.py
src/ocr/hsbc_ocr.py -> src/parsing/ocr/hsbc_ocr.py
src/pdf/pdf_to_text.py -> src/parsing/pdf/pdf_to_text.py
```

- [ ] **Step 4: Delete stale parsing artifacts from active `src/`**

Remove:

```text
src/llm/parse_receipt.py.backup
tracked src/**/__pycache__ entries
```

- [ ] **Step 5: Update imports and patch targets throughout active code/tests**

Representative replacements:

```python
from src.parsing.banks.factory import parse_with_bank_factory
from src.parsing.llm.parse_receipt import parse_receipt_text, parse_multiple_receipts, ReceiptParsingError
from src.parsing.llm.chunking import chunk_transactions
from src.parsing.pdf.pdf_to_text import extract_text_from_pdf
from src.parsing.ocr.hsbc_ocr import enrich_hsbc_transactions_with_ocr
```

- [ ] **Step 6: Run the focused parsing test slice to verify it passes**

Run: `./venv/bin/pytest test/test_bank_parsers.py test/test_chunking.py test/test_pdf_to_text.py test/test_ocr.py -q`
Expected: PASS, or only known unrelated baseline failures.

- [ ] **Step 7: Search for stale imports from old parsing package names**

Run: `rg -n "src\\.(bank_parsers|llm|ocr|pdf)\\." main.py src test docs -S`
Expected: no active-code/test hits outside archived docs or temporary shims.

- [ ] **Step 8: Commit the parsing move**

```bash
git add src/parsing src/app.py test
git commit -m "refactor: move parsing modules into src.parsing"
```

## Chunk 5: Move Runtime Orchestration And Finalize Active Paths

### Task 5: Move the application orchestrator into `src/runtime/` and cut over the entry point

**Files:**
- Create: `src/runtime/app.py`
- Modify: `main.py`
- Modify: `test/test_app.py`
- Modify: `test/test_app_comprehensive.py`
- Modify: `test/test_integration.py`
- Modify: `docs/DEVELOPER_GUIDE.md`
- Modify: `docs/TRD_v1.md`
- Test: `test/test_app.py`
- Test: `test/test_app_comprehensive.py`
- Test: `test/test_integration.py`

- [ ] **Step 1: Update app-focused tests to use the new runtime path**

Example:

```python
from src.runtime.app import GmailExpenseParserApp
```

Update patch targets similarly:

```python
patch("src.runtime.app.get_gmail_service")
```

- [ ] **Step 2: Run the runtime-focused tests to verify they fail**

Run: `./venv/bin/pytest test/test_app.py test/test_app_comprehensive.py test/test_integration.py -q`
Expected: FAIL on missing `src.runtime.app`.

- [ ] **Step 3: Move `src/app.py` to `src/runtime/app.py` and update the entry point**

Representative change in `main.py`:

```python
from src.runtime.app import GmailExpenseParserApp
```

- [ ] **Step 4: Update active docs to describe the new package structure**

At minimum update:

```text
docs/DEVELOPER_GUIDE.md
docs/TRD_v1.md
```

Document the new active path, replacing older references like `src/app.py` and `src/utils/*`.

- [ ] **Step 5: Run the runtime-focused tests to verify they pass**

Run: `./venv/bin/pytest test/test_app.py test/test_app_comprehensive.py test/test_integration.py -q`
Expected: PASS, or only known unrelated baseline failures.

- [ ] **Step 6: Search for stale imports from `src.app`**

Run: `rg -n "src\\.app|from src\\.app import|patch\\('src\\.app" main.py src test docs -S`
Expected: no active-code/test hits outside archived docs.

- [ ] **Step 7: Commit the runtime move**

```bash
git add main.py src/runtime docs/DEVELOPER_GUIDE.md docs/TRD_v1.md test
git commit -m "refactor: move application runtime into src.runtime"
```

## Chunk 6: Remove Temporary Shims And Run Final Verification

### Task 6: Ensure only final paths remain and verify the refactor end-to-end

**Files:**
- Modify: `.gitignore`
- Modify: `docs/README.md`
- Test: `test/test_app.py`
- Test: `test/test_gmail_auth.py`
- Test: `test/test_fetch_emails.py`
- Test: `test/test_download_pdfs.py`
- Test: `test/test_csv_writer.py`
- Test: `test/test_bank_parsers.py`
- Test: `test/test_pdf_to_text.py`
- Test: `test/test_utils_retry.py`

- [ ] **Step 1: Remove any temporary compatibility shims introduced during the migration**

Delete any transitional modules that preserve old package paths once all imports are updated.

- [ ] **Step 2: Remove tracked generated source artifacts if any remain**

Run: `git ls-files src | rg "__pycache__|\\.pyc$|\\.backup$"`
Expected: no output

- [ ] **Step 3: Run a broad active-code verification slice**

Run: `./venv/bin/pytest test/test_app.py test/test_app_comprehensive.py test/test_gmail_auth.py test/test_fetch_emails.py test/test_download_pdfs.py test/test_csv_writer.py test/test_bank_parsers.py test/test_pdf_to_text.py test/test_utils_retry.py -q`
Expected: PASS, or only known unrelated baseline failures already documented.

- [ ] **Step 4: Run stale-import searches across active code**

Run: `rg -n "src\\.(app|auth|fetch|bank_parsers|llm|ocr|pdf|output|utils|config)\\." main.py src test docs -S`
Expected: no active-code/test hits; archive docs may still mention historical paths.

- [ ] **Step 5: Run the full suite and record actual status**

Run: `./venv/bin/pytest -q`
Expected: PASS, or the same pre-existing retry import failures if still unresolved before this refactor starts. Any new failure is a regression to fix before completion.

- [ ] **Step 6: Commit the final cleanup**

```bash
git add .gitignore docs main.py src test
git commit -m "refactor: finalize src package reorganization"
```
