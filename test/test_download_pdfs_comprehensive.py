"""
Comprehensive tests for download_pdfs.py to improve coverage to 85%.
Focuses on edge cases and uncovered lines.
"""
import os
import pytest
import base64
import hashlib
from unittest.mock import Mock, patch, MagicMock, call
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from src.fetch.download_pdfs import (
    extract_sender_tag,
    download_attachment,
    batch_download_pdfs,
    build_pdf_filename_by_sender,
    compute_md5_hash,
    get_existing_file_by_md5,
    download_pdf_attachments
)


class TestDownloadPDFsComprehensive:
    """Comprehensive tests for PDF download functions."""
    
    @pytest.fixture(autouse=True)
    def mock_retry(self):
        """Mock the retry decorator for all tests in this class."""
        with patch('src.support.retry.retry_gmail', side_effect=lambda f: f):
            yield
    
    def test_extract_sender_tag_edge_cases(self):
        """Test edge cases for extract_sender_tag."""
        # Empty string
        assert extract_sender_tag("") == "unknown"
        
        # No @ symbol
        assert extract_sender_tag("bankstatement") == "bankstatement"
        
        # Multiple @ symbols (invalid but should handle)
        assert extract_sender_tag("test@test@example.com") == "test_example_com"
        
        # Very long sender
        long_sender = "a" * 100 + "@example.com"
        tag = extract_sender_tag(long_sender)
        assert len(tag) <= 30  # Should be truncated
        
        # Special characters
        assert extract_sender_tag("bank-statement@example.com") == "example_com"
        assert extract_sender_tag("bank.statement@example.com") == "example_com"
        assert extract_sender_tag("bank_statement@example.com") == "example_com"
    
    def test_extract_sender_tag_bank_patterns(self):
        """Test bank-specific domain patterns."""
        # HSBC Singapore
        assert extract_sender_tag("service@mail.hsbc.com.sg") == "hsbc_sg_mail"
        assert extract_sender_tag("service@hsbc.com.sg") == "hsbc_sg"
        
        # HSBC Taiwan
        assert extract_sender_tag("service@cards.estatements.hsbc.com.tw") == "hsbc_tw_cards"
        assert extract_sender_tag("service@estatements.hsbc.com.tw") == "hsbc_tw_estatements"
        assert extract_sender_tag("service@hsbc.com.tw") == "hsbc_tw"
        
        # Generic HSBC
        assert extract_sender_tag("service@hsbc.example.com") == "hsbc"
        
        # Fubon
        assert extract_sender_tag("service@taipeifubon.com.tw") == "fubon_tw"
        assert extract_sender_tag("service@fubon.com") == "fubon"
        
        # Esun
        assert extract_sender_tag("service@esunbank.com.tw") == "esun_tw"
        assert extract_sender_tag("service@esunbank.com") == "esun"
        
        # DBS
        assert extract_sender_tag("service@dbs.com.sg") == "dbs_sg"
        assert extract_sender_tag("service@dbs.com") == "dbs"
    
    def test_build_pdf_filename_by_sender(self):
        """Test build_pdf_filename_by_sender function."""
        # Test with sender and original filename
        filename = build_pdf_filename_by_sender("bank@example.com", "statement.pdf")
        
        # Should return a filename with sender tag
        assert filename.endswith(".pdf")
        assert "statement" in filename.lower()
    
    def test_build_pdf_filename_by_sender_with_file_data(self):
        """Test build_pdf_filename_by_sender with file data."""
        # Test with file data for MD5 suffix
        file_data = b"fake pdf content"
        filename = build_pdf_filename_by_sender("bank@example.com", "statement.pdf", file_data)
        
        # Should return a filename with MD5 suffix
        assert filename.endswith(".pdf")
        assert "statement" in filename.lower()
    
    def test_compute_md5_hash(self):
        """Test compute_md5_hash function."""
        # Test with bytes
        data = b"test data"
        md5_hash = compute_md5_hash(data)
        
        # Should return correct MD5 hash
        expected = hashlib.md5(data).hexdigest()
        assert md5_hash == expected
        
        # Test with empty bytes
        md5_hash = compute_md5_hash(b"")
        expected = hashlib.md5(b"").hexdigest()
        assert md5_hash == expected
    
    def test_get_existing_file_by_md5(self):
        """Test get_existing_file_by_md5 function."""
        with patch('os.listdir') as mock_listdir:
            with patch('os.path.join') as mock_join:
                with patch('src.fetch.download_pdfs.compute_md5_hash') as mock_compute_md5:
                    # Setup mock
                    mock_listdir.return_value = ["file1.pdf", "file2.pdf", "not_a_pdf.txt"]
                    mock_join.side_effect = lambda dir, file: f"{dir}/{file}"
                    
                    # First file matches MD5
                    mock_compute_md5.side_effect = ["hash1", "hash2", "hash3"]
                    
                    result = get_existing_file_by_md5("/tmp", "hash1")
                    assert result == "/tmp/file1.pdf"
                    
                    # No file matches MD5
                    result = get_existing_file_by_md5("/tmp", "nonexistent")
                    assert result is None
    
    def test_download_attachment_file_exists(self):
        """Test download_attachment when file already exists."""
        mock_service = Mock()
        attachment_info = {
            'attachmentId': 'att1',
            'filename': 'test.pdf'
        }
        
        # Mock API response
        mock_service.users().messages().attachments().get().execute.return_value = {
            'data': base64.urlsafe_b64encode(b'fake pdf data').decode('UTF-8')
        }
        
        with patch('src.fetch.download_pdfs.DOWNLOAD_DIR', '/tmp/downloads'):
            with patch('os.makedirs'):
                with patch('src.fetch.download_pdfs.compute_md5_hash') as mock_compute_md5:
                    with patch('src.fetch.download_pdfs.get_existing_file_by_md5') as mock_get_existing:
                        with patch('src.fetch.download_pdfs.build_pdf_filename_by_sender') as mock_build_filename:
                            with patch('os.path.exists', return_value=True):
                                # File already exists by MD5
                                mock_compute_md5.return_value = "existing_hash"
                                mock_get_existing.return_value = "/tmp/downloads/existing.pdf"
                                mock_build_filename.return_value = "new_filename.pdf"
                                
                                filepath = download_attachment(
                                    mock_service, 
                                    'msg1', 
                                    attachment_info, 
                                    'bank@example.com'
                                )
                                
                                # Should return existing file path
                                assert filepath == "/tmp/downloads/existing.pdf"
                                
                                # Should not have written new file
                                mock_service.users().messages().attachments().get().execute.assert_called_once()
    
    def test_download_attachment_write_error(self):
        """Test download_attachment when file write fails."""
        mock_service = Mock()
        attachment_info = {
            'attachmentId': 'att1',
            'filename': 'test.pdf'
        }
        
        # Mock API response
        mock_service.users().messages().attachments().get().execute.return_value = {
            'data': base64.urlsafe_b64encode(b'fake pdf data').decode('UTF-8')
        }
        
        with patch('src.fetch.download_pdfs.DOWNLOAD_DIR', '/tmp/downloads'):
            with patch('os.makedirs'):
                with patch('src.fetch.download_pdfs.compute_md5_hash') as mock_compute_md5:
                    with patch('src.fetch.download_pdfs.get_existing_file_by_md5') as mock_get_existing:
                        with patch('src.fetch.download_pdfs.build_pdf_filename_by_sender') as mock_build_filename:
                            with patch('os.path.exists', return_value=False):
                                with patch('builtins.open', side_effect=IOError("Disk full")):
                                    # File write should fail
                                    mock_compute_md5.return_value = "new_hash"
                                    mock_get_existing.return_value = None
                                    mock_build_filename.return_value = "bank_test_123.pdf"
                                    
                                    # Should raise IOError
                                    with pytest.raises(IOError, match="Disk full"):
                                        download_attachment(
                                            mock_service, 
                                            'msg1', 
                                            attachment_info, 
                                            'bank@example.com'
                                        )
    
    def test_download_pdf_attachments(self):
        """Test download_pdf_attachments function."""
        mock_service = Mock()
        email_info = {
            'id': 'msg1',
            'sender': 'bank@example.com'
        }
        
        # Mock list_attachments to return attachment list
        with patch('src.fetch.download_pdfs.list_attachments') as mock_list_attachments:
            with patch('src.fetch.download_pdfs.download_attachment') as mock_download:
                mock_list_attachments.return_value = [
                    {'attachmentId': 'att1', 'filename': 'test1.pdf'},
                    {'attachmentId': 'att2', 'filename': 'test2.pdf'}
                ]
                
                mock_download.side_effect = ['/tmp/file1.pdf', '/tmp/file2.pdf']
                
                results = download_pdf_attachments(mock_service, email_info)
                
                # Should have downloaded both attachments
                assert len(results) == 2
                assert results == ['/tmp/file1.pdf', '/tmp/file2.pdf']
                
                # Should have called download_attachment with correct parameters
                assert mock_download.call_count == 2
                mock_download.assert_any_call(
                    mock_service, 'msg1', 
                    {'attachmentId': 'att1', 'filename': 'test1.pdf'},
                    'bank@example.com'
                )
    
    def test_download_pdf_attachments_no_attachments(self):
        """Test download_pdf_attachments with no attachments."""
        mock_service = Mock()
        email_info = {
            'id': 'msg1',
            'sender': 'bank@example.com'
        }
        
        with patch('src.fetch.download_pdfs.list_attachments') as mock_list_attachments:
            mock_list_attachments.return_value = []
            
            results = download_pdf_attachments(mock_service, email_info)
            
            # Should return empty list
            assert results == []
    
    def test_download_pdf_attachments_partial_failure(self):
        """Test download_pdf_attachments with partial download failure."""
        mock_service = Mock()
        email_info = {
            'id': 'msg1',
            'sender': 'bank@example.com'
        }
        
        with patch('src.fetch.download_pdfs.list_attachments') as mock_list_attachments:
            with patch('src.fetch.download_pdfs.download_attachment') as mock_download:
                mock_list_attachments.return_value = [
                    {'attachmentId': 'att1', 'filename': 'test1.pdf'},
                    {'attachmentId': 'att2', 'filename': 'test2.pdf'},
                    {'attachmentId': 'att3', 'filename': 'test3.pdf'}
                ]
                
                # First succeeds, second fails, third succeeds
                mock_download.side_effect = ['/tmp/file1.pdf', IOError("Download failed"), '/tmp/file3.pdf']
                
                results = download_pdf_attachments(mock_service, email_info)
                
                # Should return successful downloads only
                assert len(results) == 2
                assert results == ['/tmp/file1.pdf', '/tmp/file3.pdf']
    
    def test_batch_download_pdfs_with_emails(self):
        """Test batch_download_pdfs with multiple emails."""
        mock_service = Mock()
        
        emails = [
            {
                'id': 'msg1',
                'sender': 'bank1@example.com'
            },
            {
                'id': 'msg2', 
                'sender': 'bank2@example.com'
            }
        ]
        
        with patch('src.fetch.download_pdfs.download_pdf_attachments') as mock_download_pdfs:
            # First email has 2 attachments, second has 1
            mock_download_pdfs.side_effect = [
                ['/tmp/file1.pdf', '/tmp/file2.pdf'],
                ['/tmp/file3.pdf']
            ]
            
            results = batch_download_pdfs(mock_service, emails)
            
            # Should return flattened list of all attachments
            assert len(results) == 3
            assert results == ['/tmp/file1.pdf', '/tmp/file2.pdf', '/tmp/file3.pdf']
            
            # Should have been called for each email
            assert mock_download_pdfs.call_count == 2
    
    def test_batch_download_pdfs_with_exception(self):
        """Test batch_download_pdfs when an email causes an exception."""
        mock_service = Mock()
        
        emails = [
            {
                'id': 'msg1',
                'sender': 'bank1@example.com'
            },
            {
                'id': 'msg2',
                'sender': 'bank2@example.com'
            }
        ]
        
        with patch('src.fetch.download_pdfs.download_pdf_attachments') as mock_download_pdfs:
            # First succeeds, second raises exception
            mock_download_pdfs.side_effect = [
                ['/tmp/file1.pdf'],
                ValueError("Invalid email format")
            ]
            
            # Should not raise exception, should continue
            results = batch_download_pdfs(mock_service, emails)
            
            # Should return results from successful downloads only
            assert results == ['/tmp/file1.pdf']


if __name__ == '__main__':
    pytest.main([__file__, '-v'])