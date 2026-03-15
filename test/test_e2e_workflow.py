"""
End-to-end integration test to improve overall coverage.
This test exercises the full workflow with mocks.
"""
import pytest
from unittest.mock import Mock, patch, MagicMock, mock_open
import sys
from pathlib import Path
import os

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from src.runtime.app import GmailExpenseParserApp


class TestEndToEndWorkflow:
    """End-to-end workflow tests."""
    
    @pytest.fixture
    def app(self):
        """Create an app instance."""
        with patch('src.runtime.app.setup_logging'), \
             patch('src.runtime.app.get_logger'):
            app = GmailExpenseParserApp(use_enhancements=True)
            app.logger = Mock()
            yield app
    
    def test_full_workflow_success(self, app):
        """Test complete successful workflow."""
        # Mock all dependencies
        with patch.object(app, 'validate_configuration', return_value=True), \
             patch('src.runtime.app.get_gmail_service') as mock_service, \
             patch('src.runtime.app.search_emails') as mock_search, \
             patch('src.runtime.app.batch_download_pdfs') as mock_download, \
             patch('src.runtime.app.extract_text_from_pdf') as mock_extract, \
             patch('src.runtime.app.parse_multiple_receipts') as mock_parse, \
             patch('src.runtime.app.export_receipts_to_csv') as mock_export_receipts, \
             patch('src.runtime.app.export_extracted_texts_to_csv') as mock_export_texts:
            
            mock_service.return_value = Mock()
            mock_search.return_value = [
                {'id': 'msg1', 'subject': 'Test', 'from': 'HSBC@mail.hsbc.com.sg'}
            ]
            mock_download.return_value = [
                {'filepath': '/tmp/test1.pdf', 'filename': 'test1.pdf', 'sender': 'HSBC@mail.hsbc.com.sg'}
            ]
            mock_extract.return_value = "Extracted text content"
            mock_parse.return_value = [{'date': '2024-01-01', 'amount': 100.0}]
            mock_export_receipts.return_value = "/output/receipts.csv"
            mock_export_texts.return_value = "/output/texts.csv"
            
            result = app.run()
            
            assert isinstance(result, dict)
            app.logger.info.assert_any_call("=" * 60)
    
    def test_workflow_with_no_emails(self, app):
        """Test workflow when no emails found."""
        with patch.object(app, 'validate_configuration', return_value=True), \
             patch('src.runtime.app.get_gmail_service') as mock_service, \
             patch('src.runtime.app.search_emails') as mock_search:
            
            mock_service.return_value = Mock()
            mock_search.return_value = []
            
            result = app.run()
            
            assert isinstance(result, dict)
            # Should still complete successfully
            assert result['emails_found'] == 0
    
    def test_workflow_with_config_validation_failure(self, app):
        """Test workflow when config validation fails."""
        with patch.object(app, 'validate_configuration', return_value=False):
            result = app.run()
            
            assert isinstance(result, dict)
    
    def test_workflow_with_auth_failure(self, app):
        """Test workflow when authentication fails."""
        with patch.object(app, 'validate_configuration', return_value=True), \
             patch('src.runtime.app.get_gmail_service', side_effect=Exception("Auth failed")):
            result = app.run()
            
            assert isinstance(result, dict)
    
    def test_workflow_partial_failure_in_extraction(self, app):
        """Test workflow with some extraction failures."""
        with patch.object(app, 'validate_configuration', return_value=True), \
             patch('src.runtime.app.get_gmail_service') as mock_service, \
             patch('src.runtime.app.search_emails') as mock_search, \
             patch('src.runtime.app.batch_download_pdfs') as mock_download, \
             patch('src.runtime.app.extract_text_from_pdf') as mock_extract, \
             patch('src.runtime.app.parse_multiple_receipts') as mock_parse, \
             patch('src.runtime.app.export_receipts_to_csv') as mock_export:
            
            mock_service.return_value = Mock()
            mock_search.return_value = [{'id': 'msg1', 'subject': 'Test', 'from': 'test@example.com'}]
            mock_download.return_value = [
                {'filepath': '/tmp/test1.pdf', 'filename': 'test1.pdf', 'sender': 'test@example.com'},
                {'filepath': '/tmp/test2.pdf', 'filename': 'test2.pdf', 'sender': 'test@example.com'}
            ]
            # First extract succeeds, second fails
            def extract_side_effect(pdf_path, password=None):
                if 'test1' in pdf_path:
                    return "Text 1"
                else:
                    raise Exception("Extraction failed")
            mock_extract.side_effect = extract_side_effect
            mock_parse.return_value = [{'date': '2024-01-01', 'amount': 100.0}]
            mock_export.return_value = "/output/receipts.csv"
            
            result = app.run()
            
            assert isinstance(result, dict)
            # Should have warnings/errors count
            assert 'errors' in result
    
    def test_workflow_with_parse_failure(self, app):
        """Test workflow when parsing fails."""
        with patch.object(app, 'validate_configuration', return_value=True), \
             patch('src.runtime.app.get_gmail_service') as mock_service, \
             patch('src.runtime.app.search_emails') as mock_search, \
             patch('src.runtime.app.batch_download_pdfs') as mock_download, \
             patch('src.runtime.app.extract_text_from_pdf') as mock_extract, \
             patch('src.runtime.app.parse_multiple_receipts') as mock_parse, \
             patch('src.runtime.app.export_receipts_to_csv') as mock_export:
            
            mock_service.return_value = Mock()
            mock_search.return_value = [{'id': 'msg1', 'subject': 'Test'}]
            mock_download.return_value = [{'filepath': '/tmp/test1.pdf', 'filename': 'test1.pdf'}]
            mock_extract.return_value = "Text"
            mock_parse.side_effect = Exception("Parse failed")
            mock_export.return_value = "/output/receipts.csv"
            
            result = app.run()
            
            assert isinstance(result, dict)
    
    def test_multiple_emails_workflow(self, app):
        """Test workflow with multiple emails."""
        with patch.object(app, 'validate_configuration', return_value=True), \
             patch('src.runtime.app.get_gmail_service') as mock_service, \
             patch('src.runtime.app.search_emails') as mock_search, \
             patch('src.runtime.app.batch_download_pdfs') as mock_download, \
             patch('src.runtime.app.extract_text_from_pdf') as mock_extract, \
             patch('src.runtime.app.parse_multiple_receipts') as mock_parse, \
             patch('src.runtime.app.export_receipts_to_csv') as mock_export, \
             patch('src.parsing.llm.parse_receipt._get_llm_runtime_config') as mock_llm_config:
            
            # Disable LLM to avoid connection timeouts in tests
            mock_llm_config.return_value = {"enabled": False}
            
            mock_service.return_value = Mock()
            mock_search.return_value = [
                {'id': 'msg1', 'subject': 'Test1', 'from': 'sender1@example.com'},
                {'id': 'msg2', 'subject': 'Test2', 'from': 'sender2@example.com'},
                {'id': 'msg3', 'subject': 'Test3', 'from': 'sender3@example.com'}
            ]
            mock_download.return_value = [
                {'filepath': f'/tmp/test{i}.pdf', 'filename': f'test{i}.pdf', 'sender': f'sender{i}@example.com'}
                for i in range(1, 4)
            ]
            mock_extract.return_value = "Text"
            mock_parse.return_value = [{'date': '2024-01-01', 'amount': 100.0}]
            mock_export.return_value = "/output/receipts.csv"
            
            result = app.run()
            
            assert isinstance(result, dict)
            assert result['emails_found'] == 3
            assert result['pdfs_downloaded'] == 3
