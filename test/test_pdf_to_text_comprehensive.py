"""Additional branch-coverage tests for src/pdf/pdf_to_text.py."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import src.parsing.pdf.pdf_to_text as pdfmod


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
