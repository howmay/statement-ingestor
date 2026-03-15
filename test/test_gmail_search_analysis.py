from src.integrations.gmail.search_analysis import (
    build_attachment_inventory_query,
    recommend_search_filters,
)


def test_build_attachment_inventory_query_uses_pdf_csv_and_date_range():
    query = build_attachment_inventory_query("2026-02-01", "2026-03-14")

    assert '"statement"' in query
    assert '"對帳單"' in query
    assert "filename:pdf" in query
    assert "filename:csv" in query
    assert "after:2026/02/01" in query
    assert "before:2026/03/15" in query
    assert "保單" in query


def test_recommend_search_filters_separates_positive_and_negative_terms():
    records = [
        {
            "sender": "service@hsbc.com.tw",
            "subject": "匯豐(台灣)商業銀行運籌理財對帳單 2026年02月",
            "attachment_filenames": ["statement.pdf"],
            "body_text": "對帳單明細\n交易明細\n滙豐(台灣)商業銀行股份有限公司2026",
        },
        {
            "sender": "service@bhu.taipeifubon.com.tw",
            "subject": "台北富邦銀行2026年2月 銀行對帳單",
            "attachment_filenames": ["statement.pdf"],
            "body_text": "對帳單期間：2026/02/01~2026/02/28\n交易明細\n台北富邦銀行",
        },
        {
            "sender": "notice@insurance.example",
            "subject": "新光人壽保單通知 2026年02月",
            "attachment_filenames": ["notice.pdf"],
            "body_text": "保單通知\n保險內容\n新光人壽",
        },
        {
            "sender": "promo@bank.example",
            "subject": "活動通知與優惠總覽",
            "attachment_filenames": ["offer.pdf"],
            "body_text": "優惠活動\n立即申辦\n不是對帳單",
        },
    ]

    result = recommend_search_filters(records)

    assert any("對帳單" in term for term in result["include_terms"])
    assert any("銀行對帳單" in term for term in result["include_terms"])
    assert "保單" in result["exclude_terms"]
    assert "活動通知" in result["exclude_terms"]
    assert any(profile["senders"] == ["service@hsbc.com.tw"] for profile in result["profiles"])
    assert "filename:pdf" in result["recommended_query"]
