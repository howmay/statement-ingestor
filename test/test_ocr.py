"""
Tests for HSBC OCR enrichment module.
"""
import pytest
from unittest.mock import Mock, MagicMock, patch
import os
import sys

from src.ocr.hsbc_ocr import (
    enrich_hsbc_transactions_with_ocr,
    _get_tesseract_langs,
    _normalize_md,
    _safe_float,
    _extract_rows_from_ocr_text
)

class TestHSBCOCR:
    """Test suite for HSBC OCR functionality."""

    def test_get_tesseract_langs_success(self):
        """Test getting installed languages from tesseract."""
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "List of available languages (3):\neng\nosd\nchi_tra"
        
        with patch('subprocess.run', return_value=mock_proc):
            langs = _get_tesseract_langs()
            assert 'eng' in langs
            assert 'chi_tra' in langs
            assert 'osd' in langs
            assert len(langs) == 3

    def test_get_tesseract_langs_failure(self):
        """Test failure to get languages."""
        with patch('subprocess.run', side_effect=Exception("Failed")):
            langs = _get_tesseract_langs()
            assert langs == set()

    def test_normalize_md(self):
        """Test date normalization."""
        assert _normalize_md("01/05") == "01/05"
        assert _normalize_md("1/5") == "01/05"
        assert _normalize_md("11/15") == "11/15"
        assert _normalize_md("1/1") == "01/01"

    def test_safe_float(self):
        """Test safe float conversion."""
        assert _safe_float("1,234.56") == 1234.56
        assert _safe_float("-50.0") == -50.0
        assert _safe_float(100) == 100.0
        assert _safe_float(None) is None
        assert _safe_float("abc") is None

    def test_extract_rows_from_ocr_text(self):
        """Test parsing rows from raw OCR text."""
        ocr_text = """
        01/05 02/05 STARBUCKS TAIWAN 150.00
        05/05 06/05 UBER TRIP 200.00 DR
        NOT A TRANSACTION LINE
        10/05 11/05 REBATE 50.00 CR
        """
        rows = _extract_rows_from_ocr_text(ocr_text)
        assert len(rows) == 3
        
        assert rows[0]['tx_md'] == "01/05"
        assert rows[0]['desc'] == "STARBUCKS TAIWAN"
        assert rows[0]['amount'] == 150.0
        
        assert rows[1]['tx_md'] == "05/05"
        assert rows[1]['amount'] == 200.0   # DR should be positive (Expense)
        
        assert rows[2]['tx_md'] == "10/05"
        assert rows[2]['amount'] == -50.0   # CR should be negative (Refund)

    @patch('src.ocr.hsbc_ocr.shutil.which')
    @patch('src.ocr.hsbc_ocr.os.path.exists')
    def test_enrich_hsbc_skipped_conditions(self, mock_exists, mock_which):
        """Test conditions where OCR is skipped."""
        transactions = [{'expense_name': '01/05 01/05 100.00'}]
        
        # 1. Missing filepath
        assert enrich_hsbc_transactions_with_ocr(transactions, {}) == 0
        
        # 2. File does not exist
        mock_exists.return_value = False
        assert enrich_hsbc_transactions_with_ocr(transactions, {'filepath': 'test.pdf'}) == 0
        
        # 3. Tesseract not found
        mock_exists.return_value = True
        mock_which.return_value = None
        assert enrich_hsbc_transactions_with_ocr(transactions, {'filepath': 'test.pdf'}) == 0

    @patch('src.ocr.hsbc_ocr._ocr_statement_rows')
    @patch('src.ocr.hsbc_ocr.shutil.which')
    @patch('src.ocr.hsbc_ocr.os.path.exists')
    @patch('src.ocr.hsbc_ocr._get_tesseract_langs')
    def test_enrich_hsbc_success(self, mock_langs, mock_exists, mock_which, mock_ocr_rows):
        """Test successful enrichment."""
        mock_exists.return_value = True
        mock_which.return_value = '/usr/bin/tesseract'
        mock_langs.return_value = {'chi_tra', 'eng'}
        
        transactions = [
            {
                'expense_name': '01/05 02/05 150.00',
                'raw_text_snippet': '01/05 02/05 150.00',
                'amount': 150.0
            }
        ]
        
        mock_ocr_rows.return_value = [
            {
                'tx_md': '01/05',
                'post_md': '02/05',
                'desc': 'STARBUCKS',
                'amount': 150.0
            }
        ]
        
        count = enrich_hsbc_transactions_with_ocr(
            transactions, 
            {'filepath': 'test.pdf'}
        )
        
        assert count == 1
        assert transactions[0]['expense_name'] == 'STARBUCKS'
        assert transactions[0]['description_source'] == 'ocr'
        assert transactions[0]['confidence'] == 0.93

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
