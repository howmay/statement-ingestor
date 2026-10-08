import pytest
import src.integrations.gmail.fetch as fe
from unittest.mock import Mock
from src.integrations.gmail.fetch import build_gmail_query, search_emails


class TestFetchEmails:
    """Test suite for Gmail email fetching functions."""

    def test_build_gmail_query_single_sender_single_keyword(self):
        """Test building Gmail query with single sender and keyword."""
        senders = ["bank@example.com"]
        keywords = ["statement"]
        query = build_gmail_query(senders, keywords)

        assert 'from:"bank@example.com"' in query
        assert '"statement"' in query
        assert "(filename:pdf OR filename:csv)" in query

    def test_build_gmail_query_multiple_senders_multiple_keywords(self):
        """Test building Gmail query with multiple senders and keywords."""
        senders = ["bank1@example.com", "bank2@example.com"]
        keywords = ["statement", "invoice"]
        query = build_gmail_query(senders, keywords)

        assert '(from:"bank1@example.com" OR from:"bank2@example.com")' in query
        assert '("statement" OR "invoice")' in query
        assert "(filename:pdf OR filename:csv)" in query

    def test_build_gmail_query_no_senders_no_keywords(self):
        """Test building Gmail query with no senders or keywords."""
        query = build_gmail_query([], [])
        assert '"statement"' in query
        assert '"對帳單"' in query
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

        assert '"statement"' in query
        assert '"對帳單"' in query
        assert '"信用卡帳單"' in query
        assert '"銀行對帳單"' in query
        assert '"transaction detail"' in query
        assert '(filename:pdf OR filename:csv)' in query
        assert '-("保單" OR "人壽" OR "活動通知" OR "核卡通知" OR "應付憑據" OR "Investment Statement" OR "Margin Account")' in query
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
        assert '"statement"' in query
        assert '"銀行對帳單"' in query
        assert 'filename:pdf' in query
        assert '-("保單" OR "人壽" OR "活動通知" OR "核卡通知" OR "應付憑據" OR "Investment Statement" OR "Margin Account")' in query

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


def test_normalize_gmail_date_formats():
    assert fe._normalize_gmail_date(None) is None
    assert fe._normalize_gmail_date("") is None
    assert fe._normalize_gmail_date("2026-03-01") == "2026/03/01"
    assert fe._normalize_gmail_date("2026/03/01") == "2026/03/01"
    assert fe._normalize_gmail_date("20260301") == "2026/03/01"
    assert fe._normalize_gmail_date("03-01-2026") is None


def test_build_gmail_query_with_compact_date():
    q = fe.build_gmail_query(["a@example.com"], ["invoice"], date_from="20260301", date_to="20260331")
    assert 'after:2026/03/01' in q
    assert 'before:2026/04/01' in q


def test_build_gmail_query_explicit_legacy_inputs_still_work():
    q = fe.build_gmail_query(["a@example.com"], ["invoice"], statement_profiles=[{"senders": ["a@example.com"]}])
    assert 'from:"a@example.com"' in q
    assert 'filename:pdf' in q


def test_search_emails_dedupes_across_pages_and_respects_limit():
    service = Mock()

    list_exec = service.users().messages().list.return_value.execute
    list_exec.side_effect = [
        {
            "messages": [
                {"id": "m1", "threadId": "t1"},
                {"id": "m2", "threadId": "t2"},
            ],
            "nextPageToken": "next-1",
        },
        {
            "messages": [
                {"id": "m2", "threadId": "t2"},  # duplicate
                {"id": "m3", "threadId": "t3"},
            ],
        },
    ]

    get_exec = service.users().messages().get.return_value.execute
    get_exec.side_effect = [
        {"payload": {"headers": [{"name": "From", "value": "A"}, {"name": "Subject", "value": "S1"}]}, "internalDate": "1"},
        {"payload": {"headers": [{"name": "From", "value": "B"}, {"name": "Subject", "value": "S2"}]}, "internalDate": "2"},
        {"payload": {"headers": [{"name": "From", "value": "C"}, {"name": "Subject", "value": "S3"}]}, "internalDate": "3"},
    ]

    out = fe.search_emails(service, senders=["a@example.com"], keywords=["invoice"], max_results=3)
    assert len(out) == 3
    assert [x["id"] for x in out] == ["m1", "m2", "m3"]


def test_search_emails_raises_on_api_error():
    service = Mock()
    service.users().messages().list.return_value.execute.side_effect = RuntimeError("api error")

    with pytest.raises(RuntimeError):
        fe.search_emails(service, senders=["a@example.com"], keywords=["invoice"], max_results=1)


def test_list_attachments_nested_parts_and_single_payload():
    service = Mock()

    # first call: nested payload
    service.users().messages().get.return_value.execute.side_effect = [
        {
            "payload": {
                "parts": [
                    {
                        "parts": [
                            {
                                "filename": "bill.pdf",
                                "mimeType": "application/pdf",
                                "body": {"attachmentId": "a1", "size": 123},
                            },
                            {
                                "filename": "image.png",
                                "mimeType": "image/png",
                                "body": {"attachmentId": "a2", "size": 11},
                            },
                        ]
                    }
                ]
            }
        },
        {
            "payload": {
                "filename": "statement.PDF",
                "mimeType": "application/octet-stream",
                "body": {"attachmentId": "a3", "size": 456},
            }
        },
    ]

    out1 = fe.list_attachments(service, "m1")
    assert len(out1) == 1
    assert out1[0]["attachmentId"] == "a1"

    out2 = fe.list_attachments(service, "m2")
    assert len(out2) == 1
    assert out2[0]["attachmentId"] == "a3"


def test_list_attachments_handles_message_fetch_error():
    service = Mock()
    service.users().messages().get.return_value.execute.side_effect = RuntimeError("boom")

    with pytest.raises(RuntimeError):
        fe.list_attachments(service, "m1")


class _FakeBatch:
    """Mimics googleapiclient BatchHttpRequest: collects requests, runs them on execute()."""
    def __init__(self, callback):
        self.callback = callback
        self.requests = []

    def add(self, request, request_id=None):
        self.requests.append((request_id, request))

    def execute(self, http=None):
        for request_id, request in self.requests:
            self.callback(request_id, request.execute(), None)


def test_search_emails_fetches_metadata_in_one_batch():
    """Per-message metadata goes through new_batch_http_request, not one round trip per message."""
    service = Mock()
    service.users().messages().list.return_value.execute.return_value = {
        'messages': [{'id': 'm1', 'threadId': 't1'}, {'id': 'm2', 'threadId': 't2'}]
    }
    service.new_batch_http_request.side_effect = lambda callback: _FakeBatch(callback)

    def fake_get(userId, id, format, metadataHeaders):
        req = Mock()
        req.execute.return_value = {'internalDate': '1', 'payload': {'headers': [
            {'name': 'From', 'value': f'{id}@bank.example'}, {'name': 'Subject', 'value': f'Statement {id}'}]}}
        return req
    service.users().messages().get.side_effect = fake_get

    emails = search_emails(service, senders=['bank'], keywords=['statement'])

    assert [(e['id'], e['subject']) for e in emails] == [('m1', 'Statement m1'), ('m2', 'Statement m2')]
    assert service.new_batch_http_request.call_count == 1
    # nothing was fetched outside the batch
    for call in service.users().messages().get.return_value.execute.call_args_list:
        raise AssertionError(f"unexpected single get: {call}")
