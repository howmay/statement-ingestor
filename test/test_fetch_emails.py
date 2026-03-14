"""
Unit tests for Gmail email fetching module.
"""
import pytest
from unittest.mock import Mock, patch
import sys
from functools import wraps

# No more sys.modules hack here

# Now import the module
from src.integrations.gmail.fetch import build_gmail_query, search_emails


class TestFetchEmails:
    """Test suite for Gmail email fetching functions."""
    
    @pytest.fixture(autouse=True)
    def mock_retry(self):
        """Mock the retry decorator for all tests in this class."""
        with patch('src.support.retry.retry_gmail', side_effect=lambda f: f):
            yield

    def test_build_gmail_query_single_sender_single_keyword(self):
        """Test building Gmail query with single sender and keyword."""
        senders = ["bank@example.com"]
        keywords = ["statement"]
        query = build_gmail_query(senders, keywords)
        
        assert 'from:"bank@example.com"' in query
        assert '"statement"' in query
        assert "has:attachment filename:pdf" in query
        
    def test_build_gmail_query_multiple_senders_multiple_keywords(self):
        """Test building Gmail query with multiple senders and keywords."""
        senders = ["bank1@example.com", "bank2@example.com"]
        keywords = ["statement", "invoice"]
        query = build_gmail_query(senders, keywords)
        
        assert '(from:"bank1@example.com" OR from:"bank2@example.com")' in query
        assert '("statement" OR "invoice")' in query
        assert "has:attachment filename:pdf" in query
        
    def test_build_gmail_query_no_senders_no_keywords(self):
        """Test building Gmail query with no senders or keywords."""
        query = build_gmail_query([], [])
        assert '"credit card statement"' in query
        assert 'filename:pdf' in query

    def test_build_gmail_query_with_date_range(self):
        """Test building query with date range filters."""
        query = build_gmail_query(
            ["bank@example.com"],
            ["statement"],
            date_from="2026-03-01",
            date_to="2026-03-31",
        )

        assert 'after:2026/03/01' in query
        # before is exclusive, so date_to + 1 day
        assert 'before:2026/04/01' in query

    def test_build_gmail_query_uses_generic_statement_terms_by_default(self):
        query = build_gmail_query(
            senders=[],
            keywords=[],
            statement_profiles=[],
            date_from="2026-03-01",
            date_to="2026-03-31",
        )

        assert '"credit card statement"' in query
        assert '"bank statement"' in query
        assert '"信用卡帳單"' in query
        assert '"對帳單"' in query
        assert '(filename:pdf OR filename:xls OR filename:xlsx OR filename:csv)' in query
        assert '-(invoice OR receipt OR order OR shipment OR ticket OR tax OR subscription OR 人壽)' in query
        assert 'before:2026/04/01' in query

    def test_search_emails_success(self):
        """Test searching emails with mocked Gmail API service."""
        mock_service = Mock()
        
        # Mock the list response
        mock_list_call = mock_service.users().messages().list
        mock_list_call.return_value.execute.return_value = {
            'messages': [{'id': 'msg1', 'threadId': 'thread1'}]
        }
        
        # Mock the get response for metadata
        mock_get_call = mock_service.users().messages().get
        mock_get_call.return_value.execute.return_value = {
            'id': 'msg1',
            'threadId': 'thread1',
            'internalDate': '123456789',
            'payload': {
                'headers': [
                    {'name': 'From', 'value': 'Bank <bank@example.com>'},
                    {'name': 'Subject', 'value': 'Monthly Statement'}
                ]
            }
        }
        
        # Call the function
        emails = search_emails(
            mock_service,
            senders=["default@example.com"],
            keywords=["default"],
            max_results=1,
        )
        
        assert len(emails) == 1
        assert emails[0]['id'] == 'msg1'
        assert emails[0]['sender'] == 'Bank <bank@example.com>'
        assert emails[0]['subject'] == 'Monthly Statement'
        
        # Verify API calls
        mock_list_call.assert_called()
        mock_get_call.assert_called_with(userId='me', id='msg1', format='metadata', metadataHeaders=['From', 'Subject'])

    def test_search_emails_uses_generic_statement_query_by_default(self):
        mock_service = Mock()

        mock_service.users().messages().list().execute.return_value = {'messages': []}

        search_emails(mock_service, max_results=10)

        query = mock_service.users().messages().list.call_args.kwargs['q']
        assert '"credit card statement"' in query
        assert '"銀行對帳單"' in query
        assert 'filename:xlsx' in query
        assert '-(invoice OR receipt OR order OR shipment OR ticket OR tax OR subscription OR 人壽)' in query

    def test_search_emails_no_results(self):
        """Test searching emails when no results are found."""
        mock_service = Mock()
        mock_service.users().messages().list().execute.return_value = {'messages': []}
        
        emails = search_emails(mock_service, senders=["test@example.com"], keywords=["test"])
        
        assert len(emails) == 0

    def test_search_emails_without_limit_paginates_to_end(self):
        """When max_results is None, search should iterate until nextPageToken is absent."""
        mock_service = Mock()

        list_call = mock_service.users().messages().list
        list_call.return_value.execute.side_effect = [
            {'messages': [{'id': 'msg1', 'threadId': 't1'}], 'nextPageToken': 'tok2'},
            {'messages': [{'id': 'msg2', 'threadId': 't2'}]},
        ]

        mock_service.users().messages().get.side_effect = [
            Mock(execute=Mock(return_value={
                'id': 'msg1',
                'threadId': 't1',
                'internalDate': '123',
                'payload': {
                    'headers': [
                        {'name': 'From', 'value': 'Bank <bank@example.com>'},
                        {'name': 'Subject', 'value': 'Statement 1'},
                    ]
                }
            })),
            Mock(execute=Mock(return_value={
                'id': 'msg2',
                'threadId': 't2',
                'internalDate': '124',
                'payload': {
                    'headers': [
                        {'name': 'From', 'value': 'Bank <bank@example.com>'},
                        {'name': 'Subject', 'value': 'Statement 2'},
                    ]
                }
            })),
        ]

        emails = search_emails(
            mock_service,
            senders=['bank@example.com'],
            keywords=['statement'],
            max_results=None,
        )

        assert len(emails) == 2
        assert {e['id'] for e in emails} == {'msg1', 'msg2'}
