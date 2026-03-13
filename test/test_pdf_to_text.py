"""
Comprehensive tests for PDF text extraction module.
"""
import os
import pytest
from unittest.mock import Mock, MagicMock, patch
import logging
import sys

# Ensure the module is imported so we can patch its functions
from src.parsing.pdf.pdf_to_text import (
    extract_text_from_pdf,
    _extract_with_pdfium,
    _extract_with_pdfplumber,
    _extract_with_pypdf2,
    _extract_with_pdftotext,
    is_text_based_pdf
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
    @patch('src.parsing.pdf.pdf_to_text._extract_with_pypdf2')
    def test_extract_text_fallback_chain(self, mock_pypdf2, mock_pdfplumber, mock_pdfium, tmp_path):
        """Test the fallback chain of PDF extractors."""
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 minimal pdf content")
        
        # Test 1: pdfium succeeds
        mock_pdfium.return_value = "Text from pdfium"
        result = extract_text_from_pdf(str(pdf_file))
        assert result == "Text from pdfium"
        
        # Test 2: pdfium fails, pdfplumber succeeds
        mock_pdfium.return_value = ""
        mock_pdfplumber.return_value = "Text from pdfplumber"
        result = extract_text_from_pdf(str(pdf_file))
        assert result == "Text from pdfplumber"
        
        # Test 3: pdfium and pdfplumber fail, pypdf2 succeeds
        mock_pdfium.return_value = ""
        mock_pdfplumber.return_value = ""
        mock_pypdf2.return_value = "Text from pypdf2"
        result = extract_text_from_pdf(str(pdf_file))
        assert result == "Text from pypdf2"
        
        # Test 4: All extractors fail
        mock_pdfium.return_value = ""
        mock_pdfplumber.return_value = ""
        mock_pypdf2.return_value = ""
        result = extract_text_from_pdf(str(pdf_file))
        assert result is None

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

    def test_extract_with_pypdf2_success(self, tmp_path):
        """Test PyPDF2 extraction success."""
        # Create a real file to avoid FileNotFoundError
        pdf_path = tmp_path / "test.pdf"
        pdf_path.write_bytes(b"%PDF")
        
        mock_pypdf2 = MagicMock()
        # Mocking the exceptions
        mock_pypdf2.errors = MagicMock()
        mock_pypdf2.errors.FileNotDecryptedError = type('FileNotDecryptedError', (Exception,), {})
        mock_pypdf2.errors.PasswordError = type('PasswordError', (Exception,), {})
        
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "Extracted text from pypdf2"
        mock_reader = MagicMock()
        mock_reader.pages = [mock_page]
        mock_pypdf2.PdfReader.return_value = mock_reader
        
        with patch.dict('sys.modules', {'PyPDF2': mock_pypdf2}):
            result = _extract_with_pypdf2(str(pdf_path))
            assert "Extracted text from pypdf2" in result
            assert "--- Page 1 ---" in result

    def test_is_text_based_pdf(self, tmp_path):
        """Test text-based PDF detection."""
        pdf_file = tmp_path / "text.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 content")
        
        with patch('src.parsing.pdf.pdf_to_text.extract_text_from_pdf') as mock_extract:
            mock_extract.return_value = "Some text content"
            assert is_text_based_pdf(str(pdf_file)) is True
            
            mock_extract.return_value = "   "
            assert is_text_based_pdf(str(pdf_file)) is False

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

    def test_extract_with_pdftotext_success(self):
        """Test pdftotext extraction success."""
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "Text from pdftotext"
        
        with patch('shutil.which', return_value='/usr/bin/pdftotext'):
            with patch('subprocess.run', return_value=mock_proc) as mock_run:
                result = _extract_with_pdftotext("/path/to/test.pdf")
                assert result == "Text from pdftotext"
                mock_run.assert_called()
                assert 'pdftotext' in mock_run.call_args[0][0]

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
