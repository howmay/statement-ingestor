# Statement-Only Gmail Search Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restrict Gmail fetching to monthly bank statements and credit-card statements so the pipeline stops ingesting merchant receipts and reduces duplicate financial records.

**Architecture:** Replace the single global sender+keyword Gmail query with explicit statement search profiles. Each profile describes one class of monthly statement emails using sender constraints, subject keywords, attachment requirements, and optional exclusions. The Gmail fetch layer will build an OR query across profiles, while runtime/config validation will treat statement profiles as the primary search contract.

**Tech Stack:** Python, Gmail API query syntax, pytest, dotenv-based config

---

## Chunk 1: Search Profile Model and Config Loading

### Task 1: Define statement search profile contract

**Files:**
- Modify: `src/core/config.py`
- Test: `test/test_config_edge_cases.py`
- Test: `test/test_utils_config_validator.py`

- [ ] **Step 1: Write the failing config tests**

Add tests that prove config can load statement-only search profiles from environment, for example:

```python
def test_statement_search_profiles_from_json_env():
    with patch.dict(os.environ, {
        "STATEMENT_SEARCH_PROFILES": json.dumps([
            {
                "name": "fubon-bank",
                "senders": ["service@bhu.taipeifubon.com.tw"],
                "subject_keywords": ["對帳單", "電子對帳單"],
                "exclude_keywords": ["otp", "驗證"],
                "has_pdf_attachment": True,
            }
        ])
    }, clear=False):
        config_module = reload_config_module()
        assert len(config_module.STATEMENT_SEARCH_PROFILES) == 1
        assert config_module.STATEMENT_SEARCH_PROFILES[0]["name"] == "fubon-bank"
```

Also add a fallback test showing invalid/missing profile env does not crash import and produces a safe default.

- [ ] **Step 2: Run tests to verify they fail**

Run: `./venv/bin/pytest test/test_config_edge_cases.py test/test_utils_config_validator.py -q`
Expected: FAIL because `STATEMENT_SEARCH_PROFILES` is not defined or validated yet.

- [ ] **Step 3: Add minimal config loading**

In `src/core/config.py`:
- Add a new env var, `STATEMENT_SEARCH_PROFILES`
- Parse it as JSON array of dicts
- Normalize each profile into a predictable structure:
  - `name: str`
  - `senders: list[str]`
  - `subject_keywords: list[str]`
  - `exclude_keywords: list[str]`
  - `has_pdf_attachment: bool`
- Provide a built-in default statement-only profile set for currently supported banks/cards when env is unset
- Keep `TARGET_SENDERS` and `TARGET_KEYWORDS` for backward compatibility, but stop treating them as the primary statement search mechanism

- [ ] **Step 4: Run tests to verify they pass**

Run: `./venv/bin/pytest test/test_config_edge_cases.py test/test_utils_config_validator.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/core/config.py test/test_config_edge_cases.py test/test_utils_config_validator.py
git commit -m "feat: add statement search profile config"
```


### Task 2: Validate the new profile configuration

**Files:**
- Modify: `src/support/config_validator.py`
- Test: `test/test_utils_config_validator.py`

- [ ] **Step 1: Write the failing validator tests**

Add tests covering:
- valid JSON list of statement profiles passes
- malformed JSON fails
- missing `senders` or `subject_keywords` fails
- empty profile arrays are rejected unless a built-in default will be used

Example:

```python
def test_statement_search_profiles_validator_rejects_missing_senders():
    value = '[{"name":"hsbc","subject_keywords":["帳單"]}]'
    ok, message = validate_env_var("STATEMENT_SEARCH_PROFILES", value, RULE)
    assert ok is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./venv/bin/pytest test/test_utils_config_validator.py -q`
Expected: FAIL because validator rules do not know this env var.

- [ ] **Step 3: Implement validator support**

In `src/support/config_validator.py`:
- Register `STATEMENT_SEARCH_PROFILES` in the rule set
- Add validation logic for JSON structure and required fields
- Keep error messages concrete so users know which profile entry is malformed

- [ ] **Step 4: Run tests to verify they pass**

Run: `./venv/bin/pytest test/test_utils_config_validator.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/support/config_validator.py test/test_utils_config_validator.py
git commit -m "test: validate statement search profile config"
```

## Chunk 2: Gmail Query Builder Rewrite

### Task 3: Build profile-based Gmail queries

**Files:**
- Modify: `src/integrations/gmail/fetch.py`
- Test: `test/test_fetch_emails.py`
- Test: `test/test_fetch_emails_comprehensive.py`

- [ ] **Step 1: Write the failing query-builder tests**

Replace or extend current query expectations so they assert profile-based behavior, for example:

```python
def test_build_gmail_query_from_statement_profiles():
    profiles = [
        {
            "name": "fubon-bank",
            "senders": ["service@bhu.taipeifubon.com.tw"],
            "subject_keywords": ["對帳單", "電子對帳單"],
            "exclude_keywords": ["otp", "驗證"],
            "has_pdf_attachment": True,
        },
        {
            "name": "hsbc-card",
            "senders": ["cards@estatements.hsbc.com.tw"],
            "subject_keywords": ["信用卡帳單", "eStatement"],
            "exclude_keywords": [],
            "has_pdf_attachment": True,
        },
    ]
    q = build_gmail_query(statement_profiles=profiles, date_from="2026-03-01", date_to="2026-03-31")
    assert 'from:"service@bhu.taipeifubon.com.tw"' in q
    assert 'from:"cards@estatements.hsbc.com.tw"' in q
    assert 'filename:pdf' in q
    assert 'before:2026/04/01' in q
```

Also add tests for:
- profile-level exclusions (`-OTP`, `-驗證`, etc.)
- OR composition across multiple profiles
- subject-only keyword grouping instead of broad body keywords
- zero profiles fallback behavior

- [ ] **Step 2: Run tests to verify they fail**

Run: `./venv/bin/pytest test/test_fetch_emails.py test/test_fetch_emails_comprehensive.py -q`
Expected: FAIL because `build_gmail_query` still only accepts senders+keywords.

- [ ] **Step 3: Implement profile-based query generation**

In `src/integrations/gmail/fetch.py`:
- Add helper(s) such as:
  - `_build_profile_query(profile)`
  - `_quote_gmail_term(term)`
- Update `build_gmail_query(...)` to prefer `statement_profiles`
- Build one Gmail subquery per profile:
  - sender OR group
  - subject keyword OR group
  - optional exclusion terms
  - `has:attachment filename:pdf` when requested
- Combine profile subqueries using top-level OR
- Preserve date range logic at the top level

Keep implementation DRY and avoid mixing legacy keyword search branches into the new main path.

- [ ] **Step 4: Run tests to verify they pass**

Run: `./venv/bin/pytest test/test_fetch_emails.py test/test_fetch_emails_comprehensive.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/integrations/gmail/fetch.py test/test_fetch_emails.py test/test_fetch_emails_comprehensive.py
git commit -m "feat: build gmail queries from statement profiles"
```


### Task 4: Switch email search to statement profiles by default

**Files:**
- Modify: `src/integrations/gmail/fetch.py`
- Modify: `src/runtime/app.py`
- Test: `test/test_app.py`
- Test: `test/test_e2e_workflow.py`

- [ ] **Step 1: Write the failing behavior tests**

Add tests that prove:
- `search_emails()` uses `STATEMENT_SEARCH_PROFILES` by default
- runtime logging reports statement-profile search rather than generic sender/keyword search
- `GmailExpenseParserApp.fetch_emails()` still passes date ranges correctly

Example:

```python
def test_search_emails_uses_statement_profiles_by_default(mock_service):
    with patch("src.integrations.gmail.fetch.STATEMENT_SEARCH_PROFILES", [...]):
        search_emails(mock_service, max_results=10)
        mock_service.users().messages().list.assert_called_once()
        assert "filename:pdf" in mock_service.users().messages().list.call_args.kwargs["q"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./venv/bin/pytest test/test_app.py test/test_e2e_workflow.py test/test_fetch_emails.py -q`
Expected: FAIL because search still defaults to `TARGET_SENDERS` and `TARGET_KEYWORDS`.

- [ ] **Step 3: Implement default statement-only search path**

In `src/integrations/gmail/fetch.py`:
- import `STATEMENT_SEARCH_PROFILES`
- make `search_emails()` prefer profiles when callers do not explicitly pass a custom query/profile list
- keep a narrow legacy fallback only if no statement profiles are configured

In `src/runtime/app.py`:
- adjust logging text to describe statement-only search
- avoid implying merchant receipt coverage anywhere in the fetch step

- [ ] **Step 4: Run tests to verify they pass**

Run: `./venv/bin/pytest test/test_app.py test/test_e2e_workflow.py test/test_fetch_emails.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/integrations/gmail/fetch.py src/runtime/app.py test/test_app.py test/test_e2e_workflow.py test/test_fetch_emails.py
git commit -m "feat: default gmail search to statement-only profiles"
```

## Chunk 3: Documentation and Migration Safety

### Task 5: Document statement-only search configuration

**Files:**
- Modify: `README.md`
- Modify: `docs/PRD.md`
- Modify: `docs/TRD_v1.md`

- [ ] **Step 1: Write the doc updates**

Update user-facing docs so they explicitly say:
- the system now targets monthly bank/credit-card statements, not merchant receipts
- `STATEMENT_SEARCH_PROFILES` is the preferred search configuration
- provide a minimal env example showing one or two profiles
- explain why this reduces duplicate counting

Include a concrete config example like:

```env
STATEMENT_SEARCH_PROFILES=[
  {"name":"fubon-bank","senders":["service@bhu.taipeifubon.com.tw"],"subject_keywords":["對帳單","電子對帳單"],"exclude_keywords":["OTP","驗證"],"has_pdf_attachment":true},
  {"name":"hsbc-card","senders":["cards@estatements.hsbc.com.tw"],"subject_keywords":["信用卡帳單","eStatement"],"exclude_keywords":[],"has_pdf_attachment":true}
]
```

- [ ] **Step 2: Verify docs are consistent**

Run: `rg -n "receipt|invoice|TARGET_SENDERS|TARGET_KEYWORDS" README.md docs/PRD.md docs/TRD_v1.md`
Expected: remaining mentions are either historical context or clearly marked legacy/fallback.

- [ ] **Step 3: Commit**

```bash
git add README.md docs/PRD.md docs/TRD_v1.md
git commit -m "docs: describe statement-only gmail search"
```


### Task 6: Full verification and cleanup

**Files:**
- Verify only

- [ ] **Step 1: Run focused test suites**

Run:

```bash
./venv/bin/pytest test/test_fetch_emails.py test/test_fetch_emails_comprehensive.py test/test_app.py test/test_e2e_workflow.py test/test_utils_config_validator.py test/test_config_edge_cases.py -q
```

Expected: PASS

- [ ] **Step 2: Run a broader regression slice**

Run:

```bash
./venv/bin/pytest test/test_csv_writer.py test/test_csv_writer_comprehensive.py test/test_bank_parsers.py test/test_bank_pdf_samples.py test/test_app.py test/test_fetch_emails.py test/test_fetch_emails_comprehensive.py -q
```

Expected: PASS

- [ ] **Step 3: Smoke-check the final query**

Run:

```bash
./venv/bin/python - <<'PY'
from src.integrations.gmail.fetch import build_gmail_query
from src.core.config import STATEMENT_SEARCH_PROFILES
print(build_gmail_query(statement_profiles=STATEMENT_SEARCH_PROFILES, date_from="2026-03-01", date_to="2026-03-31"))
PY
```

Expected: prints one OR-composed Gmail query targeting statement senders, statement subject keywords, and PDF attachments.

- [ ] **Step 4: Final commit**

```bash
git status --short
git add -A
git commit -m "feat: narrow gmail fetch to monthly statements"
```

