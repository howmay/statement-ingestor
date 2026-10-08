import pytest
import re
import csv
import tempfile
from unittest.mock import Mock, patch
from pathlib import Path
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
def app(tmp_path, monkeypatch):
    """Create an app instance (logs and cache land in tmp_path)."""
    monkeypatch.chdir(tmp_path)
    with patch('src.runtime.app.logging.basicConfig'):
        app = GmailExpenseParserApp()
    # Replace the logger with a mock
    app.logger = Mock()
    yield app


class TestGmailExpenseParserAppInit:
    """Test initialization of the app."""
    
    def test_init(self, app):
        """Test initialization."""
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

    def test_fetch_emails_logs_statement_search_scope(self, app):
        app.service = Mock()

        with patch('src.runtime.app.search_emails', return_value=[]):
            result = app.fetch_emails(max_results=5)

            assert result is True
            log_messages = [call.args[0] for call in app.logger.info.call_args_list]
            assert any('statement' in message.lower() for message in log_messages)


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
        with patch('src.runtime.app.batch_download_pdfs', return_value=[
                 {'filepath': '/downloads/file1.pdf', 'sender_tag': 'bank'}
             ]), patch('src.runtime.app.get_gmail_service', return_value=Mock()):
            result = app.download_attachments()
            
            assert result is True
            # dedupe by filepath -> only one unique file kept
            assert len(app.downloaded_files) == 1
            assert app.stats['pdfs_downloaded'] == 1
    


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
    

    def test_extract_texts_reads_csv_without_pdf_extractor(self, app):
        with tempfile.NamedTemporaryFile('w', suffix='.csv', delete=False, encoding='utf-8') as tmp:
            tmp.write("Type,Completed Date,Description,Amount,Currency,State\n")
            tmp.write("Topup,2025-03-16 23:10:31,Transfer from *6221,100,SGD,COMPLETED\n")
            csv_path = tmp.name

        app.downloaded_files = [
            {'filepath': csv_path, 'sender': 'bank', 'subject': 'stmt', 'filename': 'statement.csv'}
        ]

        try:
            with patch('src.runtime.app.extract_text_from_pdf') as mock_pdf_extract:
                result = app.extract_texts()

            assert result is True
            assert len(app.extracted_texts) == 1
            assert 'Transfer from *6221' in app.extracted_texts[0]['text']
            mock_pdf_extract.assert_not_called()
        finally:
            Path(csv_path).unlink(missing_ok=True)


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
    


    def test_extract_and_parse_reuse_cached_file_md5(self, app):
        """MD5 should be computed once and then carried in file_info across steps."""
        app.cache = Mock()
        app.cache.get_file_md5.return_value = 'md5-1'
        app.cache.get.return_value = None
        app.downloaded_files = [
            {'filepath': '/downloads/file1.pdf', 'sender': 'bank', 'subject': 'stmt', 'filename': 'file1.pdf', 'sender_tag': 'bank'}
        ]

        with patch('src.runtime.app.extract_text_from_pdf', return_value='Extracted text'):
            assert app.extract_texts(max_workers=1) is True

        with patch('src.runtime.app.parse_receipt_text', return_value=[
            {'date': '2024-01-01', 'amount': 100.0, 'expense_name': 'Purchase', 'expense_type': 'Food', 'source': 'bank', 'confidence': 0.95}
        ]):
            assert app.parse_receipts(max_workers=1) is True

        assert app.cache.get_file_md5.call_count == 1
        # Only the Step-4 extraction text is cached; parse results never are.
        assert app.cache.get.call_count == 1
        assert app.cache.set.call_count == 1
        extracted_file_info = app.extracted_texts[0]['file_info']
        assert extracted_file_info['file_md5'] == 'md5-1'


    def test_parse_receipts_error_logs_downloaded_filename(self, app):
        app.extracted_texts = [
            {
                'text': 'text1',
                'file_info': {
                    'filepath': '/downloads/HSBC_SG_statement_abcd1234.pdf',
                    'filename': '20260322.pdf',
                    'sender': 'bank',
                    'subject': 'stmt',
                },
            }
        ]

        with patch('src.runtime.app.parse_receipt_text', side_effect=Exception("boom")):
            result = app.parse_receipts(max_workers=1)

        assert result is True
        error_messages = [call.args[0] for call in app.logger.error.call_args_list if call.args]
        assert any('HSBC_SG_statement_abcd1234.pdf' in msg for msg in error_messages)


class TestGmailExpenseParserAppExportResults:
    """Test export functionality."""
    
    def test_export_results_success(self, app):
        """Test successful export."""
        app.parsed_receipts = [{'date': '2024-01-01', 'amount': 100}]
        app.extracted_texts = [{'text': 'raw', 'file_info': {}}]
        
        with patch('src.runtime.app.export_receipts_to_csv', return_value='/output/receipts.csv'), \
             patch('src.runtime.app.export_extracted_texts_to_csv', return_value='/output/texts.csv'), \
             patch('src.runtime.app.sort_exported_receipt_csvs') as mock_sort:
            result = app.export_results()
            
            assert result is True
            mock_sort.assert_called_once_with(['/output/receipts.csv'])

    def test_export_results_sorts_multiple_exported_receipt_csvs(self, app):
        app.parsed_receipts = [{'date': '2024-01-01', 'amount': 100}]

        with patch('src.runtime.app.export_receipts_to_csv', return_value='/output/a.csv,/output/b.csv'), \
             patch('src.runtime.app.export_extracted_texts_to_csv'), \
             patch('src.runtime.app.sort_exported_receipt_csvs') as mock_sort:
            result = app.export_results()

        assert result is True
        mock_sort.assert_called_once_with(['/output/a.csv', '/output/b.csv'])
    

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


class TestGmailExpenseParserAppValidateConfiguration:
    """Test configuration validation."""

    def test_validate_configuration_success_bool_return(self, app):
        """Current validator returns bool; app should handle it."""
        with patch('src.runtime.app.config_is_valid', return_value=True):
            result = app.validate_configuration()
        assert result is True

    def test_validate_configuration_failure_bool_return(self, app):
        """False bool return should fail gracefully (no tuple unpack crash)."""
        with patch('src.runtime.app.config_is_valid', return_value=False):
            result = app.validate_configuration()
        assert result is False
        assert app.stats['errors'] >= 1


class TestGetBankAndCountry:
    """Bank lookup: parser_name first, then filename."""

    def test_parser_name_wins_over_filename(self, app):
        receipts = [{'parser_name': 'HsbcSgCardParser'}]
        assert app._get_bank_and_country('x', 'fubon.pdf', receipts) == ('HSBC', 'SG', '信用卡')

    def test_filename_fallback(self, app):
        assert app._get_bank_and_country('', '玉山信用卡_202603.pdf') == ('E.SUN', 'TW', '信用卡')
        assert app._get_bank_and_country('', 'wise_statement.csv') == ('Wise', 'Global', '銀行帳戶')

    def test_unknown(self, app):
        assert app._get_bank_and_country('', 'foo.pdf', [{}]) == ('Unknown', 'TW', '未知')


class TestGmailExpenseParserAppErrorPaths:
    """Failure and empty-input paths of each pipeline step."""
    

    def test_authenticate_with_exception(self, app):
        """Test authentication when get_gmail_service raises an exception."""
        
        with patch('src.runtime.app.get_gmail_service', side_effect=Exception("Auth failed")):
            result = app.authenticate()
            
            assert result is False
            assert app.service is None
            assert app.stats['errors'] == 1
            app.logger.error.assert_called_once()
    
    def test_fetch_emails_with_exception(self, app):
        """Test fetch_emails when search_emails raises an exception."""
        app.service = Mock()
        
        with patch('src.runtime.app.search_emails', side_effect=Exception("Search failed")):
            result = app.fetch_emails()
            
            assert result is False
            assert app.emails == []
            assert app.stats['errors'] == 1
            app.logger.error.assert_called_once()
    
    def test_download_attachments_no_emails(self, app):
        """Test download_attachments when there are no emails."""
        app.emails = []
        
        result = app.download_attachments()
        
        assert result is True
        assert app.downloaded_files == []
        assert app.stats['pdfs_downloaded'] == 0
        app.logger.info.assert_called_with("No emails to process.")
    
    def test_download_attachments_with_exception(self, app):
        """Test download_attachments when batch_download_pdfs raises an exception."""
        app.emails = [{'id': 'msg1', 'subject': 'Test'}]
        app.service = Mock()
        
        with patch('src.runtime.app.batch_download_pdfs', side_effect=Exception("Download failed")):
            result = app.download_attachments()
            
            # The method catches exceptions per email and still returns True
            assert result is True
            assert app.stats['errors'] >= 1
    
    def test_extract_texts_no_files(self, app):
        """Test extract_texts when there are no downloaded files."""
        app.downloaded_files = []
        
        result = app.extract_texts()
        
        assert result is True
        assert app.extracted_texts == []
        assert app.stats['texts_extracted'] == 0
        app.logger.info.assert_called_with("No PDFs downloaded.")
    
    def test_extract_texts_with_exception(self, app):
        """Test extract_texts when extract_text_from_pdf raises an exception."""
        app.downloaded_files = [{'filepath': '/path/to/file1.pdf', 'filename': 'file1.pdf'}]
        
        with patch('src.runtime.app.extract_text_from_pdf', side_effect=Exception("Extraction failed")):
            result = app.extract_texts()
            
            # extract_texts handles exceptions in process_file and returns True (but increments errors)
            assert result is True
            assert app.extracted_texts == []
            assert app.stats['errors'] == 1
            # Error should be logged for each failed file
            app.logger.error.assert_called()
    
    def test_parse_receipts_no_texts(self, app):
        """Test parse_receipts when there are no extracted texts."""
        app.extracted_texts = []
        
        result = app.parse_receipts()
        
        assert result is True
        assert app.parsed_receipts == []
        assert app.stats['receipts_parsed'] == 0
        app.logger.info.assert_called_with("No text to parse.")
    
    def test_parse_receipts_with_exception(self, app):
        """Test parse_receipts when parse_receipt_text raises an exception."""
        app.extracted_texts = [
            {'text': 'text1', 'file_info': {'filepath': '/path/to/file1.pdf', 'filename': 'file1.pdf'}},
            {'text': 'text2', 'file_info': {'filepath': '/path/to/file2.pdf', 'filename': 'file2.pdf'}}
        ]
        
        with patch('src.runtime.app.parse_receipt_text', side_effect=Exception("Parsing failed")):
            result = app.parse_receipts()
            
            assert result is True  # parse_receipts returns True even if individual parsing fails
            assert app.parsed_receipts == []
            app.logger.error.assert_called()
    
    def test_export_results_no_data(self, app):
        """Test export_results when there is no data to export."""
        app.parsed_receipts = []
        app.extracted_texts = []
        
        result = app.export_results()
        
        assert result is True
        app.logger.info.assert_called_with("No results to export.")
    
    def test_export_results_with_exception(self, app):
        """Test export_results when export functions raise exceptions."""
        app.parsed_receipts = [{'date': '2024-01-01', 'amount': 100.0}]
        app.extracted_texts = ['text1']
        
        with patch('src.runtime.app.export_receipts_to_csv', side_effect=Exception("Export failed")):
            result = app.export_results()
            
            assert result is False
            assert app.stats['errors'] == 1
            app.logger.error.assert_called_once()
    
    
    
    
    
    
    
    
    def test_run_success_with_stats(self, app):
        """Test successful run with statistics."""
        
        with patch.object(app, 'validate_configuration', return_value=True), \
             patch.object(app, 'authenticate', return_value=True), \
             patch.object(app, 'fetch_emails', return_value=True), \
             patch.object(app, 'download_attachments', return_value=True), \
             patch.object(app, 'extract_texts', return_value=True), \
             patch.object(app, 'parse_receipts', return_value=True), \
             patch.object(app, 'export_results', return_value=True):
            result = app.run()
            
            # run() returns stats dict
            assert isinstance(result, dict)
            assert result['errors'] == 0
            app.logger.info.assert_any_call("=" * 60)
    
    
    


_RUN_STEPS = ['validate_configuration', 'authenticate', 'fetch_emails', 'download_attachments',
              'extract_texts', 'parse_receipts', 'export_results']


@pytest.mark.parametrize('failing', range(len(_RUN_STEPS)), ids=_RUN_STEPS)
def test_run_stops_at_first_failing_step(app, failing):
    mocks = {name: Mock(return_value=i != failing) for i, name in enumerate(_RUN_STEPS)}
    with patch.multiple(app, **mocks):
        stats = app.run(max_results=10)

    assert stats is app.stats
    for i, name in enumerate(_RUN_STEPS):
        assert mocks[name].called is (i <= failing), name


def test_validate_configuration_exception_counts_as_failure(app):
    with patch('src.runtime.app.config_is_valid', side_effect=RuntimeError("boom")):
        assert app.validate_configuration() is False

    assert app.stats['errors'] == 1
    app.logger.error.assert_called_once()


def test_bank_and_country_uses_sg_sender_tag(app):
    assert app._get_bank_and_country('hsbc_sg_mail', 'dbs_statement.pdf') == ('DBS', 'SG', '銀行帳戶')


def test_bank_falls_back_to_sender_tag(app):
    assert app._get_bank_and_country('fubon_tw_bhu', 'Statement.pdf', None)[0] == 'Fubon'
    assert app._get_bank_and_country('hsbc_sg', 'x.pdf', None)[:2] == ('HSBC', 'SG')


def _pipeline_mocks(emails, downloads):
    """Mocks for every external call of the pipeline, keyed by name in src.runtime.app."""
    return {
        'get_gmail_service': Mock(return_value=Mock()),
        'search_emails': Mock(return_value=emails),
        'batch_download_pdfs': Mock(return_value=downloads),
        'extract_text_from_pdf': Mock(return_value='Extracted text content'),
        'parse_receipt_text': Mock(return_value=[{'date': '2024-01-01', 'amount': 100.0}]),
        'export_receipts_to_csv': Mock(return_value='/output/receipts.csv'),
        'export_extracted_texts_to_csv': Mock(return_value='/output/texts.csv'),
        'sort_exported_receipt_csvs': Mock(),
    }


def test_full_workflow_success(app):
    mocks = _pipeline_mocks(
        emails=[{'id': 'msg1', 'subject': 'Test', 'from': 'HSBC@mail.hsbc.com.sg'}],
        downloads=[{'filepath': '/tmp/test1.pdf', 'filename': 'test1.pdf', 'sender': 'HSBC@mail.hsbc.com.sg'}],
    )
    with patch.object(app, 'validate_configuration', return_value=True), \
         patch.multiple('src.runtime.app', **mocks):
        stats = app.run()

    assert (stats['emails_found'], stats['pdfs_downloaded'], stats['texts_extracted'], stats['receipts_parsed']) == (1, 1, 1, 1)
    assert stats['errors'] == 0
    mocks['export_receipts_to_csv'].assert_called_once()


def test_workflow_with_no_emails(app):
    mocks = _pipeline_mocks(emails=[], downloads=[])
    with patch.object(app, 'validate_configuration', return_value=True), \
         patch.multiple('src.runtime.app', **mocks):
        stats = app.run()

    assert stats['emails_found'] == 0
    assert stats['errors'] == 0


def test_workflow_partial_failure_in_extraction(app):
    mocks = _pipeline_mocks(
        emails=[{'id': 'msg1', 'subject': 'Test', 'from': 'test@example.com'}],
        downloads=[
            {'filepath': '/tmp/test1.pdf', 'filename': 'test1.pdf', 'sender': 'test@example.com'},
            {'filepath': '/tmp/test2.pdf', 'filename': 'test2.pdf', 'sender': 'test@example.com'},
        ],
    )

    def extract(pdf_path, password=None):
        if 'test1' in pdf_path:
            return "Text 1"
        raise Exception("Extraction failed")

    mocks['extract_text_from_pdf'] = Mock(side_effect=extract)
    with patch.object(app, 'validate_configuration', return_value=True), \
         patch.multiple('src.runtime.app', **mocks):
        stats = app.run()

    assert (stats['pdfs_downloaded'], stats['texts_extracted'], stats['receipts_parsed']) == (2, 1, 1)
    assert stats['errors'] == 1


def test_workflow_with_parse_failure(app):
    mocks = _pipeline_mocks(
        emails=[{'id': 'msg1', 'subject': 'Test'}],
        downloads=[{'filepath': '/tmp/test1.pdf', 'filename': 'test1.pdf'}],
    )
    mocks['parse_receipt_text'] = Mock(side_effect=Exception("Parse failed"))
    with patch.object(app, 'validate_configuration', return_value=True), \
         patch.multiple('src.runtime.app', **mocks):
        stats = app.run()

    assert stats['texts_extracted'] == 1
    assert stats['receipts_parsed'] == 0
    mocks['export_receipts_to_csv'].assert_not_called()


def test_multiple_emails_workflow(app):
    emails = [{'id': f'msg{i}', 'subject': f'Test{i}', 'from': f'sender{i}@example.com'} for i in range(1, 4)]
    downloads = [{'filepath': f'/tmp/test{i}.pdf', 'filename': f'test{i}.pdf', 'sender': f'sender{i}@example.com'}
                 for i in range(1, 4)]
    mocks = _pipeline_mocks(emails=emails, downloads=downloads)
    with patch.object(app, 'validate_configuration', return_value=True), \
         patch.multiple('src.runtime.app', **mocks):
        stats = app.run()

    assert stats['emails_found'] == 3
    assert stats['pdfs_downloaded'] == 3


def test_main_entrypoint_exists():
    project_root = Path(__file__).resolve().parent.parent
    content = (project_root / 'main.py').read_text()
    assert 'def main()' in content


def test_parse_receipts_collects_statement_balances_even_without_transactions(app, monkeypatch):
    """An empty DBS statement yields no rows but its account balances still reach balances.csv."""
    app.extracted_texts = [{'text': '帳戶摘要\n活期儲蓄存款 60765**818* TWD 1,234.50\n', 'file_info': {'filepath': '/tmp/dbs.pdf', 'filename': 'dbs.pdf', 'sender_tag': 'dbs'}}]
    monkeypatch.setattr('src.runtime.app.parse_receipt_text', lambda *_a, **_k: [])
    app.parse_receipts(max_workers=1)
    assert [(b['bank'], b['balance'], b['source_file']) for b in app.balances] == [('DBS Taiwan', 1234.5, 'dbs.pdf')]
    with patch('src.runtime.app.export_balances_to_csv', return_value='output/balances.csv') as exp, \
         patch('src.runtime.app.export_extracted_texts_to_csv', return_value='x.csv'):
        assert app.export_results() is True
        exp.assert_called_once_with(app.balances)
