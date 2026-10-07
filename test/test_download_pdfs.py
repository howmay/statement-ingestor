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

from src.integrations.gmail.downloads import extract_sender_tag, download_attachment, batch_download_pdfs


class TestDownloadPDFs:
    """Test suite for PDF download functions."""
    
    def test_extract_sender_tag(self):
        """Test extracting sender tag from email address."""
        assert extract_sender_tag("service@mail.hsbc.com.sg") == "hsbc_sg_mail"
        assert extract_sender_tag("service@taipeifubon.com.tw") == "fubon_tw"
        assert extract_sender_tag("receipt@apple.com") == "apple"
        assert extract_sender_tag("bank@example.com") == "example_com"
        assert extract_sender_tag("unknown") == "unknown"

    @patch('src.integrations.gmail.downloads.DOWNLOAD_DIR', '/tmp/downloads')
    @patch('src.integrations.gmail.downloads._cache', Mock(**{'get_downloaded_path.return_value': None}))
    @patch('src.integrations.gmail.downloads.os.makedirs')
    @patch('src.integrations.gmail.downloads.build_pdf_filename_by_sender')
    @patch('builtins.open', new_callable=Mock)
    def test_download_attachment_success(
        self, mock_open_func, mock_build_filename, mock_makedirs, tmp_path
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
        
        mock_build_filename.return_value = "bank_test_123.pdf"
        
        # os.path.exists -> False: no identical file on disk yet
        with patch('src.integrations.gmail.downloads.os.path.exists', return_value=False):
            filepath = download_attachment(mock_service, 'msg1', attachment_info, 'bank@example.com')
            
            assert filepath == '/tmp/downloads/bank_test_123.pdf'
            mock_open_func.assert_called_with('/tmp/downloads/bank_test_123.pdf', 'wb')
            
    def test_batch_download_pdfs_empty(self):
        """Test batch download with empty email list."""
        mock_service = Mock()
        results = batch_download_pdfs(mock_service, [])
        assert results == []
