"""
Unit tests for CSV output writer module.
"""
import os
import pytest
import csv
from unittest.mock import patch
from datetime import datetime
from src.output.csv_writer import export_receipts_to_csv, export_extracted_texts_to_csv


class TestCSVWriter:
    """Test suite for CSV output writer functions."""
    
    def test_export_receipts_to_csv_success(self, tmp_path):
        """Test exporting receipts to CSV file."""
        receipts = [
            {
                'date': '2023-01-01',
                'amount': 100.5,
                'currency': 'TWD',
                'expense_name': 'Test Expense',
                'expense_type': 'Shopping'
            }
        ]
        
        # Call the function with temporary output directory
        output_dir = tmp_path / "output"
        filepath = export_receipts_to_csv(receipts, output_dir=str(output_dir))
        
        assert os.path.exists(filepath)
        assert filepath.endswith('.csv')
        
        # Verify CSV content
        with open(filepath, 'r', encoding='utf-8-sig') as csvfile:
            reader = csv.DictReader(csvfile)
            rows = list(reader)
            
            # The first row (header display name) is automatically handled by DictReader
            # but wait, the implementation writes display names as the first row.
            # DictReader will treat it as keys.
            assert len(rows) == 1
            # Check if values match
            # Note: DictReader keys will be the display names (日期, 金額, etc.)
            assert rows[0]['日期'] == '2023-01-01'
            assert rows[0]['金額'] == '100.50'
            assert rows[0]['幣別'] == 'TWD'
            assert rows[0]['消費名目'] == 'Test Expense'
            
    def test_export_receipts_to_csv_empty(self):
        """Test exporting empty receipts list."""
        filepath = export_receipts_to_csv([])
        assert filepath == ""
        
    def test_export_extracted_texts_to_csv(self, tmp_path):
        """Test exporting extracted texts to CSV."""
        extracted_texts = [
            {
                'text': 'Sample extracted text',
                'filename': 'test.pdf',
                'sender_tag': 'bank',
                'subject': 'Test Subject'
            }
        ]
        
        output_dir = tmp_path / "output"
        filepath = export_extracted_texts_to_csv(extracted_texts, output_dir=str(output_dir))
        
        assert os.path.exists(filepath)
        
        with open(filepath, 'r', encoding='utf-8-sig') as csvfile:
            reader = csv.DictReader(csvfile)
            rows = list(reader)
            
            assert len(rows) == 1
            assert rows[0]['filename'] == 'test.pdf'
            assert rows[0]['line_text'] == 'Sample extracted text'
            assert rows[0]['sender_tag'] == 'bank'
