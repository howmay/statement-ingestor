"""
Comprehensive tests for HSBC OCR enrichment module.
Covers all branches and edge cases to improve test coverage.
"""
import pytest
from unittest.mock import Mock, MagicMock, patch, mock_open
import os
import sys
import tempfile
import json

from src.ocr.hsbc_ocr import (
    enrich_hsbc_transactions_with_ocr,
    _get_tesseract_langs,
    _normalize_md,
    _safe_float,
    _extract_rows_from_ocr_text,
    _clean_ocr_desc,
    _run_tesseract_text,
    _ocr_statement_rows,
    _open_pdf_with_password_candidates,
    OCR_ROW_PATTERN,
    MISSING_DESC_LINE_PATTERN
)


class TestHSBCOCRComprehensive:
    """Comprehensive test suite for HSBC OCR functionality."""

    def test_missing_desc_line_pattern(self):
        """Test the MISSING_DESC_LINE_PATTERN regex."""
        # Valid patterns
        assert MISSING_DESC_LINE_PATTERN.match("01/05 02/05 100.00")
        assert MISSING_DESC_LINE_PATTERN.match("1/5 2/5 1,234.56")
        assert MISSING_DESC_LINE_PATTERN.match("11/15 12/15 -50.00")
        
        # Invalid patterns (should not match)
        assert not MISSING_DESC_LINE_PATTERN.match("01/05 02/05 Starbucks 100.00")
        assert not MISSING_DESC_LINE_PATTERN.match("01/05 Starbucks 100.00")
        assert not MISSING_DESC_LINE_PATTERN.match("Starbucks 100.00")

    def test_ocr_row_pattern(self):
        """Test the OCR_ROW_PATTERN regex with various formats."""
        # Standard format
        match = OCR_ROW_PATTERN.search("01/05 02/05 STARBUCKS TAIWAN 150.00")
        assert match
        assert match.group('tx_md') == "01/05"
        assert match.group('post_md') == "02/05"
        assert match.group('desc') == "STARBUCKS TAIWAN"
        assert match.group('amount') == "150.00"
        
        # With DR suffix
        match = OCR_ROW_PATTERN.search("01/05 02/05 UBER TRIP 200.00 DR")
        assert match
        assert match.group('amount') == "200.00"
        assert match.group('suffix') == "DR"
        
        # With CR suffix
        match = OCR_ROW_PATTERN.search("01/05 02/05 REBATE 50.00 CR")
        assert match
        assert match.group('suffix') == "CR"
        
        # With dash separator
        match = OCR_ROW_PATTERN.search("01-05 02-05 TEST 100.00")
        assert match
        assert match.group('tx_md') == "01-05"
        assert match.group('post_md') == "02-05"
        
        # Negative amount
        match = OCR_ROW_PATTERN.search("01/05 02/05 REFUND -100.00")
        assert match
        assert match.group('amount') == "-100.00"

    def test_clean_ocr_desc(self):
        """Test cleaning OCR artifacts from description."""
        # Normal description
        assert _clean_ocr_desc("STARBUCKS TAIWAN") == "STARBUCKS TAIWAN"
        
        # With quotes and brackets
        assert _clean_ocr_desc("「STARBUCKS」") == "STARBUCKS"
        assert _clean_ocr_desc("【STARBUCKS】") == "STARBUCKS"
        assert _clean_ocr_desc("『STARBUCKS』") == "STARBUCKS"
        
        # With leading punctuation
        assert _clean_ocr_desc("| STARBUCKS") == "STARBUCKS"
        assert _clean_ocr_desc("¦ STARBUCKS") == "STARBUCKS"
        # Note: The regex only strips leading punctuation, not trailing
        assert _clean_ocr_desc("[STARBUCKS]") == "STARBUCKS]"
        
        # Empty or whitespace
        assert _clean_ocr_desc("") == ""
        assert _clean_ocr_desc("   ") == ""
        
        # With channel tag (should be preserved)
        assert _clean_ocr_desc("STARBUCKS APE") == "STARBUCKS APE"
        assert _clean_ocr_desc("| STARBUCKS FP") == "STARBUCKS FP"

    def test_normalize_md_edge_cases(self):
        """Test date normalization edge cases."""
        # Invalid formats should return stripped input
        assert _normalize_md("01-05-2023") == "01-05-2023"
        assert _normalize_md("invalid") == "invalid"
        assert _normalize_md("") == ""
        assert _normalize_md("  01/05  ") == "01/05"

    def test_safe_float_edge_cases(self):
        """Test safe float conversion edge cases."""
        # Empty strings
        assert _safe_float("") is None
        assert _safe_float("   ") is None
        
        # Scientific notation
        assert _safe_float("1.23e4") == 12300.0
        
        # With currency symbols (should fail)
        assert _safe_float("$100.00") is None
        
        # Boolean values - these will fail because str(True) = "True" which can't be converted to float
        assert _safe_float(True) is None
        assert _safe_float(False) is None

    def test_extract_rows_from_ocr_text_edge_cases(self):
        """Test edge cases for OCR row extraction."""
        # Empty text
        assert _extract_rows_from_ocr_text("") == []
        
        # Text with no valid rows
        text = """
        STATEMENT PERIOD: 01/05 - 31/05
        CREDIT LIMIT: 100,000
        MINIMUM PAYMENT: 1,000
        """
        assert _extract_rows_from_ocr_text(text) == []
        
        # Text with header-like rows that should be skipped
        text = """
        01/05 02/05 STATEMENT DATE 100.00
        01/05 02/05 PAYMENT DUE 200.00
        01/05 02/05 CREDIT LIMIT 300.00
        01/05 02/05 總額 400.00
        01/05 02/05 應繳金額 500.00
        01/05 02/05 STARBUCKS 150.00
        """
        rows = _extract_rows_from_ocr_text(text)
        assert len(rows) == 1
        assert rows[0]['desc'] == "STARBUCKS"
        
        # Text with very short descriptions (should be filtered)
        text = "01/05 02/05 A 100.00"
        assert _extract_rows_from_ocr_text(text) == []
        
        # Text with amount parsing failure
        text = "01/05 02/05 TEST invalid"
        assert _extract_rows_from_ocr_text(text) == []

    @patch('subprocess.run')
    def test_run_tesseract_text(self, mock_run):
        """Test tesseract text extraction."""
        # Success with chi_tra+eng
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "OCR text result"
        mock_run.return_value = mock_proc
        
        result = _run_tesseract_text("test.png")
        assert result == "OCR text result"
        
        # Fallback to eng when chi_tra+eng fails
        mock_run.side_effect = [
            Exception("Failed"),  # First call fails
            mock_proc             # Second call succeeds
        ]
        
        result = _run_tesseract_text("test.png")
        assert result == "OCR text result"
        
        # Both attempts fail
        mock_run.side_effect = Exception("Failed")
        result = _run_tesseract_text("test.png")
        assert result == ""

    @patch('src.ocr.hsbc_ocr.pdfium', create=True)
    @patch('tempfile.TemporaryDirectory')
    def test_ocr_statement_rows(self, mock_tempdir, mock_pdfium):
        """Test OCR statement rows extraction."""
        # Mock PDF document
        mock_pdf = MagicMock()
        mock_pdf.__len__.return_value = 2
        
        mock_page1 = MagicMock()
        mock_bitmap1 = MagicMock()
        mock_image1 = MagicMock()
        
        mock_page2 = MagicMock()
        mock_bitmap2 = MagicMock()
        mock_image2 = MagicMock()
        
        # Set up page rendering chain
        mock_pdf.__getitem__.side_effect = [mock_page1, mock_page2]
        mock_page1.render.return_value = mock_bitmap1
        mock_bitmap1.to_pil.return_value = mock_image1
        
        mock_page2.render.return_value = mock_bitmap2
        mock_bitmap2.to_pil.return_value = mock_image2
        
        mock_pdfium.PdfDocument.return_value = mock_pdf
        
        # Mock temporary directory
        mock_tempdir.return_value.__enter__.return_value = "/tmp/test"
        
        # Mock tesseract
        with patch('src.ocr.hsbc_ocr._run_tesseract_text') as mock_tesseract:
            mock_tesseract.side_effect = [
                "01/05 02/05 STARBUCKS 150.00\n02/05 03/05 UBER 200.00",
                ""  # Second page empty
            ]
            
            # Mock _open_pdf_with_password_candidates to return our mock PDF
            with patch('src.ocr.hsbc_ocr._open_pdf_with_password_candidates') as mock_open_pdf:
                mock_open_pdf.return_value = mock_pdf
                rows = _ocr_statement_rows("test.pdf", {})
            assert len(rows) == 2
            assert rows[0]['desc'] == "STARBUCKS"
            assert rows[1]['desc'] == "UBER"
            
            # Verify PDF was closed
            mock_pdf.close.assert_called_once()

    @patch('builtins.__import__')
    def test_ocr_statement_rows_pdfium_import_error(self, mock_import):
        """Test OCR statement rows when pypdfium2 is not available."""
        # Mock the import error for pypdfium2
        mock_import.side_effect = ImportError("No module named 'pypdfium2'")
        
        with pytest.raises(RuntimeError, match="pypdfium2 is required for OCR fallback"):
            _ocr_statement_rows("test.pdf", {})

    @patch('src.core.config.get_bank_password')
    @patch('src.ocr.hsbc_ocr.pdfium', create=True)
    def test_open_pdf_with_password_candidates(self, mock_pdfium, mock_get_password):
        """Test PDF opening with password candidates."""
        mock_pdf = MagicMock()
        
        # Test with preferred password
        source_info = {'sender': 'hsbc@example.com', 'pdf_password': 'secret123'}
        mock_pdfium.PdfDocument.return_value = mock_pdf
        
        result = _open_pdf_with_password_candidates(mock_pdfium, "test.pdf", source_info)
        assert result == mock_pdf
        mock_pdfium.PdfDocument.assert_called_with("test.pdf", password='secret123')
        
        # Test fallback to config passwords
        mock_pdfium.PdfDocument.reset_mock()
        mock_pdfium.PdfDocument.side_effect = [
            Exception("Wrong password"),  # First attempt fails
            mock_pdf                      # Second succeeds
        ]
        mock_get_password.return_value = ['config_pass1', 'config_pass2']
        
        source_info = {'sender': 'hsbc@example.com'}
        result = _open_pdf_with_password_candidates(mock_pdfium, "test.pdf", source_info)
        assert result == mock_pdf
        # Should have tried config_pass1 first, then config_pass2
        # The last successful call was with config_pass2
        mock_pdfium.PdfDocument.assert_called_with("test.pdf", password='config_pass2')
        
        # Test opening without password as last resort
        mock_pdfium.PdfDocument.reset_mock()
        mock_pdfium.PdfDocument.side_effect = [
            Exception("Wrong password"),  # config_pass fails
            mock_pdf                      # No password succeeds
        ]
        mock_get_password.return_value = ['config_pass']
        
        result = _open_pdf_with_password_candidates(mock_pdfium, "test.pdf", source_info)
        assert result == mock_pdf
        assert result == mock_pdf
        # Should have tried without password
        mock_pdfium.PdfDocument.assert_called_with("test.pdf")

    @patch('src.ocr.hsbc_ocr._ocr_statement_rows')
    @patch('src.ocr.hsbc_ocr.shutil.which')
    @patch('src.ocr.hsbc_ocr.os.path.exists')
    @patch('src.core.config.get_bank_password')
    def test_enrich_hsbc_chi_tra_not_required(self, mock_get_password, mock_exists, mock_which, mock_ocr_rows):
        """Test OCR when chi_tra is not required."""
        mock_exists.return_value = True
        mock_which.return_value = '/usr/bin/tesseract'
        
        # Set environment variable to not require chi_tra
        with patch.dict('os.environ', {'HSBC_OCR_REQUIRE_CHI_TRA': 'false'}):
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

    @patch('src.ocr.hsbc_ocr._ocr_statement_rows')
    @patch('src.ocr.hsbc_ocr.shutil.which')
    @patch('src.core.config.get_bank_password')
    @patch('src.ocr.hsbc_ocr.os.path.exists')
    def test_enrich_hsbc_candidate_selection(self, mock_exists, mock_get_password, mock_which, mock_ocr_rows):
        """Test transaction candidate selection logic."""
        mock_exists.return_value = True
        mock_which.return_value = '/usr/bin/tesseract'
        
        # Test various candidate scenarios
        transactions = [
            # Valid candidate: matches missing pattern
            {
                'expense_name': '01/05 02/05 150.00',
                'raw_text_snippet': '01/05 02/05 150.00',
                'amount': 150.0
            },
            # Not a candidate: has description
            {
                'expense_name': 'STARBUCKS 150.00',
                'raw_text_snippet': 'STARBUCKS 150.00',
                'amount': 150.0
            },
            # Candidate: expense_name matches but raw_text doesn't
            {
                'expense_name': '01/05 02/05 200.00',
                'raw_text_snippet': 'Some other text',
                'amount': 200.0
            },
            # Not a candidate: amount is None
            {
                'expense_name': '01/05 02/05 300.00',
                'raw_text_snippet': '01/05 02/05 300.00',
                'amount': None
            }
        ]
        
        mock_ocr_rows.return_value = [
            {
                'tx_md': '01/05',
                'post_md': '02/05',
                'desc': 'STARBUCKS',
                'amount': 150.0
            },
            {
                'tx_md': '01/05',
                'post_md': '02/05',
                'desc': 'UBER',
                'amount': 200.0
            }
        ]
        
        count = enrich_hsbc_transactions_with_ocr(
            transactions, 
            {'filepath': 'test.pdf'}
        )
        
        # Only first and third transactions should be enriched
        assert count == 2
        assert transactions[0]['expense_name'] == 'STARBUCKS'
        assert transactions[2]['expense_name'] == 'UBER'
        assert transactions[1]['expense_name'] == 'STARBUCKS 150.00'  # Unchanged

    @patch('src.ocr.hsbc_ocr._ocr_statement_rows')
    @patch('src.ocr.hsbc_ocr.shutil.which')
    @patch('src.ocr.hsbc_ocr.os.path.exists')
    def test_enrich_hsbc_matching_logic(self, mock_exists, mock_which, mock_ocr_rows):
        """Test OCR matching logic with exact and absolute value matches."""
        mock_exists.return_value = True
        mock_which.return_value = '/usr/bin/tesseract'
        
        transactions = [
            {
                'expense_name': '01/05 02/05 150.00',
                'raw_text_snippet': '01/05 02/05 150.00',
                'amount': 150.0,
                'confidence': 0.5
            },
            {
                'expense_name': '02/05 03/05 -200.00',
                'raw_text_snippet': '02/05 03/05 -200.00',
                'amount': -200.0,
                'confidence': 0.6
            }
        ]
        
        # OCR rows with both positive and negative amounts
        mock_ocr_rows.return_value = [
            {
                'tx_md': '01/05',
                'post_md': '02/05',
                'desc': 'STARBUCKS',
                'amount': 150.0
            },
            {
                'tx_md': '02/05',
                'post_md': '03/05',
                'desc': 'UBER REFUND',
                'amount': -200.0  # Negative in OCR
            }
        ]
        
        count = enrich_hsbc_transactions_with_ocr(
            transactions, 
            {'filepath': 'test.pdf'}
        )
        
        # Both should match using absolute value matching for the negative one
        assert count == 2
        assert transactions[0]['expense_name'] == 'STARBUCKS'
        assert transactions[0]['confidence'] == 0.93  # Should be max(0.5, 0.93)
        assert transactions[1]['expense_name'] == 'UBER REFUND'
        assert transactions[1]['confidence'] == 0.93  # Should be max(0.6, 0.93)

    @patch('src.ocr.hsbc_ocr._ocr_statement_rows')
    @patch('src.ocr.hsbc_ocr.shutil.which')
    @patch('src.ocr.hsbc_ocr.os.path.exists')
    @patch('src.ocr.hsbc_ocr._get_tesseract_langs')
    def test_enrich_hsbc_no_candidates(self, mock_langs, mock_exists, mock_which, mock_ocr_rows):
        """Test when no transactions are candidates for enrichment."""
        mock_exists.return_value = True
        mock_which.return_value = '/usr/bin/tesseract'
        mock_langs.return_value = {'chi_tra', 'eng'}
        
        # Transactions with descriptions already
        transactions = [
            {
                'expense_name': 'STARBUCKS 150.00',
                'raw_text_snippet': 'STARBUCKS 150.00',
                'amount': 150.0
            }
        ]
        
        count = enrich_hsbc_transactions_with_ocr(
            transactions, 
            {'filepath': 'test.pdf'}
        )
        
        assert count == 0
        mock_ocr_rows.assert_not_called()  # Should not even attempt OCR

    @patch('src.ocr.hsbc_ocr._ocr_statement_rows')
    @patch('src.ocr.hsbc_ocr.shutil.which')
    @patch('src.ocr.hsbc_ocr.os.path.exists')
    @patch('src.ocr.hsbc_ocr._get_tesseract_langs')
    def test_enrich_hsbc_ocr_failure(self, mock_langs, mock_exists, mock_which, mock_ocr_rows):
        """Test when OCR fails."""
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
        
        mock_ocr_rows.side_effect = Exception("OCR failed")
        
        count = enrich_hsbc_transactions_with_ocr(
            transactions, 
            {'filepath': 'test.pdf'}
        )
        
        assert count == 0
        assert transactions[0]['expense_name'] == '01/05 02/05 150.00'  # Unchanged

    @patch('src.ocr.hsbc_ocr._ocr_statement_rows')
    @patch('src.ocr.hsbc_ocr.shutil.which')
    @patch('src.ocr.hsbc_ocr.os.path.exists')
    @patch('src.ocr.hsbc_ocr._get_tesseract_langs')
    def test_enrich_hsbc_no_ocr_rows(self, mock_langs, mock_exists, mock_which, mock_ocr_rows):
        """Test when OCR returns no rows."""
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
        
        mock_ocr_rows.return_value = []
        
        count = enrich_hsbc_transactions_with_ocr(
            transactions, 
            {'filepath': 'test.pdf'}
        )
        
        assert count == 0

    @patch('src.ocr.hsbc_ocr._ocr_statement_rows')
    @patch('src.ocr.hsbc_ocr.shutil.which')
    @patch('src.ocr.hsbc_ocr.os.path.exists')
    @patch('src.ocr.hsbc_ocr._get_tesseract_langs')
    def test_enrich_hsbc_partial_matching(self, mock_langs, mock_exists, mock_which, mock_ocr_rows):
        """Test when only some candidates match OCR rows."""
        mock_exists.return_value = True
        mock_which.return_value = '/usr/bin/tesseract'
        mock_langs.return_value = {'chi_tra', 'eng'}
        
        transactions = [
            {
                'expense_name': '01/05 02/05 150.00',
                'raw_text_snippet': '01/05 02/05 150.00',
                'amount': 150.0
            },
            {
                'expense_name': '02/05 03/05 200.00',
                'raw_text_snippet': '02/05 03/05 200.00',
                'amount': 200.0
            },
            {
                'expense_name': '03/05 04/05 300.00',
                'raw_text_snippet': '03/05 04/05 300.00',
                'amount': 300.0
            }
        ]
        
        # Only first transaction has a match in OCR
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
        assert transactions[1]['expense_name'] == '02/05 03/05 200.00'  # Unchanged
        assert transactions[2]['expense_name'] == '03/05 04/05 300.00'  # Unchanged

    def test_enrich_hsbc_description_truncation(self):
        """Test that descriptions are truncated to 120 characters."""
        # This test doesn't need mocks since we're testing the logic directly
        # We'll create a simple test to verify the truncation logic
        transactions = [
            {
                'expense_name': '01/05 02/05 150.00',
                'raw_text_snippet': '01/05 02/05 150.00',
                'amount': 150.0
            }
        ]
        
        # Mock the minimum required functions
        with patch('src.ocr.hsbc_ocr.os.path.exists', return_value=True):
            with patch('src.ocr.hsbc_ocr.shutil.which', return_value='/usr/bin/tesseract'):
                with patch('src.ocr.hsbc_ocr._get_tesseract_langs', return_value={'chi_tra', 'eng'}):
                    with patch('src.ocr.hsbc_ocr._ocr_statement_rows') as mock_ocr_rows:
                        # Create a very long description
                        long_desc = 'A' * 150
                        mock_ocr_rows.return_value = [
                            {
                                'tx_md': '01/05',
                                'post_md': '02/05',
                                'desc': long_desc,
                                'amount': 150.0
                            }
                        ]
                        
                        count = enrich_hsbc_transactions_with_ocr(
                            transactions, 
                            {'filepath': 'test.pdf'}
                        )
                        
                        assert count == 1
                        assert len(transactions[0]['expense_name']) == 120
                        assert transactions[0]['expense_name'] == 'A' * 120


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
