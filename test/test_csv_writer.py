"""Unit tests for CSV output writer module."""

import os
import csv
from src.export.csv_writer import export_receipts_to_csv, export_extracted_texts_to_csv


class TestCSVWriter:
    """Test suite for CSV output writer functions."""

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
            assert rows[0]['amount'] == '100.50'
            assert rows[0]['currency'] == 'TWD'
            assert rows[0]['expense_name'] == 'Test Expense'
            assert rows[0]['source_file'] == 'a.pdf'

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
        extracted_texts = [
            {
                'text': 'Sample extracted text',
                'filename': 'test.pdf',
                'sender_tag': 'bank',
                'subject': 'Test Subject',
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
