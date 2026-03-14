"""
Comprehensive tests for the current Gmail PDF downloads API.
"""
import base64
import hashlib
from unittest.mock import Mock, mock_open, patch

import pytest

from src.integrations.gmail.downloads import (
    batch_download_pdfs,
    build_pdf_filename_by_sender,
    compute_md5_hash,
    download_attachment,
    download_pdf_attachments,
    extract_sender_display_name,
    extract_sender_tag,
    get_existing_file_by_md5,
)


class TestDownloadPDFsComprehensive:
    @pytest.fixture(autouse=True)
    def mock_retry(self):
        with patch("src.support.retry.retry_gmail", side_effect=lambda f: f):
            yield

    def test_extract_sender_tag_edge_cases(self):
        assert extract_sender_tag("") == "unknown"
        assert extract_sender_tag("bankstatement") == "bankstatement"
        assert extract_sender_tag("test@test@example.com") == "test"
        assert extract_sender_tag("bank-statement@example.com") == "example_com"
        assert extract_sender_tag("service@esunbank.com.tw") == "_bank"

    def test_extract_sender_display_name_and_filename_builder(self):
        assert extract_sender_display_name('"HSBC Bank" <service@hsbc.com>') == "HSBC_Bank"

        filename = build_pdf_filename_by_sender("bank@example.com", "statement.pdf")
        assert filename.startswith("bank_")
        assert filename.endswith(".pdf")

        filename_with_data = build_pdf_filename_by_sender(
            "bank@example.com",
            "statement.pdf",
            b"fake pdf content",
        )
        assert filename_with_data.startswith("bank_")
        assert filename_with_data.endswith(".pdf")
        assert filename != filename_with_data

    def test_compute_md5_hash(self):
        data = b"test data"
        assert compute_md5_hash(data) == hashlib.md5(data).hexdigest()

    @patch("src.integrations.gmail.downloads.os.path.isfile", return_value=True)
    @patch("src.integrations.gmail.downloads.os.listdir", return_value=["file1.pdf"])
    @patch("src.integrations.gmail.downloads.os.path.exists", return_value=True)
    def test_get_existing_file_by_md5(self, _exists, _listdir, _isfile):
        data = b"file content"
        target_md5 = hashlib.md5(data).hexdigest()

        with patch("builtins.open", mock_open(read_data=data)):
            result = get_existing_file_by_md5(target_md5, "/tmp")

        assert result == "/tmp/file1.pdf"

    @patch("src.integrations.gmail.downloads.DOWNLOAD_DIR", "/tmp/downloads")
    @patch("src.integrations.gmail.downloads.os.makedirs")
    @patch("src.integrations.gmail.downloads.get_existing_file_by_md5")
    @patch("src.integrations.gmail.downloads.os.path.exists", return_value=False)
    @patch("builtins.open", new_callable=mock_open)
    def test_download_attachment_success(self, _open, _exists, _get_existing, _makedirs):
        _get_existing.return_value = None
        mock_service = Mock()
        attachment_info = {"attachmentId": "att1", "filename": "statement.pdf"}
        payload = base64.urlsafe_b64encode(b"fake pdf data").decode("utf-8")
        mock_service.users().messages().attachments().get().execute.return_value = {"data": payload}

        result = download_attachment(mock_service, "msg1", attachment_info, "bank@example.com")

        assert result.startswith("/tmp/downloads/bank_")
        assert result.endswith(".pdf")

    @patch("src.integrations.gmail.downloads.download_attachment")
    @patch("src.integrations.gmail.downloads.extract_sender_tag", return_value="tag")
    @patch("src.integrations.gmail.downloads.list_attachments")
    def test_download_pdf_attachments_returns_metadata_dicts(self, mock_list, _tag, mock_download):
        mock_service = Mock()
        mock_list.return_value = [{"attachmentId": "a1", "filename": "f1.pdf"}]
        mock_download.return_value = "/tmp/f1.pdf"
        email_metadata = {"sender": "bank@example.com", "subject": "Statement"}

        results = download_pdf_attachments(mock_service, "msg1", email_metadata)

        assert len(results) == 1
        assert results[0]["filepath"] == "/tmp/f1.pdf"
        assert results[0]["filename"] == "f1.pdf"
        assert results[0]["sender"] == "bank@example.com"
        assert results[0]["sender_tag"] == "tag"
        assert results[0]["message_id"] == "msg1"

    @patch("src.integrations.gmail.downloads.download_attachment")
    @patch("src.integrations.gmail.downloads.list_attachments")
    def test_download_pdf_attachments_skips_failed_attachment(self, mock_list, mock_download):
        mock_service = Mock()
        mock_list.return_value = [
            {"attachmentId": "a1", "filename": "f1.pdf"},
            {"attachmentId": "a2", "filename": "f2.pdf"},
        ]
        mock_download.side_effect = ["/tmp/f1.pdf", IOError("download failed")]

        results = download_pdf_attachments(mock_service, "msg1", {"sender": "bank@example.com"})

        assert len(results) == 1
        assert results[0]["filepath"] == "/tmp/f1.pdf"

    @patch("src.integrations.gmail.downloads.download_pdf_attachments")
    def test_batch_download_pdfs_flattens_results(self, mock_download):
        mock_service = Mock()
        emails = [{"id": "msg1"}, {"id": "msg2"}]
        mock_download.side_effect = [
            [{"filepath": "/tmp/f1.pdf", "filename": "f1.pdf"}],
            [{"filepath": "/tmp/f2.pdf", "filename": "f2.pdf"}],
        ]

        results = batch_download_pdfs(mock_service, emails)

        assert [item["filepath"] for item in results] == ["/tmp/f1.pdf", "/tmp/f2.pdf"]

    @patch("src.integrations.gmail.downloads.download_pdf_attachments", side_effect=RuntimeError("boom"))
    def test_batch_download_pdfs_propagates_email_failure(self, mock_download):
        mock_service = Mock()
        emails = [{"id": "msg1"}]

        with pytest.raises(RuntimeError, match="boom"):
            batch_download_pdfs(mock_service, emails)

        mock_download.assert_called_once()
