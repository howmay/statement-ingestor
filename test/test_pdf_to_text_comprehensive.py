"""Additional branch-coverage tests for src/pdf/pdf_to_text.py."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import src.parsing.pdf.pdf_to_text as pdfmod


class TestExtractTextFromPdfBranches:
    def test_pdfium_importerror_branch_then_pdftotext_success(self, tmp_path):
        pdf_file = tmp_path / "a.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 test")

        with patch("src.parsing.pdf.pdf_to_text._extract_with_pdfium", side_effect=ImportError("no pdfium")), \
             patch("src.parsing.pdf.pdf_to_text._extract_with_pdftotext", return_value="from pdftotext"):
            out = pdfmod.extract_text_from_pdf(str(pdf_file))

        assert out == "from pdftotext"

    def test_pdftotext_exception_then_pdfplumber_success(self, tmp_path):
        pdf_file = tmp_path / "a.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 test")

        with patch("src.parsing.pdf.pdf_to_text._extract_with_pdfium", return_value=""), \
             patch("src.parsing.pdf.pdf_to_text._extract_with_pdftotext", side_effect=RuntimeError("cli fail")), \
             patch("src.parsing.pdf.pdf_to_text._extract_with_pdfplumber", return_value="from pdfplumber"):
            out = pdfmod.extract_text_from_pdf(str(pdf_file))

        assert out == "from pdfplumber"

    def test_pdfplumber_importerror_fallback_to_pypdf2(self, tmp_path):
        pdf_file = tmp_path / "a.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 test")

        with patch("src.parsing.pdf.pdf_to_text._extract_with_pdfium", return_value=""), \
             patch("src.parsing.pdf.pdf_to_text._extract_with_pdftotext", return_value=""), \
             patch("src.parsing.pdf.pdf_to_text._extract_with_pdfplumber", side_effect=ImportError("no pdfplumber")), \
             patch("src.parsing.pdf.pdf_to_text._extract_with_pypdf2", return_value="from pypdf2"):
            out = pdfmod.extract_text_from_pdf(str(pdf_file))

        assert out == "from pypdf2"

    def test_pypdf2_importerror_raises(self, tmp_path):
        pdf_file = tmp_path / "a.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 test")

        with patch("src.parsing.pdf.pdf_to_text._extract_with_pdfium", return_value=""), \
             patch("src.parsing.pdf.pdf_to_text._extract_with_pdftotext", return_value=""), \
             patch("src.parsing.pdf.pdf_to_text._extract_with_pdfplumber", return_value=""), \
             patch("src.parsing.pdf.pdf_to_text._extract_with_pypdf2", side_effect=ImportError("missing")):
            with pytest.raises(ImportError):
                pdfmod.extract_text_from_pdf(str(pdf_file))

    def test_all_extractors_fail_with_password_logs_encrypted_warning(self, tmp_path):
        pdf_file = tmp_path / "enc.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 encrypted")

        with patch("src.parsing.pdf.pdf_to_text._extract_with_pdfium", return_value=""), \
             patch("src.parsing.pdf.pdf_to_text._extract_with_pdftotext", return_value=""), \
             patch("src.parsing.pdf.pdf_to_text._extract_with_pdfplumber", return_value=""), \
             patch("src.parsing.pdf.pdf_to_text._extract_with_pypdf2", return_value=""):
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


class TestPdftotextBranches:
    def test_pdftotext_not_installed_returns_empty(self):
        with patch("shutil.which", return_value=None):
            assert pdfmod._extract_with_pdftotext("/tmp/a.pdf") == ""

    def test_pdftotext_password_args_and_exception(self):
        proc = SimpleNamespace(returncode=0, stdout="ok")
        with patch("shutil.which", return_value="/usr/bin/pdftotext"), \
             patch("subprocess.run", return_value=proc) as run_mock:
            out = pdfmod._extract_with_pdftotext("/tmp/a.pdf", password="pw")
            assert out == "ok"
            cmd = run_mock.call_args[0][0]
            assert "-opw" in cmd and "-upw" in cmd

        with patch("shutil.which", return_value="/usr/bin/pdftotext"), \
             patch("subprocess.run", side_effect=RuntimeError("fail")):
            assert pdfmod._extract_with_pdftotext("/tmp/a.pdf") == ""


class TestPdfplumberAndPypdf2Branches:
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

    def test_pypdf2_error_branches(self, tmp_path):
        pdf_path = tmp_path / "a.pdf"
        pdf_path.write_bytes(b"%PDF")

        mock_pypdf2 = MagicMock()
        FileNotDecryptedError = type("FileNotDecryptedError", (Exception,), {})
        PdfReadError = type("PdfReadError", (Exception,), {})
        mock_pypdf2.errors = SimpleNamespace(
            FileNotDecryptedError=FileNotDecryptedError,
            PdfReadError=PdfReadError,
        )

        with patch.dict("sys.modules", {"PyPDF2": mock_pypdf2}):
            mock_pypdf2.PdfReader.side_effect = FileNotDecryptedError()
            with pytest.raises(ValueError, match="encrypted"):
                pdfmod._extract_with_pypdf2(str(pdf_path))

            mock_pypdf2.PdfReader.side_effect = PdfReadError("incorrect password")
            with pytest.raises(ValueError, match="Incorrect password"):
                pdfmod._extract_with_pypdf2(str(pdf_path), password="pw")

            mock_pypdf2.PdfReader.side_effect = RuntimeError("other")
            with pytest.raises(ValueError, match="Failed to read PDF"):
                pdfmod._extract_with_pypdf2(str(pdf_path))

    def test_pypdf2_page_extract_exception_continue(self, tmp_path):
        pdf_path = tmp_path / "a.pdf"
        pdf_path.write_bytes(b"%PDF")

        mock_pypdf2 = MagicMock()
        mock_pypdf2.errors = SimpleNamespace(
            FileNotDecryptedError=type("FileNotDecryptedError", (Exception,), {}),
            PdfReadError=type("PdfReadError", (Exception,), {}),
        )

        page = MagicMock()
        page.extract_text.side_effect = RuntimeError("bad page")
        reader = MagicMock()
        reader.pages = [page]
        mock_pypdf2.PdfReader.return_value = reader

        with patch.dict("sys.modules", {"PyPDF2": mock_pypdf2}):
            out = pdfmod._extract_with_pypdf2(str(pdf_path))

        assert out == ""


class TestIsTextBasedAndCliMain:
    def test_is_text_based_none_and_exception(self):
        with patch("src.parsing.pdf.pdf_to_text.extract_text_from_pdf", return_value=None):
            assert pdfmod.is_text_based_pdf("/tmp/a.pdf") is False

        with patch("src.parsing.pdf.pdf_to_text.extract_text_from_pdf", side_effect=RuntimeError("x")):
            assert pdfmod.is_text_based_pdf("/tmp/a.pdf") is False

    def test_main_usage_and_success_and_error_paths(self, capsys):
        assert pdfmod.main([]) == 1
        assert "Usage:" in capsys.readouterr().out

        with patch("src.parsing.pdf.pdf_to_text.extract_text_from_pdf", return_value="hello"):
            assert pdfmod.main(["a.pdf"]) == 0
            out = capsys.readouterr().out
            assert "Extracted text from: a.pdf" in out
            assert "Total:" in out

        long_text = "x" * 600
        with patch("src.parsing.pdf.pdf_to_text.extract_text_from_pdf", return_value=long_text):
            assert pdfmod.main(["a.pdf", "pw"]) == 0
            out = capsys.readouterr().out
            assert "Using password:" in out
            assert "more characters" in out

        with patch("src.parsing.pdf.pdf_to_text.extract_text_from_pdf", return_value=None):
            assert pdfmod.main(["a.pdf"]) == 1
            out = capsys.readouterr().out
            assert "No text could be extracted" in out

        with patch("src.parsing.pdf.pdf_to_text.extract_text_from_pdf", side_effect=FileNotFoundError("missing")):
            assert pdfmod.main(["a.pdf"]) == 1
            out = capsys.readouterr().out
            assert "Error: missing" in out

        with patch("src.parsing.pdf.pdf_to_text.extract_text_from_pdf", side_effect=ValueError("bad")):
            assert pdfmod.main(["a.pdf"]) == 1
            out = capsys.readouterr().out
            assert "Error: bad" in out

        with patch("src.parsing.pdf.pdf_to_text.extract_text_from_pdf", side_effect=RuntimeError("boom")):
            assert pdfmod.main(["a.pdf"]) == 1
            out = capsys.readouterr().out
            assert "Unexpected error: boom" in out
