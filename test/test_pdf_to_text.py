import pytest
import src.parsing.pdf.pdf_to_text as pdfmod
from unittest.mock import MagicMock, patch
from src.parsing.pdf.pdf_to_text import extract_text_from_pdf, _extract_with_pdfium, _extract_with_pdfplumber


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


class TestExtractTextFromPdfBranches:
    def test_pdfplumber_importerror_falls_back_to_pdfium(self, tmp_path):
        pdf_file = tmp_path / "a.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 test")

        with patch("src.parsing.pdf.pdf_to_text._extract_with_pdfplumber", side_effect=ImportError("no pdfplumber")), \
             patch("src.parsing.pdf.pdf_to_text._extract_with_pdfium", return_value="from pdfium"):
            out = pdfmod.extract_text_from_pdf(str(pdf_file))

        assert out == "from pdfium"

    def test_last_exception_is_raised_when_all_engines_fail(self, tmp_path):
        pdf_file = tmp_path / "a.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 test")

        with patch("src.parsing.pdf.pdf_to_text._extract_with_pdfplumber", return_value=""), \
             patch("src.parsing.pdf.pdf_to_text._extract_with_pdfium", side_effect=ImportError("missing")):
            with pytest.raises(ImportError, match="missing"):
                pdfmod.extract_text_from_pdf(str(pdf_file))

    def test_all_extractors_empty_with_password_returns_none(self, tmp_path):
        pdf_file = tmp_path / "enc.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 encrypted")

        with patch("src.parsing.pdf.pdf_to_text._extract_with_pdfium", return_value=""), \
             patch("src.parsing.pdf.pdf_to_text._extract_with_pdfplumber", return_value=""):
            out = pdfmod.extract_text_from_pdf(str(pdf_file), password="secret")

        assert out is None


class TestPdfiumBranches:
    def test_pdfium_page_without_textpage_getter_and_close_exceptions(self):
        # PdfPage has no get_textpage/get_text_page -> line 137 path
        mock_pdfium = MagicMock()
        mock_pdfium.PdfiumError = type("PdfiumError", (Exception,), {})

        class BadPage:
            def close(self):
                raise RuntimeError("close fail")

        bad_page = BadPage()

        doc = MagicMock()
        doc.__len__.return_value = 1
        doc.__getitem__.return_value = bad_page
        mock_pdfium.PdfDocument.return_value = doc

        with patch.dict("sys.modules", {"pypdfium2": mock_pdfium}):
            out = pdfmod._extract_with_pdfium("/tmp/a.pdf")

        assert out == ""

    def test_pdfium_textpage_close_exception_is_ignored(self):
        mock_pdfium = MagicMock()
        mock_pdfium.PdfiumError = type("PdfiumError", (Exception,), {})

        text_page = MagicMock()
        text_page.get_text_range.return_value = "ok"
        text_page.close.side_effect = RuntimeError("tp close fail")

        page = MagicMock()
        page.get_textpage = MagicMock(return_value=text_page)
        page.close.side_effect = RuntimeError("page close fail")

        doc = MagicMock()
        doc.__len__.return_value = 1
        doc.__getitem__.return_value = page
        mock_pdfium.PdfDocument.return_value = doc

        with patch.dict("sys.modules", {"pypdfium2": mock_pdfium}):
            out = pdfmod._extract_with_pdfium("/tmp/a.pdf")

        assert "ok" in out

    def test_pdfium_encrypted_error_and_unexpected_error(self):
        mock_pdfium = MagicMock()
        PdfiumError = type("PdfiumError", (Exception,), {})
        mock_pdfium.PdfiumError = PdfiumError

        with patch.dict("sys.modules", {"pypdfium2": mock_pdfium}):
            mock_pdfium.PdfDocument.side_effect = PdfiumError("encrypted password")
            with pytest.raises(ValueError, match="encrypted"):
                pdfmod._extract_with_pdfium("/tmp/a.pdf")

            mock_pdfium.PdfDocument.side_effect = RuntimeError("boom")
            with pytest.raises(ValueError, match="Unexpected error"):
                pdfmod._extract_with_pdfium("/tmp/a.pdf")


class TestPdfplumberBranches:
    def test_pdfplumber_page_extract_exception_continue(self, tmp_path):
        pdf_path = tmp_path / "a.pdf"
        pdf_path.write_bytes(b"%PDF")

        mock_pdfplumber = MagicMock()
        bad_page = MagicMock()
        bad_page.extract_text.side_effect = RuntimeError("bad page")
        pdf_obj = MagicMock()
        pdf_obj.pages = [bad_page]
        mock_pdfplumber.open.return_value.__enter__.return_value = pdf_obj

        with patch.dict("sys.modules", {"pdfplumber": mock_pdfplumber}):
            out = pdfmod._extract_with_pdfplumber(str(pdf_path))

        assert out == ""

    def test_pdfplumber_password_errors(self, tmp_path):
        pdf_path = tmp_path / "a.pdf"
        pdf_path.write_bytes(b"%PDF")

        mock_pdfplumber = MagicMock()
        mock_pdfplumber.open.side_effect = Exception("Incorrect password")
        with patch.dict("sys.modules", {"pdfplumber": mock_pdfplumber}):
            with pytest.raises(ValueError, match="Incorrect password"):
                pdfmod._extract_with_pdfplumber(str(pdf_path), password="pw")
