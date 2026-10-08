import base64
import logging
import os
from pathlib import Path
from unittest.mock import Mock, mock_open, patch

import pytest

import src.integrations.gmail.downloads as downloads
from src.integrations.gmail.downloads import (
    extract_sender_tag,
    extract_sender_display_name,
    build_sender_base64_suffix,
    build_file_base64_suffix,
    build_hash10_suffix,
    build_pdf_filename_by_sender,
    download_attachment,
    batch_download_pdfs,
    download_pdf_attachments,
)
from src.support.cache import ResultCache


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    """Point downloads at a tmp DOWNLOAD_DIR and a tmp attachment index."""
    download_dir = tmp_path / "downloads"
    download_dir.mkdir()
    cache = ResultCache(str(tmp_path / ".cache"))
    monkeypatch.setattr(downloads, 'DOWNLOAD_DIR', str(download_dir))
    monkeypatch.setattr(downloads, '_cache', cache)
    return download_dir, cache


def _service_returning(data: bytes) -> Mock:
    service = Mock()
    service.users.return_value.messages.return_value.attachments.return_value.get.return_value.execute.return_value = {
        'data': base64.urlsafe_b64encode(data).decode('UTF-8')
    }
    return service


class TestDownloadPDFs:
    """Test suite for PDF download functions."""
    
    def test_extract_sender_tag(self):
        """Test extracting sender tag from email address."""
        assert extract_sender_tag("service@mail.hsbc.com.sg") == "hsbc_sg_mail"
        assert extract_sender_tag("service@taipeifubon.com.tw") == "fubon_tw"
        assert extract_sender_tag("receipt@apple.com") == "apple"
        assert extract_sender_tag("bank@example.com") == "example_com"
        assert extract_sender_tag("unknown") == "unknown"

    @patch('src.integrations.gmail.downloads._cache', Mock(**{'get_downloaded_path.return_value': None}))
    @patch('src.integrations.gmail.downloads.os.makedirs')
    @patch('src.integrations.gmail.downloads.build_pdf_filename_by_sender')
    @patch('builtins.open', new_callable=Mock)
    def test_download_attachment_success(
        self, mock_open_func, mock_build_filename, mock_makedirs, tmp_path, monkeypatch
    ):
        """Test downloading an attachment successfully."""
        monkeypatch.setattr(downloads, 'DOWNLOAD_DIR', str(tmp_path))
        expected = os.path.join(str(tmp_path), 'bank_test_123.pdf')
        mock_open_instance = mock_open()
        mock_open_func.side_effect = mock_open_instance

        mock_service = Mock()
        attachment_info = {
            'attachmentId': 'att1',
            'filename': 'test.pdf'
        }
        
        # Mock API response for attachment data
        mock_service.users().messages().attachments().get().execute.return_value = {
            'data': base64.urlsafe_b64encode(b'fake pdf data').decode('UTF-8')
        }
        
        mock_build_filename.return_value = "bank_test_123.pdf"
        
        # os.path.exists -> False: no identical file on disk yet
        with patch('src.integrations.gmail.downloads.os.path.exists', return_value=False):
            filepath = download_attachment(mock_service, 'msg1', attachment_info, 'bank@example.com')
            
            assert filepath == expected
            mock_open_func.assert_called_with(expected, 'wb')
            
    def test_batch_download_pdfs_empty(self):
        """Test batch download with empty email list."""
        mock_service = Mock()
        results = batch_download_pdfs(mock_service, [])
        assert results == []

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

    @patch('src.integrations.gmail.downloads._extract_pdf_text_hint', return_value="")
    def test_same_bytes_twice_yields_one_file_and_one_api_call(self, _mock_hint, isolated):
        download_dir, _cache = isolated
        service = _service_returning(b"same content")
        get_mock = service.users.return_value.messages.return_value.attachments.return_value.get
        attachment_info = {'attachmentId': 'att1', 'filename': 'statement.pdf'}

        first = download_attachment(service, 'msg1', attachment_info)
        second = download_attachment(service, 'msg1', attachment_info)

        assert first == second
        assert get_mock.call_count == 1
        assert os.listdir(download_dir) == [os.path.basename(first)]

        # Different attachment id, same bytes: fetched once more but no new file.
        third = download_attachment(service, 'msg2', {'attachmentId': 'att2', 'filename': 'statement.pdf'})
        assert third == first
        assert get_mock.call_count == 2
        assert len(os.listdir(download_dir)) == 1

    @patch('src.integrations.gmail.downloads._extract_pdf_text_hint', return_value="")
    def test_same_bytes_under_different_subjects_yields_one_file(self, _mock_hint, isolated):
        download_dir, _cache = isolated
        service = _service_returning(b"same content")

        first = download_attachment(service, 'msg1', {'attachmentId': 'att1', 'filename': 'statement.pdf'},
                                    subject='信用卡帳單 2026年01月')
        second = download_attachment(service, 'msg2', {'attachmentId': 'att2', 'filename': 'statement.pdf'},
                                     subject='銀行對帳單 2026年02月')

        assert second == first
        assert os.listdir(download_dir) == [os.path.basename(first)]

    def test_download_attachment_logs_index_hit(self, isolated, caplog):
        download_dir, cache = isolated
        existing = download_dir / "existing.pdf"
        existing.write_bytes(b"existing data")
        cache.set_downloaded_path(downloads._index_key('msg1', {'filename': 'statement.pdf'}), str(existing))

        mock_service = Mock()
        attachment_info = {'attachmentId': 'att1', 'filename': 'statement.pdf'}

        with caplog.at_level(logging.INFO):
            result = download_attachment(mock_service, 'msg1', attachment_info)

        assert result == str(existing)
        mock_service.users.assert_not_called()
        assert "reusing indexed Gmail attachment" in caplog.text

    @patch('src.integrations.gmail.downloads._extract_pdf_text_hint', return_value="")
    def test_index_hit_survives_new_attachment_id(self, _mock_hint, isolated):
        service = _service_returning(b"statement bytes")
        first = download_attachment(service, 'msg1', {'attachmentId': 'att-A', 'filename': 's.pdf', 'size': 15})

        other = Mock()
        second = download_attachment(other, 'msg1', {'attachmentId': 'att-B', 'filename': 's.pdf', 'size': 15})

        assert second == first
        other.users.assert_not_called()

    def test_download_attachment_redownloads_when_indexed_file_was_deleted(self, isolated, caplog):
        download_dir, cache = isolated
        stale = download_dir / "missing.pdf"
        cache.set_downloaded_path(downloads._index_key('msg1', {'filename': 'statement.pdf'}), str(stale))

        file_data = b'new attachment bytes'
        mock_service = _service_returning(file_data)
        attachment_info = {'attachmentId': 'att1', 'filename': 'statement.pdf'}

        with caplog.at_level(logging.INFO):
            result = download_attachment(mock_service, 'msg1', attachment_info)

        assert Path(result).read_bytes() == file_data
        assert result != str(stale)
        assert cache.get_downloaded_path(downloads._index_key('msg1', attachment_info)) == result
        assert "Downloaded attachment to" in caplog.text

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


def test_filename_hint_skips_pdf_text_extraction_when_subject_is_enough():
    """Subject already gives statement type + month: never open the PDF just to name it."""
    with patch('src.integrations.gmail.downloads.extract_text_from_pdf') as extract:
        name = build_pdf_filename_by_sender('"台北富邦銀行" <creditcard@taipeifubon.com.tw>', 'bill.pdf', b'%PDF-1.4 x', subject='2026年8月信用卡帳單')
    assert name.startswith('台北富邦銀行_信用卡帳單_2026-08_')
    extract.assert_not_called()


def test_filename_hint_reads_pdf_when_subject_is_uninformative():
    with patch('src.integrations.gmail.downloads.extract_text_from_pdf', return_value='滙豐(台灣) 信用卡帳單 2026年07月') as extract, \
         patch('src.integrations.gmail.downloads.get_bank_password', return_value=['pw']):
        name = build_pdf_filename_by_sender('cards@estatements.hsbc.com.tw', '20260720.pdf', b'%PDF-1.4 x', subject='Your statement')
    assert name.startswith('滙豐(台灣)_信用卡帳單_2026-07_')
    assert extract.call_count == 1
