# Income And Expense Columns Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the exported single signed `amount` column with separate `收入` and `支出` columns while preserving internal signed amounts and applying source-specific classification rules for credit-card and bank statements.

**Architecture:** Keep parser and runtime internals on the current signed `amount` schema to minimize migration risk. Introduce a focused export-layer classification helper that maps each transaction into exactly one of `收入` or `支出` based on source type and sign. Update CSV schema, documentation, and tests around this export contract without introducing a third transfer/offset field.

**Tech Stack:** Python, pytest, CSV export, existing bank parser/runtime pipeline, Markdown docs

---

## Chunk 1: Lock The Export Contract With Tests

### Task 1: Add failing tests for the new CSV column schema

**Files:**
- Modify: `test/test_csv_writer.py`
- Modify: `test/test_csv_writer_comprehensive.py`
- Test: `test/test_csv_writer.py`
- Test: `test/test_csv_writer_comprehensive.py`

- [ ] **Step 1: Write a failing focused schema test in `test/test_csv_writer.py`**

Add a test that asserts exported rows contain `收入` and `支出` columns and no longer expose `amount` in the CSV header:

```python
def test_export_receipts_uses_income_and_expense_columns(tmp_path):
    receipts = [{
        "date": "2026-03-01",
        "amount": 100.0,
        "currency": "TWD",
        "expense_name": "Store",
        "expense_type": "Shopping",
        "source": "Fubon Credit Card",
        "source_file": "card.pdf",
    }]

    path = export_receipts_to_csv(receipts, output_dir=str(tmp_path))

    with open(path.split(",")[0], "r", encoding="utf-8-sig") as f:
        header = f.readline().strip()

    assert "收入" in header
    assert "支出" in header
    assert "amount" not in header
```

- [ ] **Step 2: Write failing rule tests for credit-card and bank sign handling**

Add one test per rule in `test/test_csv_writer.py`:

```python
def test_credit_card_positive_amount_exports_to_expense(tmp_path):
    ...
    assert row["收入"] == ""
    assert row["支出"] == "100.00"


def test_credit_card_negative_amount_exports_to_income(tmp_path):
    ...
    assert row["收入"] == "11.00"
    assert row["支出"] == ""


def test_bank_positive_amount_exports_to_income(tmp_path):
    ...
    assert row["收入"] == "2500.00"
    assert row["支出"] == ""


def test_bank_negative_amount_exports_to_expense(tmp_path):
    ...
    assert row["收入"] == ""
    assert row["支出"] == "2500.00"
```

Use representative `source` values already present in the codebase, such as:
- `Fubon Credit Card`
- `Sinopac Credit Card`
- `Fubon Bank`
- `First Bank Credit Card` only for credit-card coverage, not bank-statement rule coverage

- [ ] **Step 3: Write a failing exclusivity test**

Add a test that asserts one row never has both populated:

```python
def test_export_row_never_populates_income_and_expense_together():
    row = _format_export_row({...})
    assert not (row["income"] and row["expense"])
```

Adjust key names to match the actual internal/export representation you choose.

- [ ] **Step 4: Write a failing dedupe compatibility test in `test/test_csv_writer_comprehensive.py`**

Add coverage that exporting the same logical row twice still de-duplicates even after `amount` is replaced in the CSV file by `收入`/`支出`:

```python
def test_export_receipts_dedupes_with_income_expense_columns(tmp_path):
    receipts = [...]
    export_receipts_to_csv(receipts, output_dir=str(tmp_path))
    export_receipts_to_csv(receipts, output_dir=str(tmp_path))
    ...
    assert len(rows) == 1
```

- [ ] **Step 5: Run the CSV writer tests to verify they fail**

Run: `/home/zh/Documents/gmail-expense-parser/venv/bin/pytest test/test_csv_writer.py test/test_csv_writer_comprehensive.py -q`
Expected: FAIL because export code still writes `amount` and has no `收入`/`支出` logic.

- [ ] **Step 6: Commit the failing tests**

```bash
git add test/test_csv_writer.py test/test_csv_writer_comprehensive.py
git commit -m "test: define income and expense csv columns"
```

## Chunk 2: Implement Export-Layer Classification

### Task 2: Add a focused helper that classifies signed amounts into `收入` or `支出`

**Files:**
- Modify: `src/export/csv_writer.py`
- Test: `test/test_csv_writer.py`

- [ ] **Step 1: Add source-type detection helpers in `src/export/csv_writer.py`**

Introduce small helpers near the top of the file:

```python
def _detect_statement_kind(receipt: Dict[str, Any]) -> str:
    source = str(receipt.get("source") or "").lower()
    sender_tag = str(receipt.get("sender_tag") or "").lower()
    source_file = str(receipt.get("source_file") or "").lower()
    hint = " ".join([source, sender_tag, source_file])

    if any(token in hint for token in ["credit card", "信用卡", "card", "hsbc", "sinopac", "first bank credit"]):
        return "credit_card"
    if any(token in hint for token in ["bank", "銀行", "存款", "對帳單"]):
        return "bank"
    return "unknown"
```

Keep this intentionally narrow and based on values already present in current receipts; do not introduce parser rewrites here.

- [ ] **Step 2: Add the amount-splitting helper**

Add a pure helper:

```python
def _split_income_and_expense(receipt: Dict[str, Any]) -> tuple[str, str]:
    amount = receipt.get("amount")
    if amount is None:
        return "", ""

    value = float(amount)
    if value == 0:
        return "", ""

    kind = _detect_statement_kind(receipt)

    if kind == "credit_card":
        if value < 0:
            return f"{abs(value):.2f}", ""
        return "", f"{abs(value):.2f}"

    if kind == "bank":
        if value > 0:
            return f"{abs(value):.2f}", ""
        return "", f"{abs(value):.2f}"

    return "", ""
```

This plan intentionally does **not** add a third transfer/offset classification.

- [ ] **Step 3: Replace the export schema**

Update `CSV_COLUMNS` from:

```python
("amount", "金額")
```

to:

```python
("income", "收入")
("expense", "支出")
```

Use ASCII internal keys and Chinese display labels as the file already does for display labels.

- [ ] **Step 4: Update `_format_export_row()`**

Change row formatting so:
- it no longer writes `amount`
- it populates `income` and `expense` from `_split_income_and_expense(receipt)`
- all other fields still serialize as before

Representative shape:

```python
income, expense = _split_income_and_expense(receipt)
...
elif key == "income":
    row[key] = income
elif key == "expense":
    row[key] = expense
```

- [ ] **Step 5: Update de-duplication keys to use the new exported columns**

In `_receipt_key()` and the CSV existing-row key comparison, replace the old `amount` key element with `(income, expense)` or their row equivalents so reruns stay stable:

```python
return (
    ...,
    income_str,
    expense_str,
    ...
)
```

- [ ] **Step 6: Run the focused CSV writer tests to verify they pass**

Run: `/home/zh/Documents/gmail-expense-parser/venv/bin/pytest test/test_csv_writer.py test/test_csv_writer_comprehensive.py -q`
Expected: PASS

- [ ] **Step 7: Commit the export-layer implementation**

```bash
git add src/export/csv_writer.py test/test_csv_writer.py test/test_csv_writer_comprehensive.py
git commit -m "feat: split exported amount into income and expense columns"
```

## Chunk 3: Verify Representative Source Rules End-To-End

### Task 3: Add app/export integration tests proving the rule works with real source types

**Files:**
- Modify: `test/test_app.py`
- Modify: `test/test_bank_pdf_samples.py`
- Test: `test/test_app.py`
- Test: `test/test_bank_pdf_samples.py`

- [ ] **Step 1: Add a failing app-level export test for credit-card rows**

In `test/test_app.py`, add a focused test where `parsed_receipts` includes a credit-card transaction and `export_results()` writes a CSV row with `支出` populated:

```python
def test_export_results_writes_credit_card_expense_columns(app, tmp_path):
    ...
```

Prefer using `export_receipts_to_csv()` directly if that gives clearer coverage than mocking through `app.export_results()`.

- [ ] **Step 2: Add a failing sample-PDF export classification test**

In `test/test_bank_pdf_samples.py`, after parsing one representative credit-card sample and one representative bank sample, feed the transactions to `_format_export_row()` or `export_receipts_to_csv()` and assert:
- Sinopac negative reward maps to `收入`
- Sinopac positive spend maps to `支出`
- Fubon bank positive inflow maps to `收入`
- Fubon bank negative debit/refund maps to `支出` where representative data exists

Keep this focused on classification; do not over-expand the sample PDF suite.

- [ ] **Step 3: Run the focused integration tests to verify they fail**

Run: `/home/zh/Documents/gmail-expense-parser/venv/bin/pytest test/test_app.py test/test_bank_pdf_samples.py -q`
Expected: FAIL until export classification is wired correctly.

- [ ] **Step 4: Implement minimal fixes if any source-kind heuristics are still insufficient**

Tighten only the helper heuristics in `src/export/csv_writer.py`. Do **not** push this concern down into each parser unless a missing source hint makes export impossible.

- [ ] **Step 5: Run the focused integration tests to verify they pass**

Run: `/home/zh/Documents/gmail-expense-parser/venv/bin/pytest test/test_app.py test/test_bank_pdf_samples.py -q`
Expected: PASS

- [ ] **Step 6: Commit the representative-rule coverage**

```bash
git add test/test_app.py test/test_bank_pdf_samples.py src/export/csv_writer.py
git commit -m "test: cover income and expense export rules"
```

## Chunk 4: Update Active Docs And Final Verification

### Task 4: Document the new CSV contract and verify active slices

**Files:**
- Modify: `docs/PRD.md`
- Modify: `docs/TRD_v1.md`
- Modify: `docs/README.md`
- Test: `test/test_csv_writer.py`
- Test: `test/test_app.py`
- Test: `test/test_bank_parsers.py`

- [ ] **Step 1: Update active documentation to describe `收入` and `支出`**

At minimum update these sections:
- `docs/PRD.md`: exported CSV field list and any FAQ text about income/expense classification
- `docs/TRD_v1.md`: data schema section and execution/export notes
- `docs/README.md`: if it mentions CSV output shape, align it

Replace statements like:

```text
Amount：金額
Category：類別（收入/支出）
```

with the new explicit export shape:

```text
收入：該筆若為收入則填值，否則留空
支出：該筆若為支出則填值，否則留空
```

Document the sign rules:
- 信用卡：負數視為收入，正數視為支出
- 銀行：正數視為收入，負數視為支出

- [ ] **Step 2: Run a verification slice across export and parser flows**

Run: `/home/zh/Documents/gmail-expense-parser/venv/bin/pytest test/test_csv_writer.py test/test_csv_writer_comprehensive.py test/test_app.py test/test_bank_parsers.py test/test_bank_pdf_samples.py -q`
Expected: PASS

- [ ] **Step 3: Search active docs/code for stale `amount`-as-export-column assumptions**

Run: `rg -n "Amount：|Amount\\b|\\bamount\\b.*CSV|Category.*收入|類別（收入/支出）" src test docs/README.md docs/PRD.md docs/TRD_v1.md -S`
Expected: no active-doc references claiming the CSV exports a single `amount` column or a separate income/expense category field.

- [ ] **Step 4: Run the broad app/export slice**

Run: `/home/zh/Documents/gmail-expense-parser/venv/bin/pytest test/test_app.py test/test_app_comprehensive.py test/test_csv_writer.py test/test_csv_writer_comprehensive.py test/test_bank_parsers.py test/test_bank_pdf_samples.py test/test_pdf_to_text.py -q`
Expected: PASS

- [ ] **Step 5: Commit docs and final verification changes**

```bash
git add docs/PRD.md docs/TRD_v1.md docs/README.md test src/export/csv_writer.py
git commit -m "docs: describe income and expense export columns"
```

