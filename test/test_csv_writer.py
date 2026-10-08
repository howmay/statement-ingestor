import os
import csv
import pytest
import src.export.csv_writer as cw
from src.export.csv_writer import export_receipts_to_csv, export_extracted_texts_to_csv
from pathlib import Path
from unittest.mock import patch


class TestCSVWriter:
    """Test suite for CSV output writer functions."""

    def test_export_receipts_uses_income_and_expense_columns(self, tmp_path):
        receipts = [
            {
                'date': '2026-03-01',
                'amount': 100.0,
                'currency': 'TWD',
                'expense_name': 'Card Spend',
                'expense_type': 'Shopping',
                'source': 'Sinopac Credit Card',
                'source_file': 'card.pdf',
            }
        ]

        output_dir = tmp_path / 'output'
        filepath = export_receipts_to_csv(receipts, output_dir=str(output_dir)).split(',')[0]

        with open(filepath, 'r', encoding='utf-8-sig') as csvfile:
            reader = csv.DictReader(csvfile)
            rows = list(reader)

        assert 'income' in reader.fieldnames
        assert 'expense' in reader.fieldnames
        assert 'amount' not in reader.fieldnames
        assert rows[0]['income'] == ''
        assert rows[0]['expense'] == '100.00'

    def test_export_receipts_to_csv_success_month_partition(self, tmp_path):
        """Receipts should be exported into month-partitioned CSV file."""
        receipts = [
            {
                'date': '2023-01-01',
                'amount': 100.5,
                'currency': 'TWD',
                'expense_name': 'Test Expense',
                'expense_type': 'Shopping',
                'source': 'HSBC',
                'source_file': 'a.pdf',
            }
        ]

        output_dir = tmp_path / 'output'
        paths = export_receipts_to_csv(receipts, output_dir=str(output_dir))
        path_list = [p for p in paths.split(',') if p]

        assert len(path_list) == 1
        filepath = path_list[0]
        assert os.path.exists(filepath)
        assert filepath.endswith('expenses_2023-01.csv')

        with open(filepath, 'r', encoding='utf-8-sig') as csvfile:
            reader = csv.DictReader(csvfile)
            rows = list(reader)
            assert len(rows) == 1
            assert rows[0]['date'] == '2023-01-01'
            assert rows[0]['income'] == ''
            assert rows[0]['expense'] == '100.50'
            assert rows[0]['currency'] == 'TWD'
            assert rows[0]['expense_name'] == 'Test Expense'
            assert rows[0]['source_file'] == 'a.pdf'

    def test_credit_card_negative_amount_exports_to_income(self, tmp_path):
        receipts = [
            {
                'date': '2026-03-01',
                'amount': -11.0,
                'currency': 'TWD',
                'expense_name': 'Cashback',
                'expense_type': 'Reward',
                'source': 'Sinopac Credit Card',
                'source_file': 'card.pdf',
            }
        ]

        output_dir = tmp_path / 'output'
        filepath = export_receipts_to_csv(receipts, output_dir=str(output_dir)).split(',')[0]

        with open(filepath, 'r', encoding='utf-8-sig') as csvfile:
            rows = list(csv.DictReader(csvfile))

        assert rows[0]['income'] == '11.00'
        assert rows[0]['expense'] == ''

    def test_bank_positive_amount_exports_to_income(self, tmp_path):
        receipts = [
            {
                'date': '2026-03-01',
                'amount': 2500.0,
                'currency': 'TWD',
                'expense_name': 'Salary',
                'expense_type': 'Income',
                'source': 'Fubon Bank',
                'source_file': 'bank.pdf',
            }
        ]

        output_dir = tmp_path / 'output'
        filepath = export_receipts_to_csv(receipts, output_dir=str(output_dir)).split(',')[0]

        with open(filepath, 'r', encoding='utf-8-sig') as csvfile:
            rows = list(csv.DictReader(csvfile))

        assert rows[0]['income'] == '2500.00'
        assert rows[0]['expense'] == ''

    def test_bank_negative_amount_exports_to_expense(self, tmp_path):
        receipts = [
            {
                'date': '2026-03-01',
                'amount': -2500.0,
                'currency': 'TWD',
                'expense_name': 'Transfer Out',
                'expense_type': 'Transfer',
                'source': 'Fubon Bank',
                'source_file': 'bank.pdf',
            }
        ]

        output_dir = tmp_path / 'output'
        filepath = export_receipts_to_csv(receipts, output_dir=str(output_dir)).split(',')[0]

        with open(filepath, 'r', encoding='utf-8-sig') as csvfile:
            rows = list(csv.DictReader(csvfile))

        assert rows[0]['income'] == ''
        assert rows[0]['expense'] == '2500.00'

    def test_export_receipts_to_csv_dedupe_on_rerun(self, tmp_path):
        """Same rows should not be appended repeatedly across reruns."""
        receipt = {
            'date': '2023-01-01',
            'amount': 100.5,
            'currency': 'TWD',
            'expense_name': 'Test Expense',
            'expense_type': 'Shopping',
            'source': 'HSBC',
            'source_file': 'a.pdf',
        }

        output_dir = tmp_path / 'output'
        export_receipts_to_csv([receipt], output_dir=str(output_dir))
        export_receipts_to_csv([receipt], output_dir=str(output_dir))

        filepath = output_dir / 'expenses_2023-01.csv'
        with open(filepath, 'r', encoding='utf-8-sig') as csvfile:
            rows = list(csv.DictReader(csvfile))
            assert len(rows) == 1

    def test_export_receipts_to_csv_empty(self):
        """Test exporting empty receipts list."""
        filepath = export_receipts_to_csv([])
        assert filepath == ''

    def test_export_extracted_texts_to_csv(self, tmp_path):
        """Test exporting extracted texts to CSV."""
        # Shape produced by GmailExpenseParserApp.extract_texts: metadata lives under file_info.
        extracted_texts = [
            {
                'text': 'Sample extracted text',
                'file_info': {'filename': 'test.pdf', 'sender_tag': 'bank', 'subject': 'Test Subject'},
            }
        ]

        output_dir = tmp_path / 'output'
        filepath = export_extracted_texts_to_csv(extracted_texts, output_dir=str(output_dir))

        assert os.path.exists(filepath)

        with open(filepath, 'r', encoding='utf-8-sig') as csvfile:
            reader = csv.DictReader(csvfile)
            rows = list(reader)

            assert len(rows) == 1
            assert rows[0]['filename'] == 'test.pdf'
            assert rows[0]['line_text'] == 'Sample extracted text'
            assert rows[0]['sender_tag'] == 'bank'


def test_transaction_month_and_receipt_key_helpers():
    assert cw._transaction_month({"date": "2026-03-12"}) == "2026-03"
    assert cw._transaction_month({"date": "2026/03/12"}) == "2026-03"
    assert cw._transaction_month({"date": "bad"}) == "unknown"

    key = cw._receipt_key(cw._format_export_row({
        "date": "2026-03-12",
        "amount": "12.3",
        "currency": "TWD",
        "expense_name": "Coffee",
        "source": "Sinopac Credit Card",
        "source_file": "a.pdf",
    }))
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


def test_export_receipts_dedupes_within_one_call_and_across_calls(tmp_path):
    output_dir = tmp_path / "out"
    receipt = {
        "date": "2026-03-01",
        "amount": 100,
        "currency": "TWD",
        "expense_name": "A",
        "source": "Sinopac Credit Card",
        "source_file": "a.pdf",
    }

    path_csv = cw.export_receipts_to_csv([receipt, dict(receipt)], output_dir=str(output_dir))
    assert cw.export_receipts_to_csv([receipt, receipt], output_dir=str(output_dir)) == ""

    with open(path_csv, "r", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    assert len(rows) == 1


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
        writer = csv.DictWriter(f, fieldnames=cw.CSV_COLUMNS)
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


def _card_receipt(amount, **extra):
    base = {
        'date': '2026-07-26', 'amount': amount, 'currency': 'TWD', 'expense_name': 'PCHOME',
        'expense_type': 'Shopping', 'source': 'Esun Bank', 'parser_name': 'EsunCardParser',
        'confidence': 0.9, 'source_file': 'ESUN_Estatement_11507.pdf',
    }
    base.update(extra)
    return base


def test_credit_card_side_is_decided_by_parser_name_not_source_label(tmp_path):
    """Esun's card parser labels its source 'Esun Bank'; a positive amount is still a card purchase."""
    path = export_receipts_to_csv([_card_receipt(4663.0), _card_receipt(-295.0, expense_name='自動轉帳繳款')], output_dir=str(tmp_path))
    rows = list(csv.DictReader(open(path, encoding='utf-8-sig')))
    assert [(r['income'], r['expense']) for r in rows] == [('', '4663.00'), ('295.00', '')]


def test_zero_amount_rows_are_not_exported(tmp_path):
    """A 0-interest line moves no money and must not become a blank row."""
    receipts = [_card_receipt(0.0, expense_name='INTEREST', parser_name='TaishinBankParser', source='Taishin Bank'), _card_receipt(10.0)]
    path = export_receipts_to_csv(receipts, output_dir=str(tmp_path))
    rows = list(csv.DictReader(open(path, encoding='utf-8-sig')))
    assert [r['expense_name'] for r in rows] == ['PCHOME']


def test_balance_column_is_exported_and_old_files_are_migrated(tmp_path):
    """Bank-account rows carry the running balance; a CSV written with the old header is upgraded in place."""
    old = tmp_path / 'expenses_2026-07.csv'
    old.write_text('﻿date,income,expense,currency,expense_name,expense_type,source,source_file\n'
                   '2026-07-01,,100.00,TWD,OLD ROW,Other,Taishin Bank,old.pdf\n', encoding='utf-8')
    receipts = [_card_receipt(50.0, date='2026-07-02', expense_name='NEW ROW', parser_name='TaishinBankParser',
                              source='Taishin Bank', balance=1234.5, cashflow_side='expense')]
    export_receipts_to_csv(receipts, output_dir=str(tmp_path))
    rows = list(csv.DictReader(open(old, encoding='utf-8-sig')))
    assert list(rows[0].keys())[-1] == 'balance'
    assert [(r['expense_name'], r['balance']) for r in rows] == [('OLD ROW', ''), ('NEW ROW', '1234.50')]
