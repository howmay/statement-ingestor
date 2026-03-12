"""
Unit tests for Gmail email fetching module.
"""
import pytest
from unittest.mock import Mock, patch
import sys
from functools import wraps

# No more sys.modules hack here

# Now import the module
from src.fetch.fetch_emails import build_gmail_query, search_emails


class TestFetchEmails:
    """Test suite for Gmail email fetching functions."""
    
    @pytest.fixture(autouse=True)
    def mock_retry(self):
        """Mock the retry decorator for all tests in this class."""
        with patch('src.utils.retry.retry_gmail', side_effect=lambda f: f):
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
        assert query == "has:attachment filename:pdf"

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

    @patch('src.fetch.fetch_emails.TARGET_SENDERS', ["default@example.com"])
    @patch('src.fetch.fetch_emails.TARGET_KEYWORDS', ["default"])
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
        emails = search_emails(mock_service, max_results=1)
        
        assert len(emails) == 1
        assert emails[0]['id'] == 'msg1'
        assert emails[0]['sender'] == 'Bank <bank@example.com>'
        assert emails[0]['subject'] == 'Monthly Statement'
        
        # Verify API calls
        mock_list_call.assert_called()
        mock_get_call.assert_called_with(userId='me', id='msg1', format='metadata', metadataHeaders=['From', 'Subject'])

    def test_search_emails_no_results(self):
        """Test searching emails when no results are found."""
        mock_service = Mock()
        mock_service.users().messages().list().execute.return_value = {'messages': []}
        
        emails = search_emails(mock_service, senders=["test@example.com"], keywords=["test"])
        
        assert len(emails) == 0
