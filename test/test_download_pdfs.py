"""
Unit tests for PDF download module.
"""
import os
import pytest
import base64
from unittest.mock import Mock, patch
import sys
from functools import wraps

# No more sys.modules hack here

from src.fetch.download_pdfs import extract_sender_tag, download_attachment, batch_download_pdfs


class TestDownloadPDFs:
    """Test suite for PDF download functions."""
    
    @pytest.fixture(autouse=True)
    def mock_retry(self):
        """Mock the retry decorator for all tests in this class."""
        with patch('src.utils.retry.retry_gmail', side_effect=lambda f: f):
            yield

    def test_extract_sender_tag(self):
        """Test extracting sender tag from email address."""
        assert extract_sender_tag("service@mail.hsbc.com.sg") == "hsbc_sg_mail"
        assert extract_sender_tag("service@taipeifubon.com.tw") == "fubon_tw"
        assert extract_sender_tag("receipt@apple.com") == "apple"
        assert extract_sender_tag("bank@example.com") == "example_com"
        assert extract_sender_tag("unknown") == "unknown"

    @patch('src.fetch.download_pdfs.DOWNLOAD_DIR', '/tmp/downloads')
    @patch('src.fetch.download_pdfs.os.makedirs')
    @patch('src.fetch.download_pdfs.compute_md5_hash')
    @patch('src.fetch.download_pdfs.get_existing_file_by_md5')
    @patch('src.fetch.download_pdfs.build_pdf_filename_by_sender')
    @patch('builtins.open', new_callable=Mock)
    def test_download_attachment_success(
        self, mock_open_func, mock_build_filename, mock_get_existing, mock_hash, mock_makedirs, tmp_path
    ):
        """Test downloading an attachment successfully."""
        from unittest.mock import mock_open
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
        
        mock_hash.return_value = "md5hash"
        mock_get_existing.return_value = None
        mock_build_filename.return_value = "bank_test_123.pdf"
        
        # We need to mock os.path.exists to return False so it doesn't try to increment suffix
        with patch('src.fetch.download_pdfs.os.path.exists', return_value=False):
            filepath = download_attachment(mock_service, 'msg1', attachment_info, 'bank@example.com')
            
            assert filepath == '/tmp/downloads/bank_test_123.pdf'
            mock_open_func.assert_called_with('/tmp/downloads/bank_test_123.pdf', 'wb')
            
    def test_batch_download_pdfs_empty(self):
        """Test batch download with empty email list."""
        mock_service = Mock()
        results = batch_download_pdfs(mock_service, [])
        assert results == []
