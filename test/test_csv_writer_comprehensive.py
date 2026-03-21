import csv
from pathlib import Path
from unittest.mock import patch

import pytest

import src.export.csv_writer as cw


def test_transaction_month_and_receipt_key_helpers():
    assert cw._transaction_month({"date": "2026-03-12"}) == "2026-03"
    assert cw._transaction_month({"date": "2026/03/12"}) == "2026-03"
    assert cw._transaction_month({"date": "bad"}) == "unknown"

    key = cw._receipt_key({
        "date": "2026-03-12",
        "amount": "12.3",
        "currency": "TWD",
        "expense_name": "Coffee",
        "source": "Sinopac Credit Card",
        "source_file": "a.pdf",
    })
    assert key[1] == ""
    assert key[2] == "12.30"


def test_format_export_row_handles_income_expense_and_none():
    row = cw._format_export_row({
        "date": "2026-03-12",
        "amount": -88.5,
        "currency": None,
        "expense_name": "Coffee",
        "expense_type": "Food",
        "source": "First Bank Credit Card",
        "original_file": "orig.pdf",
    })

    assert row["source_file"] == "orig.pdf"
    assert row["currency"] == ""
    assert row["income"] == "88.50"
    assert row["expense"] == ""


def test_format_export_row_never_populates_income_and_expense_together():
    row = cw._format_export_row({
        "date": "2026-03-12",
        "amount": 123.0,
        "currency": "TWD",
        "expense_name": "Coffee",
        "expense_type": "Food",
        "source": "First Bank Credit Card",
        "source_file": "orig.pdf",
    })

    assert not (row["income"] and row["expense"])


def test_format_export_row_prefers_cashflow_side_metadata():
    row = cw._format_export_row({
        "date": "2026-03-12",
        "amount": 2580.0,
        "currency": "TWD",
        "expense_name": "信用卡轉",
        "expense_type": "Bills",
        "source": "Fubon Bank",
        "cashflow_side": "expense",
        "source_file": "bank.pdf",
    })

    assert row["income"] == ""
    assert row["expense"] == "2580.00"


def test_load_existing_rows_missing_and_invalid(tmp_path):
    missing = tmp_path / "missing.csv"
    assert cw._load_existing_rows(str(missing)) == []

    broken = tmp_path / "broken.csv"
    broken.write_bytes(b"\xff\xfe\x00")
    # Should not raise, should return []
    assert cw._load_existing_rows(str(broken)) == []


def test_export_receipts_to_csv_appends_new_rows_only(tmp_path):
    output_dir = tmp_path / "out"

    first = {
        "date": "2026-03-01",
        "amount": 100,
        "currency": "TWD",
        "expense_name": "A",
        "expense_type": "Other",
        "source": "Sinopac Credit Card",
        "source_file": "a.pdf",
    }
    second = {
        "date": "2026-03-02",
        "amount": 200,
        "currency": "TWD",
        "expense_name": "B",
        "expense_type": "Other",
        "source": "Sinopac Credit Card",
        "source_file": "b.pdf",
    }

    path_csv = cw.export_receipts_to_csv([first], output_dir=str(output_dir)).split(",")[0]
    assert Path(path_csv).exists()

    # Re-run with one duplicate and one new row.
    cw.export_receipts_to_csv([first, second], output_dir=str(output_dir))

    with open(path_csv, "r", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    assert len(rows) == 2
    assert {r["expense_name"] for r in rows} == {"A", "B"}


def test_export_receipts_to_csv_appends_without_rewriting_existing_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    output_dir = tmp_path / "out"

    first = {
        "date": "2026-03-01",
        "amount": 100,
        "currency": "TWD",
        "expense_name": "A",
        "expense_type": "Other",
        "source": "Sinopac Credit Card",
        "source_file": "a.pdf",
    }
    second = {
        "date": "2026-03-02",
        "amount": 200,
        "currency": "TWD",
        "expense_name": "B",
        "expense_type": "Other",
        "source": "Sinopac Credit Card",
        "source_file": "b.pdf",
    }

    path_csv = cw.export_receipts_to_csv([first], output_dir=str(output_dir)).split(",")[0]
    original_open = open

    def guarded_open(path, mode="r", *args, **kwargs):
        if str(path) == path_csv and "w" in mode:
            raise AssertionError("existing monthly CSV should not be rewritten")
        return original_open(path, mode, *args, **kwargs)

    with patch("builtins.open", side_effect=guarded_open):
        cw.export_receipts_to_csv([second], output_dir=str(output_dir))

    with open(path_csv, "r", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    assert [row["expense_name"] for row in rows] == ["A", "B"]


def test_export_receipts_to_csv_backfills_existing_file_into_index(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    output_dir = tmp_path / "out"
    output_dir.mkdir()

    receipt = {
        "date": "2026-03-01",
        "amount": 100,
        "currency": "TWD",
        "expense_name": "A",
        "expense_type": "Other",
        "source": "Sinopac Credit Card",
        "source_file": "a.pdf",
    }
    new_receipt = {
        "date": "2026-03-03",
        "amount": 300,
        "currency": "TWD",
        "expense_name": "C",
        "expense_type": "Other",
        "source": "Sinopac Credit Card",
        "source_file": "c.pdf",
    }

    path_csv = output_dir / "expenses_2026-03.csv"
    with open(path_csv, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=[key for key, _ in cw.CSV_COLUMNS])
        writer.writeheader()
        writer.writerow(cw._format_export_row(receipt))

    cw.export_receipts_to_csv([receipt], output_dir=str(output_dir))

    with patch("src.export.csv_writer._load_existing_rows", side_effect=AssertionError("should use sqlite index after backfill")):
        cw.export_receipts_to_csv([receipt, new_receipt], output_dir=str(output_dir))

    with open(path_csv, "r", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    assert [row["expense_name"] for row in rows] == ["A", "C"]


def test_export_receipts_dedupes_with_income_expense_columns(tmp_path):
    output_dir = tmp_path / "out"
    receipt = {
        "date": "2026-03-01",
        "amount": 100,
        "currency": "TWD",
        "expense_name": "A",
        "expense_type": "Other",
        "source": "Sinopac Credit Card",
        "source_file": "a.pdf",
    }

    path_csv = cw.export_receipts_to_csv([receipt], output_dir=str(output_dir)).split(",")[0]
    cw.export_receipts_to_csv([receipt], output_dir=str(output_dir))

    with open(path_csv, "r", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    assert len(rows) == 1
    assert rows[0]["income"] == ""
    assert rows[0]["expense"] == "100.00"


def test_export_extracted_texts_to_csv_edge_paths(tmp_path):
    # Empty input
    assert cw.export_extracted_texts_to_csv([], output_dir=str(tmp_path)) == ""

    # Input that becomes empty after line cleaning
    only_markers = [{
        "filename": "a.pdf",
        "sender_tag": "x",
        "subject": "s",
        "text": "--- Page 1 ---\n   \n",
    }]
    assert cw.export_extracted_texts_to_csv(only_markers, output_dir=str(tmp_path)) == ""


def test_export_extracted_texts_to_csv_write_failure_raises(tmp_path):
    sample = [{
        "filename": "a.pdf",
        "sender_tag": "x",
        "subject": "s",
        "text": "2026/03/01 NT$100 test line",
    }]

    with patch("builtins.open", side_effect=OSError("disk full")):
        with pytest.raises(OSError):
            cw.export_extracted_texts_to_csv(sample, output_dir=str(tmp_path))


def test_sort_exported_receipt_csvs_sorts_rows_by_stable_key(tmp_path):
    path_csv = tmp_path / "expenses_2026-03.csv"
    with open(path_csv, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=[key for key, _ in cw.CSV_COLUMNS])
        writer.writeheader()
        writer.writerow({
            "date": "2026-03-03",
            "income": "",
            "expense": "200.00",
            "currency": "TWD",
            "expense_name": "B",
            "expense_type": "Other",
            "source": "Bank",
            "source_file": "b.pdf",
        })
        writer.writerow({
            "date": "2026-03-01",
            "income": "",
            "expense": "100.00",
            "currency": "TWD",
            "expense_name": "A",
            "expense_type": "Other",
            "source": "Bank",
            "source_file": "a.pdf",
        })

    cw.sort_exported_receipt_csvs([str(path_csv)])

    with open(path_csv, "r", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    assert [row["expense_name"] for row in rows] == ["A", "B"]


def test_format_receipt_for_csv_formats_numbers_and_none():
    out = cw.format_receipt_for_csv({
        "amount": 123.456,
        "confidence": 0.876,
        "note": None,
        "source": "X",
    })

    assert out["amount"] == "123.46"
    assert out["confidence"] == "87.6%"
    assert out["note"] == ""
    assert out["source"] == "X"
