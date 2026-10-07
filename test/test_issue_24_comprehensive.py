"""Comprehensive pytest coverage for Issue #24 large-transaction handling."""

from __future__ import annotations

import json
import os
from datetime import datetime
from unittest.mock import MagicMock, patch

import src.parsing.llm.parse_receipt as pr
from src.parsing.llm import chunking, json_repair
from src.parsing.llm.parse_receipt import parse_receipt_text


def generate_large_hsbc_statement(num_transactions: int = 50) -> str:
    statement = """HSBC CREDIT CARD STATEMENT
Account: ************1234
Statement Date: 2026-03-10
Currency: TWD

TRANSACTION DETAILS:
"""

    base_date = datetime(2026, 3, 1)
    for i in range(num_transactions):
        date = (base_date.replace(day=1) if i % 30 == 0 else base_date).strftime('%Y-%m-%d')
        amount = 1000 + (i * 50) % 5000
        statement += f"{date} Merchant_{i:03d} NT${amount:,.2f}\n"

    statement += """
SUMMARY:
Total Amount Due: NT$45,678.90
"""
    return statement



def test_large_statement_chunking():
    large_text = generate_large_hsbc_statement(50)
    source_info = {'sender_tag': 'hsbc', 'sender': 'HSBC Bank'}

    assert chunking.should_enable_chunking(large_text, source_info) is True

    chunks = chunking.chunk_text_by_transactions(large_text, max_chunk_size=1000, min_transactions_per_chunk=3)
    assert len(chunks) > 1
    assert all(chunk_text for chunk_text, _ in chunks)



def test_truncated_json_repair():
    truncated_json = '{"transactions":[{"date":"2026-03-01","amount":1000.0,"currency":"TWD"'
    fixed = json_repair.fix_truncated_json_enhanced(truncated_json, {'expected_keys': ['transactions']})

    assert fixed is not None
    parsed = json.loads(fixed)
    assert 'transactions' in parsed
    assert isinstance(parsed['transactions'], list)



def test_mock_api_with_chunking(monkeypatch):
    monkeypatch.setattr(pr, "STRICT_BANK_PARSER", False)
    monkeypatch.setattr(pr, "ALLOW_MATCHED_BANK_LLM_FALLBACK", True)
    monkeypatch.setenv('OPENAI_API_KEY', 'test-key')
    monkeypatch.setenv('LLM_PROVIDER', 'openai')

    large_text = generate_large_hsbc_statement(35)

    with patch('openai.OpenAI') as mock_openai_class:
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client

        mock_client.chat.completions.create.side_effect = [
            MagicMock(choices=[MagicMock(finish_reason='stop', message=MagicMock(content=json.dumps({
                'transactions': [
                    {
                        'date': '2026-03-01',
                        'amount': 1000.0,
                        'currency': 'TWD',
                        'expense_name': 'Merchant_000',
                        'expense_type': 'Other',
                        'source': 'HSBC Bank',
                        'confidence': 0.9,
                    }
                ]
            })))])
            for _ in range(3)
        ]

        source_info = {'sender_tag': 'hsbc', 'sender': 'HSBC Bank', 'filename': 'large_statement.pdf'}
        transactions = parse_receipt_text(large_text, source_info)

        assert len(transactions) >= 1
        assert mock_client.chat.completions.create.call_count >= 1
