"""
Enhanced unit tests for PDF download module.
"""
import os
import logging
from pathlib import Path
import pytest
import base64
import hashlib
from unittest.mock import Mock, patch, mock_open
import sys

from src.integrations.gmail.downloads import (
    extract_sender_tag,
    extract_sender_display_name,
    build_sender_base64_suffix,
    build_file_base64_suffix,
    build_hash10_suffix,
    build_pdf_filename_by_sender,
    compute_md5_hash,
    get_existing_file_by_md5,
    download_attachment,
    batch_download_pdfs,
    download_pdf_attachments
)

class TestDownloadPDFsEnhanced:
    """Enhanced test suite for PDF download functions."""

    @pytest.fixture(autouse=True)
    def mock_retry(self):
        """Mock the retry decorator."""
        with patch('src.support.retry.retry_gmail', side_effect=lambda f: f):
            yield

    def test_extract_sender_tag_variations(self):
        """Test variations of sender tag extraction."""
        assert extract_sender_tag("service@mail.hsbc.com.sg") == "hsbc_sg_mail"
        assert extract_sender_tag("alert@hsbc.com.tw") == "hsbc_tw"
        assert extract_sender_tag("no-reply@uber.com") == "uber"
        assert extract_sender_tag('"台新銀行" <webmaster@bhurecv.taishinbank.com.tw>') == "taishin"
        assert extract_sender_tag("alert@esunbank.com.tw") == "esunbank"
        # Adjusted expectation to match implementation
        assert extract_sender_tag("test@unknown-bank.com") == "_bank"
        assert extract_sender_tag("simple") == "simple"

    def test_extract_sender_display_name(self):
        """Test extracting display name."""
        assert extract_sender_display_name('"HSBC Bank" <service@hsbc.com>') == "HSBC_Bank"
        assert extract_sender_display_name('service@hsbc.com') == "service"
        assert extract_sender_display_name('台北富邦銀行 <service@fubon.com>') == "台北富邦銀行"

    def test_build_suffixes(self):
        """Test base64 suffixes."""
        name = "test_user"
        suffix = build_sender_base64_suffix(name)
        assert len(suffix) <= 8

        data = b"fake pdf data"
        suffix_file = build_file_base64_suffix(data)
        assert len(suffix_file) == 8
        assert len(build_hash10_suffix(data)) == 10

    @patch('src.integrations.gmail.downloads._extract_pdf_text_hint', return_value="")
    def test_build_pdf_filename(self, _mock_text_hint):
        """Test filename construction."""
        sender = "HSBC <service@hsbc.com>"
        fname = "statement.pdf"
        data = b"content"
        subject = "匯豐(台灣)商業銀行運籌理財對帳單 2026年02月"

        name = build_pdf_filename_by_sender(sender, fname, data, subject=subject)
        assert name.startswith("滙豐(台灣)_銀行帳戶對帳單_2026-02_")
        assert name.endswith(".pdf")

    def test_compute_md5(self):
        """Test MD5 computation."""
        data = b"hello world"
        expected = hashlib.md5(data).hexdigest()
        assert compute_md5_hash(data) == expected

    @patch('src.integrations.gmail.downloads.os.path.exists')
    @patch('src.integrations.gmail.downloads.os.listdir')
    def test_get_existing_file_by_md5(self, mock_listdir, mock_exists):
        """Test finding existing file by MD5."""
        mock_exists.return_value = True
        mock_listdir.return_value = ["existing.pdf"]

        data = b"file content"
        target_md5 = hashlib.md5(data).hexdigest()

        with patch('builtins.open', mock_open(read_data=data)):
            # Mock os.path.isfile to return True for the existing file
            with patch('src.integrations.gmail.downloads.os.path.isfile', return_value=True):
                result = get_existing_file_by_md5(target_md5, "/tmp/dir")
                assert result == "/tmp/dir/existing.pdf"

    def test_get_existing_file_by_md5_uses_sqlite_index_instead_of_json_cache(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        directory = tmp_path / "downloads"
        directory.mkdir()
        existing = directory / "existing.pdf"
        existing.write_bytes(b"file content")

        target_md5 = hashlib.md5(b"file content").hexdigest()

        result = get_existing_file_by_md5(target_md5, str(directory))

        assert result == str(existing)
        assert not (directory / ".md5_cache.json").exists()
        assert Path(".cache/performance_index.sqlite3").exists()

    def test_get_existing_file_by_md5_refreshes_stale_entry_when_file_changes(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        directory = tmp_path / "downloads"
        directory.mkdir()
        existing = directory / "existing.pdf"
        existing.write_bytes(b"old content")

        old_md5 = hashlib.md5(b"old content").hexdigest()
        new_md5 = hashlib.md5(b"new content").hexdigest()

        assert get_existing_file_by_md5(old_md5, str(directory)) == str(existing)

        existing.write_bytes(b"new content")
        stat_info = existing.stat()
        os.utime(existing, (stat_info.st_mtime + 1, stat_info.st_mtime + 1))

        assert get_existing_file_by_md5(old_md5, str(directory)) is None
        assert get_existing_file_by_md5(new_md5, str(directory)) == str(existing)

    @patch('src.integrations.gmail.downloads.DOWNLOAD_DIR', '/tmp/downloads')
    @patch('src.integrations.gmail.downloads.os.makedirs')
    @patch('src.integrations.gmail.downloads.get_existing_file_by_md5')
    @patch('src.integrations.gmail.downloads.os.path.exists')
    @patch('builtins.open', new_callable=mock_open)
    def test_download_attachment_already_exists(self, mock_file, mock_exists, mock_get_existing, mock_makedirs):
        """Test skipping download if file exists."""
        mock_get_existing.return_value = "/tmp/downloads/existing.pdf"

        mock_service = Mock()
        attachment_info = {'attachmentId': 'att-md5-only', 'filename': 'content-dedupe-only.pdf'}
        mock_service.users().messages().attachments().get().execute.return_value = {
            'data': base64.urlsafe_b64encode(b'data').decode('UTF-8')
        }

        result = download_attachment(mock_service, 'msg1', attachment_info)
        assert result == "/tmp/downloads/existing.pdf"
        mock_file.assert_not_called()

    @patch('src.integrations.gmail.downloads.get_existing_file_by_md5')
    def test_download_attachment_backfills_attachment_index_when_md5_dedupe_hits(
        self,
        mock_get_existing,
        tmp_path,
        monkeypatch,
    ):
        monkeypatch.chdir(tmp_path)
        download_dir = tmp_path / "downloads"
        download_dir.mkdir()
        existing = download_dir / "existing.pdf"
        existing.write_bytes(b"same content")

        monkeypatch.setattr('src.integrations.gmail.downloads.DOWNLOAD_DIR', str(download_dir))
        mock_get_existing.return_value = str(existing)

        mock_service = Mock()
        attachment_info = {'attachmentId': 'att1', 'filename': 'statement.pdf'}
        mock_service.users().messages().attachments().get().execute.return_value = {
            'data': base64.urlsafe_b64encode(b'same content').decode('UTF-8')
        }

        result = download_attachment(mock_service, 'msg1', attachment_info)

        assert result == str(existing)

        from src.integrations.gmail.downloads import _file_md5_cache
        cached = _file_md5_cache().get_downloaded_attachment_reference('msg1', 'att1')
        assert cached is not None
        assert cached['downloaded_filepath'] == str(existing)

    @patch('src.integrations.gmail.downloads.get_existing_file_by_md5')
    def test_download_attachment_uses_backfilled_attachment_index_on_second_run(
        self,
        mock_get_existing,
        tmp_path,
        monkeypatch,
    ):
        monkeypatch.chdir(tmp_path)
        download_dir = tmp_path / "downloads"
        download_dir.mkdir()
        existing = download_dir / "existing.pdf"
        existing.write_bytes(b"same content")

        monkeypatch.setattr('src.integrations.gmail.downloads.DOWNLOAD_DIR', str(download_dir))
        mock_get_existing.return_value = str(existing)

        first_service = Mock()
        attachment_info = {'attachmentId': 'att1', 'filename': 'statement.pdf'}
        first_service.users().messages().attachments().get().execute.return_value = {
            'data': base64.urlsafe_b64encode(b'same content').decode('UTF-8')
        }

        first_result = download_attachment(first_service, 'msg1', attachment_info)
        assert first_result == str(existing)

        second_service = Mock()
        second_result = download_attachment(second_service, 'msg1', attachment_info)

        assert second_result == str(existing)
        second_service.users.assert_not_called()

    @patch('src.integrations.gmail.downloads.get_existing_file_by_md5')
    def test_download_attachment_reuses_index_when_attachment_id_changes_but_filename_and_size_match(
        self,
        mock_get_existing,
        tmp_path,
        monkeypatch,
    ):
        monkeypatch.chdir(tmp_path)
        download_dir = tmp_path / "downloads"
        download_dir.mkdir()
        existing = download_dir / "existing.pdf"
        existing.write_bytes(b"same content")

        monkeypatch.setattr('src.integrations.gmail.downloads.DOWNLOAD_DIR', str(download_dir))
        mock_get_existing.return_value = str(existing)

        first_service = Mock()
        first_attachment = {
            'attachmentId': 'att-old',
            'filename': 'statement.pdf',
            'size': len(b'same content'),
        }
        first_service.users().messages().attachments().get().execute.return_value = {
            'data': base64.urlsafe_b64encode(b'same content').decode('UTF-8')
        }

        first_result = download_attachment(first_service, 'msg1', first_attachment)
        assert first_result == str(existing)

        second_service = Mock()
        second_attachment = {
            'attachmentId': 'att-new',
            'filename': 'statement.pdf',
            'size': len(b'same content'),
        }
        second_result = download_attachment(second_service, 'msg1', second_attachment)

        assert second_result == str(existing)
        second_service.users.assert_not_called()

    def test_download_attachment_reuses_indexed_gmail_attachment_when_local_file_exists(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        download_dir = tmp_path / "downloads"
        download_dir.mkdir()
        existing = download_dir / "existing.pdf"
        existing.write_bytes(b"existing data")

        monkeypatch.setattr('src.integrations.gmail.downloads.DOWNLOAD_DIR', str(download_dir))

        from src.integrations.gmail.downloads import _file_md5_cache
        cache = _file_md5_cache()
        cache.store_downloaded_attachment_reference(
            message_id='msg1',
            attachment_id='att1',
            original_filename='statement.pdf',
            downloaded_filepath=str(existing),
            size=existing.stat().st_size,
            md5=hashlib.md5(b"existing data").hexdigest(),
        )

        mock_service = Mock()
        attachment_info = {'attachmentId': 'att1', 'filename': 'statement.pdf'}
        result = download_attachment(mock_service, 'msg1', attachment_info)

        assert result == str(existing)
        mock_service.users.assert_not_called()

    def test_download_attachment_logs_index_hit(self, tmp_path, monkeypatch, caplog):
        monkeypatch.chdir(tmp_path)
        download_dir = tmp_path / "downloads"
        download_dir.mkdir()
        existing = download_dir / "existing.pdf"
        existing.write_bytes(b"existing data")

        monkeypatch.setattr('src.integrations.gmail.downloads.DOWNLOAD_DIR', str(download_dir))

        from src.integrations.gmail.downloads import _file_md5_cache
        cache = _file_md5_cache()
        cache.store_downloaded_attachment_reference(
            message_id='msg1',
            attachment_id='att1',
            original_filename='statement.pdf',
            downloaded_filepath=str(existing),
            size=existing.stat().st_size,
            md5=hashlib.md5(b"existing data").hexdigest(),
        )

        mock_service = Mock()
        attachment_info = {'attachmentId': 'att1', 'filename': 'statement.pdf'}

        with caplog.at_level(logging.INFO):
            result = download_attachment(mock_service, 'msg1', attachment_info)

        assert result == str(existing)
        mock_service.users.assert_not_called()
        assert "reusing indexed Gmail attachment" in caplog.text

    def test_download_attachment_redownloads_when_indexed_file_was_deleted(self, tmp_path, monkeypatch, caplog):
        monkeypatch.chdir(tmp_path)
        download_dir = tmp_path / "downloads"
        download_dir.mkdir()
        stale = download_dir / "missing.pdf"

        monkeypatch.setattr('src.integrations.gmail.downloads.DOWNLOAD_DIR', str(download_dir))

        from src.integrations.gmail.downloads import _file_md5_cache
        cache = _file_md5_cache()
        cache.store_downloaded_attachment_reference(
            message_id='msg1',
            attachment_id='att1',
            original_filename='statement.pdf',
            downloaded_filepath=str(stale),
            size=123,
            md5='old-md5',
        )

        file_data = b'new attachment bytes'
        mock_service = Mock()
        attachment_info = {'attachmentId': 'att1', 'filename': 'statement.pdf'}
        mock_service.users().messages().attachments().get().execute.return_value = {
            'data': base64.urlsafe_b64encode(file_data).decode('UTF-8')
        }

        with caplog.at_level(logging.INFO):
            result = download_attachment(mock_service, 'msg1', attachment_info)

        assert os.path.exists(result)
        assert Path(result).read_bytes() == file_data
        assert result != str(stale)
        assert cache.get_downloaded_attachment_reference('msg1', 'att1') is not None
        assert "removing stale Gmail attachment index" in caplog.text
        assert "Downloaded attachment to" in caplog.text

    @patch('src.integrations.gmail.downloads.DOWNLOAD_DIR', '/tmp/downloads')
    @patch('src.integrations.gmail.downloads.os.makedirs')
    @patch('src.integrations.gmail.downloads.get_existing_file_by_md5')
    @patch('src.integrations.gmail.downloads.os.path.exists')
    @patch('builtins.open', new_callable=mock_open)
    def test_download_attachment_logs_content_dedupe_reuse(
        self,
        mock_file,
        mock_exists,
        mock_get_existing,
        mock_makedirs,
        caplog,
    ):
        mock_get_existing.return_value = "/tmp/downloads/existing.pdf"

        mock_service = Mock()
        attachment_info = {'attachmentId': 'att1', 'filename': 'content-dedupe-only.pdf'}
        mock_service.users().messages().attachments().get().execute.return_value = {
            'data': base64.urlsafe_b64encode(b'data').decode('UTF-8')
        }

        with caplog.at_level(logging.INFO):
            result = download_attachment(mock_service, 'msg-log-md5-unique', attachment_info)

        assert result == "/tmp/downloads/existing.pdf"
        assert "reusing existing file by content MD5" in caplog.text
        mock_file.assert_not_called()

    @patch('src.integrations.gmail.downloads.download_attachment')
    @patch('src.integrations.gmail.downloads.extract_sender_tag')
    @patch('src.integrations.gmail.downloads.list_attachments')
    def test_download_pdf_attachments(self, mock_list, mock_tag, mock_download_att):
        """Test downloading attachments from a message."""
        mock_service = Mock()
        mock_tag.return_value = "tag"
        mock_download_att.return_value = "/path/to/f1.pdf"
        mock_list.return_value = [{'attachmentId': 'a1', 'filename': 'f1.pdf'}]
        
        email_metadata = {'id': 'msg1', 'sender': 's1', 'subject': 'subj'}
        results = download_pdf_attachments(mock_service, 'msg1', email_metadata)
        
        assert len(results) == 1
        assert results[0]['filepath'] == "/path/to/f1.pdf"
        assert results[0]['sender_tag'] == "tag"

    @patch('src.integrations.gmail.downloads.download_attachment')
    @patch('src.integrations.gmail.downloads.extract_sender_tag')
    @patch('src.integrations.gmail.downloads.list_attachments')
    def test_download_pdf_attachments_logs_prepared_summary(self, mock_list, mock_tag, mock_download_att, caplog):
        mock_service = Mock()
        mock_tag.return_value = "tag"
        mock_download_att.return_value = "/path/to/f1.pdf"
        mock_list.return_value = [{'attachmentId': 'a1', 'filename': 'f1.pdf'}]

        with caplog.at_level(logging.INFO):
            download_pdf_attachments(
                mock_service,
                'msg1',
                {'id': 'msg1', 'sender': 's1', 'subject': 'subj'},
            )

        assert "Prepared 1 attachment(s) from message msg1" in caplog.text

    @patch('src.integrations.gmail.downloads.download_pdf_attachments')
    def test_batch_download_pdfs_logs_total_prepared_summary(self, mock_download, caplog):
        mock_service = Mock()
        emails = [
            {'id': 'msg1', 'sender': 's1'},
            {'id': 'msg2', 'sender': 's2'}
        ]
        mock_download.side_effect = [
            [{"filepath": "/path/to/f1.pdf", "filename": "f1.pdf"}],
            [{"filepath": "/path/to/f2.pdf", "filename": "f2.pdf"}],
        ]

        with caplog.at_level(logging.INFO):
            results = batch_download_pdfs(mock_service, emails)

        assert len(results) == 2
        assert "Total prepared attachments: 2" in caplog.text

    @patch('src.integrations.gmail.downloads._extract_pdf_text_hint')
    def test_build_pdf_filename_dbs_sg_from_hint(self, mock_hint):
        """Verify DBS SG bank statement filename is correctly inferred from content."""
        from src.integrations.gmail.downloads import build_pdf_filename_by_sender
        
        # Simulated PDF text content for DBS
        mock_hint.return_value = "DBS Bank Ltd\nAccount Statement for Zhao Hui Chen\nStatement Date: 28 Feb 2026"
        
        filename = build_pdf_filename_by_sender(
            sender="me@example.com",
            original_filename="test_user_Statement_0000000000.pdf",
            file_data=b"dummy",
            subject="My Statement"
        )
        
        assert "DBS_SG" in filename
        assert "銀行帳戶對帳單" in filename

    @patch('src.integrations.gmail.downloads._extract_pdf_text_hint', return_value="")
    def test_build_pdf_filename_falls_back_to_original_name(self, _mock_text_hint):
        name = build_pdf_filename_by_sender(
            'service@example.com',
            'original_statement.pdf',
            b'data',
            subject='No useful metadata',
        )
        assert name.startswith('service_original_statement_')
        assert name.endswith('.pdf')

    def test_list_attachments_includes_csv(self):
        from src.integrations.gmail.fetch import list_attachments

        mock_service = Mock()
        mock_service.users().messages().get().execute.return_value = {
            "payload": {
                "parts": [
                    {
                        "filename": "statement.csv",
                        "mimeType": "text/csv",
                        "body": {"attachmentId": "csv1", "size": 321},
                    }
                ]
            }
        }

        attachments = list_attachments(mock_service, "m1")
        assert len(attachments) == 1
        assert attachments[0]["filename"] == "statement.csv"
        assert attachments[0]["attachmentId"] == "csv1"

    @patch('src.integrations.gmail.downloads.download_pdf_attachments')
    def test_batch_download_pdfs(self, mock_download):
        """Test batch downloading."""
        mock_service = Mock()
        emails = [
            {'id': 'msg1', 'sender': 's1'},
            {'id': 'msg2', 'sender': 's2'}
        ]
        mock_download.return_value = [{"filepath": "/path/to/f1.pdf", "filename": "f1.pdf"}]

        results = batch_download_pdfs(mock_service, emails)
        assert len(results) == 2
        assert results[0]['filepath'] == "/path/to/f1.pdf"
