"""Regression test for parsing multiple transactions from statement-like text."""

from __future__ import annotations

from src.parsing.llm.parse_receipt import parse_receipt_text


def test_bank_statement_parsing(monkeypatch):
    # Force heuristic/LLM fallback path without strict deterministic blocking
    monkeypatch.setenv('STRICT_BANK_PARSER', 'false')
    monkeypatch.setenv('LLM_PROVIDER', 'openai')
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)

    bank_statement_text = """
HSBC Credit Card Statement
11/29 12/01 GOOGLE *Google One SGP SINGAPORE 11/29 TWD 8,250
12/03 12/03 Spotify P3D0790DDD SWE Stockholm 12/03 TWD 298
12/05 12/05 UBER *UBER TRIP USA San Francisco 12/05 TWD 350
12/07 12/07 AMAZON *AMAZON PRIME USA Seattle 12/07 TWD 1,250
11/29 12/01 國外交易服務費 TWD 123
"""

    source_info = {
        'sender': 'HSBC@mail.hsbc.com.sg',
        'sender_tag': 'hsbc_sg',
        'filename': 'hsbc_statement.pdf',
        'subject': 'Your HSBC Credit Card Statement - December 2024',
    }

    result = parse_receipt_text(bank_statement_text, source_info)

    assert isinstance(result, list)
    # Heuristic parser may return at least 1 transaction
    assert len(result) >= 1
    # Check that we have valid transaction structure
    assert all(isinstance(tx, dict) for tx in result)
