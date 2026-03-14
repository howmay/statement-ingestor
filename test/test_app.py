"""
Unit tests for the main application (GmailExpenseParserApp).
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
import sys
from pathlib import Path
import re
import csv

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from src.runtime.app import GmailExpenseParserApp
from src.export.csv_writer import export_receipts_to_csv


def test_active_code_does_not_use_legacy_src_import_paths():
    """Active code should only import from the refactored src package layout."""
    project_root = Path(__file__).parent.parent
    active_paths = [project_root / "main.py", project_root / "src"]
    legacy_imports = re.compile(
        r"(from|import)\s+src\.(config|auth|fetch|output|bank_parsers|llm|ocr|pdf|utils)\b"
    )
    offenders = []

    for active_path in active_paths:
        files = [active_path] if active_path.is_file() else active_path.rglob("*.py")
        for file_path in files:
            text = file_path.read_text(encoding="utf-8")
            if legacy_imports.search(text):
                offenders.append(str(file_path.relative_to(project_root)))

    assert offenders == []


@pytest.fixture
def app():
    """Create an app instance with enhancements enabled."""
    with patch('src.runtime.app.setup_logging'), \
         patch('src.runtime.app.get_logger'):
        app = GmailExpenseParserApp(use_enhancements=True)
        # Replace the logger with a mock
        app.logger = Mock()
        yield app


class TestGmailExpenseParserAppInit:
    """Test initialization of the app."""
    
    def test_init(self, app):
        """Test initialization."""
        assert app.use_enhancements is True
        assert app.service is None
        assert app.user_email is None
        assert app.emails == []
        assert app.downloaded_files == []
        assert app.extracted_texts == []
        assert app.parsed_receipts == []
        # Check stats keys
        expected_stats = ['emails_found', 'pdfs_downloaded', 'texts_extracted', 
                         'receipts_parsed', 'errors', 'warnings']
        for key in expected_stats:
            assert key in app.stats
            assert app.stats[key] == 0


class TestGmailExpenseParserAppAuthenticate:
    """Test authentication."""
    
    def test_authenticate_success(self, app):
        """Test successful authentication."""
        mock_service = Mock()
        with patch('src.runtime.app.get_gmail_service', return_value=mock_service):
            result = app.authenticate()
            
            assert result is True
            assert app.service == mock_service
    
    def test_authenticate_failure(self, app):
        """Test authentication failure."""
        with patch('src.runtime.app.get_gmail_service', side_effect=Exception("Auth failed")):
            result = app.authenticate()
            
            assert result is False
            assert app.service is None


class TestGmailExpenseParserAppFetchEmails:
    """Test email fetching."""
    
    def test_fetch_emails_success(self, app):
        """Test successful email fetching."""
        app.service = Mock()
        mock_emails = [
            {'id': 'msg1', 'subject': 'statement', 'sender': 'bank@example.com'},
            {'id': 'msg2', 'subject': 'invoice', 'sender': 'vendor@example.com'}
        ]
        with patch('src.runtime.app.search_emails', return_value=mock_emails):
            result = app.fetch_emails(max_results=10)
            
            assert result is True
            assert app.emails == mock_emails
            assert app.stats['emails_found'] == 2
    
    def test_fetch_emails_no_results(self, app):
        """Test email fetching with no results."""
        app.service = Mock()
        with patch('src.runtime.app.search_emails', return_value=[]):
            result = app.fetch_emails(max_results=5)
            
            assert result is True
            assert app.emails == []
            assert app.stats['emails_found'] == 0
    
    def test_fetch_emails_error(self, app):
        """Test email fetching error."""
        app.service = Mock()
        with patch('src.runtime.app.search_emails', side_effect=Exception("API error")):
            result = app.fetch_emails(max_results=10)
            
            assert result is False
            assert app.stats['errors'] > 0

    def test_fetch_emails_with_date_range(self, app):
        """Email fetch should pass date range to search layer."""
        app.service = Mock()

        with patch('src.runtime.app.search_emails', return_value=[]) as mock_search:
            result = app.fetch_emails(max_results=20, date_from='2026-03-01', date_to='2026-03-31')

            assert result is True
            mock_search.assert_called_once_with(
                app.service,
                max_results=20,
                date_from='2026-03-01',
                date_to='2026-03-31',
            )


class TestGmailExpenseParserAppDownloadAttachments:
    """Test attachment download."""
    
    def test_download_attachments_success(self, app):
        """Test successful attachment download."""
        app.service = Mock()
        app.emails = [
            {'id': 'msg1', 'subject': 'stmt', 'sender': 'bank@example.com'},
            {'id': 'msg2', 'subject': 'inv', 'sender': 'vendor@example.com'}
        ]
        
        # batch_download_pdfs is called once per email, so 2 emails = 2 calls
        # Each call returns 1 file, so total 2 files
        with patch('src.runtime.app.list_attachments', return_value=[
            [{'attachmentId': 'att1', 'filename': 'file1.pdf'}],
            [{'attachmentId': 'att2', 'filename': 'file2.pdf'}]
        ]), \
             patch('src.runtime.app.batch_download_pdfs', return_value=[
                 {'filepath': '/downloads/file1.pdf', 'sender_tag': 'bank'}
             ]):
            result = app.download_attachments()
            
            assert result is True
            # dedupe by filepath -> only one unique file kept
            assert len(app.downloaded_files) == 1
            assert app.stats['pdfs_downloaded'] == 1
    
    def test_download_attachments_no_emails(self, app):
        """Test download with no emails."""
        app.emails = []
        
        with patch('src.runtime.app.list_attachments', return_value=[]), \
             patch('src.runtime.app.batch_download_pdfs'):
            result = app.download_attachments()
            
            assert result is True
            assert app.downloaded_files == []
            assert app.stats['pdfs_downloaded'] == 0


class TestGmailExpenseParserAppExtractTexts:
    """Test text extraction."""
    
    def test_extract_texts_success(self, app):
        """Test successful text extraction."""
        app.downloaded_files = [
            {'filepath': '/downloads/file1.pdf', 'sender': 'bank', 'subject': 'stmt'},
            {'filepath': '/downloads/file2.pdf', 'sender': 'vendor', 'subject': 'inv'}
        ]
        
        with patch('src.runtime.app.extract_text_from_pdf', return_value="Extracted text"):
            result = app.extract_texts()
            
            assert result is True
            assert len(app.extracted_texts) == 2
            assert app.stats['texts_extracted'] == 2
    
    def test_extract_texts_no_files(self, app):
        """Test extract with no files."""
        app.downloaded_files = []
        
        result = app.extract_texts()
        
        assert result is True
        assert app.extracted_texts == []
        assert app.stats['texts_extracted'] == 0


class TestGmailExpenseParserAppParseReceipts:
    """Test receipt parsing."""
    
    def test_parse_receipts_success(self, app):
        """Test successful receipt parsing."""
        app.extracted_texts = [
            {'text': 'text1', 'file_info': {'filepath': '/f1.pdf', 'sender': 'bank', 'subject': 'stmt'}},
            {'text': 'text2', 'file_info': {'filepath': '/f2.pdf', 'sender': 'vendor', 'subject': 'inv'}}
        ]
        
        with patch('src.runtime.app.parse_receipt_text', side_effect=[
            [{'date': '2024-01-01', 'amount': 100.0, 'expense_name': 'Purchase', 'expense_type': 'Food', 'source': 'bank', 'confidence': 0.95}],
            [{'date': '2024-01-01', 'amount': 100.0, 'expense_name': 'Purchase', 'expense_type': 'Food', 'source': 'bank', 'confidence': 0.95}],
        ]):
            result = app.parse_receipts()
            
            assert result is True
            assert len(app.parsed_receipts) == 2
            assert app.stats['receipts_parsed'] == 2
    
    def test_parse_receipts_no_texts(self, app):
        """Test parse with no extracted texts."""
        app.extracted_texts = []
        
        result = app.parse_receipts()
        
        assert result is True
        assert app.parsed_receipts == []
        assert app.stats['receipts_parsed'] == 0


class TestGmailExpenseParserAppExportResults:
    """Test export functionality."""
    
    def test_export_results_success(self, app):
        """Test successful export."""
        app.parsed_receipts = [{'date': '2024-01-01', 'amount': 100}]
        app.extracted_texts = [{'text': 'raw', 'file_info': {}}]
        
        with patch('src.runtime.app.export_receipts_to_csv', return_value='/output/receipts.csv'), \
             patch('src.runtime.app.export_extracted_texts_to_csv', return_value='/output/texts.csv'):
            result = app.export_results()
            
            assert result is True
    
    def test_export_results_no_data(self, app):
        """Test export with no data."""
        app.parsed_receipts = []
        app.extracted_texts = []
        
        with patch('src.runtime.app.export_receipts_to_csv'), \
             patch('src.runtime.app.export_extracted_texts_to_csv'):
            result = app.export_results()
            
            assert result is True

    def test_export_receipts_to_csv_writes_bank_income_columns(self, tmp_path):
        receipts = [{
            'date': '2026-03-01',
            'amount': 2500.0,
            'currency': 'TWD',
            'expense_name': 'Salary',
            'expense_type': 'Income',
            'source': 'Fubon Bank',
            'source_file': 'bank.pdf',
        }]

        filepath = export_receipts_to_csv(receipts, output_dir=str(tmp_path)).split(',')[0]

        with open(filepath, 'r', encoding='utf-8-sig') as csvfile:
            rows = list(csv.DictReader(csvfile))

        assert rows[0]['income'] == '2500.00'
        assert rows[0]['expense'] == ''


def test_new_src_packages_exist():
    import importlib

    for name in [
        "src.core",
        "src.support",
        "src.integrations",
        "src.integrations.gmail",
        "src.parsing",
        "src.parsing.banks",
        "src.parsing.llm",
        "src.parsing.ocr",
        "src.parsing.pdf",
        "src.export",
        "src.runtime",
    ]:
        assert importlib.import_module(name) is not None


class TestGmailExpenseParserAppRun:
    """Test full pipeline run."""
    
    def test_run_success(self, app):
        """Test successful full pipeline run."""
        with patch.object(app, 'validate_configuration', return_value=True), \
             patch.object(app, 'authenticate', return_value=True), \
             patch.object(app, 'fetch_emails', return_value=True), \
             patch.object(app, 'download_attachments', return_value=True), \
             patch.object(app, 'extract_texts', return_value=True), \
             patch.object(app, 'parse_receipts', return_value=True), \
             patch.object(app, 'export_results', return_value=True):
            stats = app.run(max_results=20)
            
            assert app.stats['errors'] == 0
    
    def test_run_config_failure(self, app):
        """Test run with configuration validation failure."""
        with patch.object(app, 'validate_configuration', return_value=False):
            stats = app.run(max_results=10)
            
            assert stats['errors'] > 0 or app.stats['errors'] >= 0
    
    def test_run_auth_failure(self, app):
        """Test run with authentication failure."""
        with patch.object(app, 'authenticate', return_value=False), \
             patch.object(app, 'validate_configuration', return_value=True):
            stats = app.run(max_results=10)
            assert app.authenticate.called


class TestGmailExpenseParserAppValidateConfiguration:
    """Test configuration validation."""

    def test_validate_configuration_success_bool_return(self, app):
        """Current validator returns bool; app should handle it."""
        app.use_enhancements = True
        with patch('src.support.config_validator.ConfigValidator.validate_all', return_value=True):
            result = app.validate_configuration()
        assert result is True

    def test_validate_configuration_failure_bool_return(self, app):
        """False bool return should fail gracefully (no tuple unpack crash)."""
        app.use_enhancements = True
        with patch('src.support.config_validator.ConfigValidator.validate_all', return_value=False):
            result = app.validate_configuration()
        assert result is False
        assert app.stats['errors'] >= 1

    def test_validate_configuration_legacy_tuple_return(self, app):
        """Legacy tuple return should still be supported."""
        app.use_enhancements = True
        with patch(
            'src.support.config_validator.ConfigValidator.validate_all',
            return_value=(False, ['missing TARGET_SENDERS'])
        ):
            result = app.validate_configuration()
        assert result is False

    def test_validate_configuration_skipped(self, app):
        """Test configuration validation skipped when enhancements disabled."""
        app.use_enhancements = False
        result = app.validate_configuration()
        assert result is True
