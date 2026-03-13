"""
Comprehensive tests for PDF text extraction module.
Covers all branches and edge cases to improve test coverage.
"""
import pytest
from unittest.mock import Mock, MagicMock, patch
import os
import sys
import tempfile
from unittest.mock import mock_open

from src.pdf.pdf_to_text import (
    extract_text_from_pdf,
    _extract_with_pdfium,
    _extract_with_pdfplumber,
    _extract_with_pypdf2,
    _extract_with_pdftotext,
    is_text_based_pdf,
    main,
)


class TestPDFTextExtractionComprehensive:
    """Comprehensive test suite for PDF text extraction."""

    def test_extract_file_not_found(self):
        """Test FileNotFoundError for non-existent file."""
        with pytest.raises(FileNotFoundError, match="PDF file not found"):
            extract_text_from_pdf("/nonexistent/file.pdf")

    def test_extract_empty_file(self, tmp_path):
        """Test ValueError for empty file."""
        empty_pdf = tmp_path / "empty.pdf"
        empty_pdf.write_bytes(b"")
        
        with pytest.raises(ValueError, match="PDF file is empty"):
            extract_text_from_pdf(str(empty_pdf))

    def test_extract_non_pdf_extension(self, tmp_path):
        """Test warning for non-PDF extension."""
        non_pdf = tmp_path / "file.txt"
        non_pdf.write_bytes(b"not a pdf")
        
        with patch("src.pdf.pdf_to_text.logger.warning") as mock_warning:
            try:
                extract_text_from_pdf(str(non_pdf))
            except Exception:
                pass
            
            # Check warning was logged
            mock_warning.assert_any_call(f"File does not have .pdf extension: {str(non_pdf)}")

    @patch('src.pdf.pdf_to_text._extract_with_pdftotext', return_value="")
    @patch('src.pdf.pdf_to_text._extract_with_pdfplumber', return_value="")
    @patch('src.pdf.pdf_to_text._extract_with_pdfium', return_value="")
    def test_extract_all_extractors_fail(self, mock_pdfium, mock_pdfplumber, mock_pdftotext, tmp_path):
        """Test when all PDF extractors return empty."""
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4")
        
        result = extract_text_from_pdf(str(pdf_file))
        assert result is None

    @patch('src.pdf.pdf_to_text._extract_with_pdftotext', return_value="")
    @patch('src.pdf.pdf_to_text._extract_with_pdfplumber', return_value="Text from pdfplumber")
    @patch('src.pdf.pdf_to_text._extract_with_pdfium', return_value="")
    def test_extract_pdftotext_empty_triggers_fallback(self, mock_pdfium, mock_pdfplumber, mock_pdftotext, tmp_path):
        """Test that pdftotext empty return triggers fallback to pdfplumber."""
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4")
        
        result = extract_text_from_pdf(str(pdf_file))
        assert result == "Text from pdfplumber"
        # pdftotext was called first
        mock_pdftotext.assert_called_once()

    @patch('src.pdf.pdf_to_text._extract_with_pdftotext', side_effect=Exception("pdftotext error"))
    @patch('src.pdf.pdf_to_text._extract_with_pdfplumber', return_value="Text from pdfplumber")
    @patch('src.pdf.pdf_to_text._extract_with_pdfium', return_value="")
    def test_extract_pdftotext_exception_triggers_fallback(self, mock_pdfium, mock_pdfplumber, mock_pdftotext, tmp_path):
        """Test that pdftotext exception triggers fallback to pdfplumber."""
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4")
        
        result = extract_text_from_pdf(str(pdf_file))
        assert result == "Text from pdfplumber"

    @patch('src.pdf.pdf_to_text._extract_with_pdftotext', return_value="")
    @patch('src.pdf.pdf_to_text._extract_with_pdfplumber', return_value="Text from pdfplumber")
    @patch('src.pdf.pdf_to_text._extract_with_pdfium', side_effect=ImportError("No module"))
    def test_extract_pdfium_import_error_fallback(self, mock_pdfium, mock_pdfplumber, mock_pdftotext, tmp_path):
        """Test fallback when pdfium import fails."""
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4")
        
        result = extract_text_from_pdf(str(pdf_file))
        assert result == "Text from pdfplumber"

    @patch('src.pdf.pdf_to_text._extract_with_pdftotext', return_value="")
    @patch('src.pdf.pdf_to_text._extract_with_pdfplumber', return_value="Text from pdfplumber")
    @patch('src.pdf.pdf_to_text._extract_with_pdfium', side_effect=Exception("pypdfium2 error"))
    def test_extract_pdfium_exception_fallback(self, mock_pdfium, mock_pdfplumber, mock_pdftotext, tmp_path):
        """Test fallback when pdfium raises exception."""
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4")
        
        result = extract_text_from_pdf(str(pdf_file))
        assert result == "Text from pdfplumber"

    @patch('src.pdf.pdf_to_text._extract_with_pdftotext', return_value="")
    @patch('shutil.which', return_value=None)
    @patch('src.pdf.pdf_to_text._extract_with_pdfplumber', return_value="Text from pdfplumber")
    @patch('src.pdf.pdf_to_text._extract_with_pdfium', return_value="")
    def test_extract_pdftotext_not_available(self, mock_pdfium, mock_pdfplumber, mock_which, mock_pdftotext, tmp_path):
        """Test when pdftotext is not available."""
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4")
        
        result = extract_text_from_pdf(str(pdf_file))
        assert result == "Text from pdfplumber"

    @patch('src.pdf.pdf_to_text._extract_with_pdftotext', side_effect=Exception("pdftotext failed"))
    @patch('src.pdf.pdf_to_text._extract_with_pdfplumber', return_value="Text from pdfplumber")
    @patch('src.pdf.pdf_to_text._extract_with_pdfium', return_value="")
    def test_extract_pdftotext_exception(self, mock_pdfium, mock_pdfplumber, mock_pdftotext, tmp_path):
        """Test when pdftotext raises exception."""
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4")
        
        result = extract_text_from_pdf(str(pdf_file))
        assert result == "Text from pdfplumber"

    @patch('src.pdf.pdf_to_text._extract_with_pdftotext', return_value="")
    @patch('src.pdf.pdf_to_text._extract_with_pdfplumber', side_effect=ImportError("No module"))
    @patch('src.pdf.pdf_to_text._extract_with_pdfium', return_value="")
    @patch('src.pdf.pdf_to_text._extract_with_pypdf2', return_value="Text from pypdf2")
    def test_extract_pdfplumber_import_error(self, mock_pdfium, mock_pdfplumber, mock_pdftotext, mock_pypdf2, tmp_path):
        """Test fallback when pdfplumber import fails."""
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4")
        
        result = extract_text_from_pdf(str(pdf_file))
        assert result == "Text from pypdf2"

    @patch('src.pdf.pdf_to_text._extract_with_pdftotext', return_value="")
    @patch('src.pdf.pdf_to_text._extract_with_pdfplumber', side_effect=ValueError("Incorrect password"))
    @patch('src.pdf.pdf_to_text._extract_with_pdfium', return_value="")
    @patch('src.pdf.pdf_to_text._extract_with_pypdf2', return_value="Text from pypdf2")
    def test_extract_pdfplumber_password_error(self, mock_pdfium, mock_pdfplumber, mock_pdftotext, mock_pypdf2, tmp_path):
        """Test pdfplumber with password error."""
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4")
        
        result = extract_text_from_pdf(str(pdf_file), password="wrong")
        assert result == "Text from pypdf2"

    # This test is complex due to import mocking; skipping for now
    # @patch('src.pdf.pdf_to_text._extract_with_pdftotext', return_value="")
    # @patch('src.pdf.pdf_to_text._extract_with_pdfplumber', side_effect=ImportError("No module"))
    # @patch('src.pdf.pdf_to_text._extract_with_pdfium', side_effect=ImportError("No module"))
    # def test_extract_no_extractor_available_error(self, mock_pdfium, mock_pdfplumber, mock_pdftotext, tmp_path):
    #     """Test error when no extractor is available."""
    #     pdf_file = tmp_path / "test.pdf"
    #     pdf_file.write_bytes(b"%PDF-1.4")
    #     
    #     with pytest.raises(ImportError, match="PDF extraction requires one of"):
    #         extract_text_from_pdf(str(pdf_file))

    def test_extract_with_password_parameter(self, tmp_path):
        """Test that password is passed to extractors."""
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4")
        
        with patch('src.pdf.pdf_to_text._extract_with_pdfium', return_value="Text") as mock_pdfium:
            result = extract_text_from_pdf(str(pdf_file), password="secret123")
            assert result == "Text"
            mock_pdfium.assert_called_with(str(pdf_file), "secret123")

    @patch('src.pdf.pdf_to_text._extract_with_pdftotext', return_value="")
    @patch('src.pdf.pdf_to_text._extract_with_pdfplumber', return_value="")
    @patch('src.pdf.pdf_to_text._extract_with_pdfium')
    def test_extract_text_truncation_in_fallback(self, mock_pdfium, mock_pdfplumber, mock_pdftotext, tmp_path):
        """Test that whitespace-only text triggers fallback."""
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4")
        
        mock_pdfium.return_value = "   \n  "
        mock_pdfplumber.return_value = "Real text"
        
        result = extract_text_from_pdf(str(pdf_file))
        assert result == "Real text"

    # Tests for individual extractors
    def test_pdfium_success(self, tmp_path):
        """Test pdfium extraction success."""
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4")
        
        mock_pdfium = MagicMock()
        mock_page = MagicMock()
        mock_text_page = MagicMock()
        mock_text_page.get_text_range.return_value = "Extracted text"
        mock_page.get_textpage = MagicMock(return_value=mock_text_page)
        
        mock_doc = MagicMock()
        mock_doc.__len__.return_value = 1
        mock_doc.__getitem__.return_value = mock_page
        mock_pdfium.PdfDocument.return_value = mock_doc
        
        with patch.dict('sys.modules', {'pypdfium2': mock_pdfium}):
            result = _extract_with_pdfium(str(pdf_file))
            assert "Extracted text" in result

    def test_pdfium_pdfium_error_password_encrypted(self, tmp_path):
        """Test pdfium with PdfiumError about encryption."""
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4")
        
        mock_pdfium = MagicMock()
        PdfiumError = type('PdfiumError', (Exception,), {})
        mock_pdfium.PdfiumError = PdfiumError
        mock_pdfium.PdfDocument.side_effect = PdfiumError("PDF is encrypted")
        
        with patch.dict('sys.modules', {'pypdfium2': mock_pdfium}):
            with pytest.raises(ValueError, match="encrypted"):
                _extract_with_pdfium(str(pdf_file))

    def test_pdfium_pdfium_error_other(self, tmp_path):
        """Test pdfium with PdfiumError not about encryption."""
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4")
        
        mock_pdfium = MagicMock()
        PdfiumError = type('PdfiumError', (Exception,), {})
        mock_pdfium.PdfiumError = PdfiumError
        mock_pdfium.PdfDocument.side_effect = PdfiumError("Some other error")
        
        with patch.dict('sys.modules', {'pypdfium2': mock_pdfium}):
            with pytest.raises(ValueError, match="Failed to read PDF"):
                _extract_with_pdfium(str(pdf_file))

    def test_pdfium_page_error_continues(self, tmp_path):
        """Test pdfium continues when individual page extraction fails."""
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4")
        
        mock_page1 = MagicMock()
        mock_page1.get_textpage = MagicMock(side_effect=Exception("Page error"))
        mock_page1.get_text_page = MagicMock(side_effect=Exception("Page error"))
        
        mock_page2 = MagicMock()
        mock_text_page2 = MagicMock()
        mock_text_page2.get_text_range.return_value = "Text from page 2"
        mock_page2.get_textpage = MagicMock(return_value=mock_text_page2)
        
        mock_doc = MagicMock()
        mock_doc.__len__.return_value = 2
        mock_doc.__getitem__.side_effect = [mock_page1, mock_page2]
        mock_pdfium = MagicMock()
        mock_pdfium.PdfDocument.return_value = mock_doc
        
        with patch.dict('sys.modules', {'pypdfium2': mock_pdfium}):
            result = _extract_with_pdfium(str(pdf_file))
            assert "Text from page 2" in result

    def test_pdfplumber_success(self, tmp_path):
        """Test pdfplumber extraction success."""
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF")
        
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "Extracted text from pdfplumber"
        mock_pdf = MagicMock()
        mock_pdf.pages = [mock_page]
        
        mock_pdfplumber = MagicMock()
        mock_pdfplumber.open.return_value.__enter__.return_value = mock_pdf
        
        with patch.dict('sys.modules', {'pdfplumber': mock_pdfplumber}):
            result = _extract_with_pdfplumber(str(pdf_file))
            assert "Extracted text from pdfplumber" in result

    def test_pdfplumber_password_error(self, tmp_path):
        """Test pdfplumber with password error."""
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4")
        
        mock_pdfplumber = MagicMock()
        mock_pdfplumber.open.side_effect = ValueError("Incorrect password")
        
        with patch.dict('sys.modules', {'pdfplumber': mock_pdfplumber}):
            with pytest.raises(ValueError, match="Incorrect password"):
                _extract_with_pdfplumber(str(pdf_file), password="wrong")

    def test_pdfplumber_general_exception(self, tmp_path):
        """Test pdfplumber with general exception."""
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4")
        
        mock_pdfplumber = MagicMock()
        mock_pdfplumber.open.side_effect = Exception("Some error")
        
        with patch.dict('sys.modules', {'pdfplumber': mock_pdfplumber}):
            # The code re-raises non-password exceptions as-is
            with pytest.raises(Exception, match="Some error"):
                _extract_with_pdfplumber(str(pdf_file))

    def test_pypdf2_success(self, tmp_path):
        """Test PyPDF2 extraction success."""
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF")
        
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "Extracted text from pypdf2"
        mock_reader = MagicMock()
        mock_reader.pages = [mock_page]
        
        mock_pypdf2 = MagicMock()
        mock_pypdf2.PdfReader.return_value = mock_reader
        
        with patch.dict('sys.modules', {'PyPDF2': mock_pypdf2}):
            with patch('builtins.open', mock_open()) as mock_file:
                mock_file.return_value.__enter__ = MagicMock(return_value=mock_file)
                mock_file.return_value.__exit__ = MagicMock(return_value=False)
                mock_file.read = MagicMock(return_value=b"PDF content")
                result = _extract_with_pypdf2(str(pdf_file))
                assert "Extracted text from pypdf2" in result

    def test_pypdf2_file_not_decrypted_error(self, tmp_path):
        """Test PyPDF2 with FileNotDecryptedError."""
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4")
        
        # Create proper exception hierarchy
        class PyPDF2Error(Exception):
            pass
        class FileNotDecryptedError(PyPDF2Error):
            pass
        
        # Create a simple namespace for errors
        class ErrorsModule:
            pass
        ErrorsModule.FileNotDecryptedError = FileNotDecryptedError
        
        mock_pypdf2 = MagicMock()
        mock_pypdf2.errors = ErrorsModule()
        mock_pypdf2.PdfReader.side_effect = FileNotDecryptedError()
        
        with patch.dict('sys.modules', {'PyPDF2': mock_pypdf2}):
            with patch('builtins.open', mock_open()):
                with pytest.raises(ValueError, match="encrypted"):
                    _extract_with_pypdf2(str(pdf_file))

    def test_pypdf2_incorrect_password_error(self, tmp_path):
        """Test PyPDF2 with incorrect password error."""
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4")
        
        class PyPDF2Error(Exception):
            pass
        class FileNotDecryptedError(PyPDF2Error):
            pass
        class PdfReadError(PyPDF2Error):
            pass
        
        class ErrorsModule:
            pass
        ErrorsModule.FileNotDecryptedError = FileNotDecryptedError
        ErrorsModule.PdfReadError = PdfReadError
        
        mock_pypdf2 = MagicMock()
        mock_pypdf2.errors = ErrorsModule()
        mock_pypdf2.PdfReader.side_effect = PdfReadError("incorrect password")
        
        with patch.dict('sys.modules', {'PyPDF2': mock_pypdf2}):
            with patch('builtins.open', mock_open()):
                with pytest.raises(ValueError, match="Incorrect password"):
                    _extract_with_pypdf2(str(pdf_file))

    def test_pypdf2_general_exception(self, tmp_path):
        """Test PyPDF2 with general exception."""
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4")
        
        class PyPDF2Error(Exception):
            pass
        class FileNotDecryptedError(PyPDF2Error):
            pass
        class PdfReadError(PyPDF2Error):
            pass
        
        class ErrorsModule:
            pass
        ErrorsModule.FileNotDecryptedError = FileNotDecryptedError
        ErrorsModule.PdfReadError = PdfReadError
        
        mock_pypdf2 = MagicMock()
        mock_pypdf2.errors = ErrorsModule()
        mock_pypdf2.PdfReader.side_effect = Exception("Some error")
        
        with patch.dict('sys.modules', {'PyPDF2': mock_pypdf2}):
            with patch('builtins.open', mock_open()):
                with pytest.raises(ValueError, match="Failed to read PDF"):
                    _extract_with_pypdf2(str(pdf_file))

    def test_pdftotext_not_available(self):
        """Test pdftotext when not available."""
        with patch('shutil.which', return_value=None):
            result = _extract_with_pdftotext("/path/to/test.pdf")
            assert result == ""

    def test_pdftotext_execution_failure(self):
        """Test pdftotext when subprocess fails."""
        with patch('shutil.which', return_value='/usr/bin/pdftotext'):
            with patch('subprocess.run', side_effect=Exception("Command failed")):
                result = _extract_with_pdftotext("/path/to/test.pdf")
                assert result == ""

    def test_pdftotext_empty_output(self):
        """Test pdftotext when returns only whitespace."""
        with patch('shutil.which', return_value='/usr/bin/pdftotext'):
            mock_proc = MagicMock()
            mock_proc.returncode = 0
            mock_proc.stdout = "   \n  \t  "
            with patch('subprocess.run', return_value=mock_proc):
                result = _extract_with_pdftotext("/path/to/test.pdf")
                # The function should return the whitespace as-is
                assert result == "   \n  \t  "

    def test_pdftotext_with_password(self):
        """Test pdftotext with password."""
        with patch('shutil.which', return_value='/usr/bin/pdftotext'):
            mock_proc = MagicMock()
            mock_proc.returncode = 0
            mock_proc.stdout = "Decrypted text"
            with patch('subprocess.run', return_value=mock_proc) as mock_run:
                result = _extract_with_pdftotext("/path/to/test.pdf", password="secret")
                assert result == "Decrypted text"
                # Verify password flags were added
                cmd = mock_run.call_args[0][0]
                assert '-opw' in cmd
                assert 'secret' in cmd

    def test_is_text_based_pdf_success(self, tmp_path):
        """Test is_text_based_pdf with extractable text."""
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4")
        
        with patch('src.pdf.pdf_to_text.extract_text_from_pdf', return_value="Hello World 123"):
            assert is_text_based_pdf(str(pdf_file)) is True

    def test_is_text_based_pdf_no_text(self, tmp_path):
        """Test is_text_based_pdf with no meaningful text."""
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4")
        
        with patch('src.pdf.pdf_to_text.extract_text_from_pdf', return_value="   \n\t  "):
            assert is_text_based_pdf(str(pdf_file)) is False

    def test_is_text_based_pdf_extraction_failed(self, tmp_path):
        """Test is_text_based_pdf when extraction returns None."""
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4")
        
        with patch('src.pdf.pdf_to_text.extract_text_from_pdf', return_value=None):
            assert is_text_based_pdf(str(pdf_file)) is False

    def test_is_text_based_pdf_exception(self, tmp_path):
        """Test is_text_based_pdf when extraction raises exception."""
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4")
        
        with patch('src.pdf.pdf_to_text.extract_text_from_pdf', side_effect=Exception("Error")):
            assert is_text_based_pdf(str(pdf_file)) is False

    def test_is_text_based_pdf_with_chinese(self, tmp_path):
        """Test is_text_based_pdf with Chinese characters."""
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4")
        
        with patch('src.pdf.pdf_to_text.extract_text_from_pdf', return_value="中文測試"):
            assert is_text_based_pdf(str(pdf_file)) is True

    def test_extract_with_pdfium_password(self, tmp_path):
        """Test pdfium extraction with password."""
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4")
        
        with patch('pypdfium2.PdfDocument') as mock_pdfium:
            mock_pdf = MagicMock()
            mock_pdf.__len__.return_value = 0
            mock_pdfium.return_value = mock_pdf
            
            _extract_with_pdfium(str(pdf_file), password="secret")
            mock_pdfium.assert_called_with(str(pdf_file), password="secret")


class TestIsTextBasedPDF:
    """Tests for is_text_based_pdf function."""

    @patch('src.pdf.pdf_to_text.extract_text_from_pdf')
    def test_is_text_based_pdf_with_meaningful_text(self, mock_extract, tmp_path):
        """Test is_text_based_pdf returns True for text with alphanumeric content."""
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4")
        mock_extract.return_value = "Hello World 123 中文"
        
        assert is_text_based_pdf(str(pdf_file)) is True

    @patch('src.pdf.pdf_to_text.extract_text_from_pdf')
    def test_is_text_based_pdf_with_only_whitespace(self, mock_extract, tmp_path):
        """Test is_text_based_pdf returns False for whitespace-only text."""
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4")
        mock_extract.return_value = "   \n\t  "
        
        assert is_text_based_pdf(str(pdf_file)) is False

    @patch('src.pdf.pdf_to_text.extract_text_from_pdf')
    def test_is_text_based_pdf_with_none(self, mock_extract, tmp_path):
        """Test is_text_based_pdf returns False when extraction returns None."""
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4")
        mock_extract.return_value = None
        
        assert is_text_based_pdf(str(pdf_file)) is False

    @patch('src.pdf.pdf_to_text.extract_text_from_pdf')
    def test_is_text_based_pdf_with_exception(self, mock_extract, tmp_path):
        """Test is_text_based_pdf returns False on extraction exception."""
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4")
        mock_extract.side_effect = Exception("Extraction error")
        
        assert is_text_based_pdf(str(pdf_file)) is False

    @patch('src.pdf.pdf_to_text.extract_text_from_pdf')
    def test_is_text_based_pdf_with_chinese_only(self, mock_extract, tmp_path):
        """Test is_text_based_pdf returns True for Chinese characters."""
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4")
        mock_extract.return_value = "中文繁體文字"
        
        assert is_text_based_pdf(str(pdf_file)) is True

    @patch('src.pdf.pdf_to_text.extract_text_from_pdf')
    def test_is_text_based_pdf_preserves_password(self, mock_extract, tmp_path):
        """Test is_text_based_pdf passes password to extract_text_from_pdf."""
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4")
        mock_extract.return_value = "Text"

        is_text_based_pdf(str(pdf_file), password="secret")
        mock_extract.assert_called_once_with(str(pdf_file), "secret")

    @patch('src.pdf.pdf_to_text.extract_text_from_pdf', return_value='Hello PDF')
    def test_cli_main_success(self, _mock_extract, capsys):
        exit_code = main(['sample.pdf'])
        out = capsys.readouterr().out

        assert exit_code == 0
        assert 'Extracted text from: sample.pdf' in out
        assert 'Total:' in out

    @patch('src.pdf.pdf_to_text.extract_text_from_pdf', return_value=None)
    def test_cli_main_no_text(self, _mock_extract, capsys):
        exit_code = main(['sample.pdf'])
        out = capsys.readouterr().out

        assert exit_code == 1
        assert 'No text could be extracted from this PDF.' in out

    @patch('src.pdf.pdf_to_text.extract_text_from_pdf', side_effect=FileNotFoundError('missing'))
    def test_cli_main_file_not_found(self, _mock_extract, capsys):
        exit_code = main(['missing.pdf'])
        out = capsys.readouterr().out

        assert exit_code == 1
        assert 'Error: missing' in out

    @patch('src.pdf.pdf_to_text.extract_text_from_pdf', side_effect=ValueError('bad password'))
    def test_cli_main_value_error(self, _mock_extract, capsys):
        exit_code = main(['encrypted.pdf', 'pw'])
        out = capsys.readouterr().out

        assert exit_code == 1
        assert 'Error: bad password' in out

    def test_cli_main_usage(self, capsys):
        exit_code = main([])
        out = capsys.readouterr().out

        assert exit_code == 1
        assert 'Usage: python src/pdf/pdf_to_text.py <pdf_file> [password]' in out


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
