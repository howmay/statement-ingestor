"""
Comprehensive tests for PDF text extraction module.
"""
import os
import pytest
from unittest.mock import Mock, MagicMock, patch
import logging
import sys
from pathlib import Path

# Ensure the module is imported so we can patch its functions
from src.parsing.pdf.pdf_to_text import (
    extract_text_from_pdf,
    _extract_with_pdfium,
    _extract_with_pdfplumber,
)


class TestPDFTextExtraction:
    """Test PDF text extraction functionality."""
    
    def test_extract_text_from_pdf_file_not_found(self):
        """Test that FileNotFoundError is raised for non-existent file."""
        with pytest.raises(FileNotFoundError):
            extract_text_from_pdf("/nonexistent/file.pdf")
    
    def test_extract_text_from_pdf_empty_file(self, tmp_path):
        """Test that ValueError is raised for empty PDF file."""
        empty_pdf = tmp_path / "empty.pdf"
        empty_pdf.write_bytes(b"")
        
        with pytest.raises(ValueError, match="PDF file is empty"):
            extract_text_from_pdf(str(empty_pdf))
    
    def test_extract_text_from_pdf_non_pdf_extension(self, tmp_path):
        """Test warning for non-PDF extension."""
        non_pdf = tmp_path / "file.txt"
        non_pdf.write_bytes(b"not a pdf")
        
        with patch("src.parsing.pdf.pdf_to_text.logger.warning") as mock_warning:
            try:
                extract_text_from_pdf(str(non_pdf))
            except Exception:
                pass
            
            # Check warning was logged
            mock_warning.assert_any_call(f"File does not have .pdf extension: {str(non_pdf)}")

    @patch('src.parsing.pdf.pdf_to_text._extract_with_pdfium')
    @patch('src.parsing.pdf.pdf_to_text._extract_with_pdfplumber')
    def test_extract_text_fallback_chain(self, mock_pdfplumber, mock_pdfium, tmp_path):
        """pdfplumber first, pypdfium2 fallback, None when both are empty."""
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 minimal pdf content")

        mock_pdfplumber.return_value = "Text from pdfplumber"
        mock_pdfium.return_value = ""
        assert extract_text_from_pdf(str(pdf_file)) == "Text from pdfplumber"
        mock_pdfium.assert_not_called()

        mock_pdfplumber.return_value = ""
        mock_pdfium.return_value = "Text from pdfium"
        assert extract_text_from_pdf(str(pdf_file)) == "Text from pdfium"

        mock_pdfium.return_value = ""
        assert extract_text_from_pdf(str(pdf_file)) is None

    def test_extract_with_pdfium_success(self):
        """Test pdfium extraction success."""
        mock_pdfium = MagicMock()
        mock_pdfium.PdfiumError = type('PdfiumError', (Exception,), {})
        
        mock_page = MagicMock()
        # Set up both get_textpage and get_text_page attributes
        mock_text_page = MagicMock()
        mock_text_page.get_text_range.return_value = "Extracted text from pdfium"
        mock_page.get_textpage = MagicMock(return_value=mock_text_page)
        mock_page.get_text_page = MagicMock(return_value=mock_text_page)
        
        mock_doc = MagicMock()
        mock_doc.__len__.return_value = 1
        mock_doc.__getitem__.return_value = mock_page
        mock_pdfium.PdfDocument.return_value = mock_doc
        
        with patch.dict('sys.modules', {'pypdfium2': mock_pdfium}):
            result = _extract_with_pdfium("/path/to/test.pdf")
            assert "Extracted text from pdfium" in result
            assert "--- Page 1 ---" in result

    def test_extract_with_pdfplumber_success(self, tmp_path):
        """Test pdfplumber extraction success."""
        # Create a real file to avoid FileNotFoundError in some paths
        pdf_path = tmp_path / "test.pdf"
        pdf_path.write_bytes(b"%PDF")
        
        mock_pdfplumber = MagicMock()
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "Extracted text from pdfplumber"
        mock_pdf = MagicMock()
        mock_pdf.pages = [mock_page]
        mock_pdfplumber.open.return_value.__enter__.return_value = mock_pdf
        
        with patch.dict('sys.modules', {'pdfplumber': mock_pdfplumber}):
            result = _extract_with_pdfplumber(str(pdf_path))
            assert "Extracted text from pdfplumber" in result
            assert "--- Page 1 ---" in result

    @patch('src.parsing.pdf.pdf_to_text.os.path.getsize')
    def test_extract_text_with_password(self, mock_getsize, tmp_path):
        """Test extraction with password parameter."""
        pdf_file = tmp_path / "encrypted.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 encrypted")
        mock_getsize.return_value = 100
        
        with patch('src.parsing.pdf.pdf_to_text._extract_with_pdfium') as mock_pdfium:
            mock_pdfium.return_value = "Decrypted text"
            result = extract_text_from_pdf(str(pdf_file), password="secret")
            assert result == "Decrypted text"
            mock_pdfium.assert_called_with(str(pdf_file), "secret")

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
