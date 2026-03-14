from unittest.mock import Mock

import pytest

import src.integrations.gmail.fetch as fe


def _wrapped_search_emails():
    return fe.search_emails.__wrapped__


def _wrapped_list_attachments():
    return fe.list_attachments.__wrapped__


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


def test_build_gmail_query_profile_exclusions_and_or_grouping():
    profiles = [
        {
            "name": "fubon-bank",
            "senders": ["service@bhu.taipeifubon.com.tw"],
            "subject_keywords": ["對帳單", "電子對帳單"],
            "exclude_keywords": ["OTP", "驗證"],
            "has_pdf_attachment": True,
        },
        {
            "name": "esun-card",
            "senders": ["estatement@esunbank.com"],
            "subject_keywords": ["信用卡", "電子帳單"],
            "exclude_keywords": ["活動"],
            "has_pdf_attachment": True,
        },
    ]

    q = fe.build_gmail_query([], [], statement_profiles=profiles)
    assert 'from:"service@bhu.taipeifubon.com.tw"' in q
    assert 'from:"estatement@esunbank.com"' in q
    assert 'subject:"對帳單"' in q
    assert 'subject:"電子帳單"' in q
    assert '-"OTP"' in q
    assert '-"活動"' in q
    assert ' OR ' in q


def test_build_gmail_query_empty_statement_profiles_falls_back_to_legacy():
    q = fe.build_gmail_query(["a@example.com"], ["invoice"], statement_profiles=[])
    assert 'from:"a@example.com"' in q
    assert '"invoice"' in q


def test_search_emails_dedupes_across_pages_and_respects_limit():
    fn = _wrapped_search_emails()
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

    out = fn(service, senders=["a@example.com"], keywords=["invoice"], max_results=3)
    assert len(out) == 3
    assert [x["id"] for x in out] == ["m1", "m2", "m3"]


def test_search_emails_raises_on_api_error():
    fn = _wrapped_search_emails()
    service = Mock()
    service.users().messages().list.return_value.execute.side_effect = RuntimeError("api error")

    with pytest.raises(RuntimeError):
        fn(service, senders=["a@example.com"], keywords=["invoice"], max_results=1)


def test_list_attachments_nested_parts_and_single_payload():
    fn = _wrapped_list_attachments()
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

    out1 = fn(service, "m1")
    assert len(out1) == 1
    assert out1[0]["attachmentId"] == "a1"

    out2 = fn(service, "m2")
    assert len(out2) == 1
    assert out2[0]["attachmentId"] == "a3"


def test_list_attachments_handles_message_fetch_error():
    fn = _wrapped_list_attachments()
    service = Mock()
    service.users().messages().get.return_value.execute.side_effect = RuntimeError("boom")

    with pytest.raises(RuntimeError):
        fn(service, "m1")
