import logging
import types
import pytest
import src.parsing.llm.parse_receipt as pr
import json
from types import SimpleNamespace
from unittest.mock import Mock, patch, MagicMock
from src.parsing.banks.base import BankParseResult
from src.parsing.llm.parse_receipt import ReceiptParsingError, parse_receipt_text
from datetime import datetime


def test_get_llm_runtime_config_local(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "local")
    monkeypatch.setenv("LOCAL_BASE_URL", "http://127.0.0.1:30000")
    monkeypatch.setenv("LOCAL_MODEL", "qwen-test")
    cfg = pr._get_llm_runtime_config()
    assert cfg["provider"] == "local"
    assert cfg["base_url"].endswith("/v1")
    assert cfg["model"] == "qwen-test"


def test_get_llm_runtime_config_openai_enabled_and_disabled(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    cfg = pr._get_llm_runtime_config()
    assert cfg["provider"] == "openai"
    assert cfg["enabled"] is False

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-test")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.example.com/v1")
    cfg = pr._get_llm_runtime_config()
    assert cfg["enabled"] is True
    assert cfg["model"] == "gpt-test"


def test_parse_receipt_text_empty_raises():
    with pytest.raises(ReceiptParsingError):
        pr.parse_receipt_text("   ")


def test_parse_receipt_text_returns_deterministic_bank_result(monkeypatch):
    txs = [{"date": "2026-01-01", "amount": 1.0, "currency": "TWD", "expense_name": "x", "expense_type": "Other", "source": "Bank", "confidence": 0.9}]
    monkeypatch.setattr(pr, "parse_with_bank_factory", lambda *_: BankParseResult(matched=True, parser_name="hsbc", transactions=txs))

    out = pr.parse_receipt_text("statement text", {"sender_tag": "hsbc"})
    assert out == txs


def test_parse_receipt_text_matched_bank_parser_raises_when_zero_transactions(monkeypatch):
    monkeypatch.setattr(pr, "parse_with_bank_factory", lambda *_: BankParseResult(matched=True, parser_name="hsbc", transactions=[]))

    with pytest.raises(ReceiptParsingError):
        pr.parse_receipt_text("statement text", {"sender_tag": "hsbc"})


def test_parse_receipt_text_known_bank_parser_does_not_fallback_to_llm_when_zero_transactions(monkeypatch):
    monkeypatch.setattr(
        pr,
        "parse_with_bank_factory",
        lambda *_: BankParseResult(matched=True, parser_name="HsbcSgBankParser", transactions=[]),
    )
    llm_called = {"called": False}

    def _mark_llm_call(*_args, **_kwargs):
        llm_called["called"] = True
        return []

    monkeypatch.setattr(pr, "_get_llm_runtime_config", lambda: {"enabled": True, "provider": "local", "model": "m"})
    monkeypatch.setattr(pr, "_parse_with_openai_enhanced", _mark_llm_call)

    with pytest.raises(ReceiptParsingError):
        pr.parse_receipt_text("statement text", {"sender_tag": "hsbc_sg_mail", "filename": "20260322.pdf"})

    assert llm_called["called"] is False


def test_parse_receipt_text_logs_filename_when_entering_llm(monkeypatch):
    monkeypatch.setattr(pr, "parse_with_bank_factory", lambda *_: BankParseResult(matched=False))
    monkeypatch.setattr(pr, "_get_llm_runtime_config", lambda: {"enabled": True, "provider": "openai", "model": "gpt-test"})
    monkeypatch.setattr(
        pr,
        "_parse_with_openai_enhanced",
        lambda *_args, **_kwargs: [
            {
                "date": "2026-01-01",
                "amount": 100.0,
                "currency": "TWD",
                "expense_name": "A",
                "expense_type": "Other",
                "source": "S",
                "confidence": 0.9,
            }
        ],
    )

    with patch.object(pr.logger, "info") as mock_info:
        out = pr.parse_receipt_text(
            "2026-01-01 NT$100.00",
            {"sender_tag": "hsbc", "filename": "statement.pdf"},
        )

    assert len(out) == 1
    logged = "\n".join(str(call.args[0]) for call in mock_info.call_args_list if call.args)
    assert "statement.pdf" in logged
    assert "Attempting openai parsing" in logged

def test_parse_receipt_text_llm_failure_falls_back_to_heuristic(monkeypatch):
    monkeypatch.setattr(pr, "parse_with_bank_factory", lambda *_: BankParseResult(matched=False))
    monkeypatch.setattr(pr, "_get_llm_runtime_config", lambda: {"enabled": True, "provider": "openai", "model": "m"})
    monkeypatch.setattr(pr, "_parse_with_openai_enhanced", Mock(side_effect=RuntimeError("llm fail")))

    with patch.object(pr.logger, "warning") as mock_warning:
        out = pr.parse_receipt_text("2026-01-01 NT$100.00", {"sender_tag": "hsbc", "filename": "wise.pdf"})

    logged = "\n".join(str(call.args[0]) for call in mock_warning.call_args_list if call.args)
    assert "wise.pdf" in logged
    assert "LLM parsing failed" in logged
    assert isinstance(out, list)
    assert len(out) >= 1


def test_parse_with_adaptive_strategy_non_chunking(monkeypatch):
    monkeypatch.setattr(pr.chunking, "should_enable_chunking", lambda *_, **__: False)

    def fake_call_llm(prompt, max_tokens):
        assert "Extract transactions" in prompt
        assert max_tokens == 4000
        return '{"transactions":[{"date":"2026-01-01","amount":100,"currency":"TWD","expense_name":"A","expense_type":"Other","source":"Bank","confidence":0.8}]}'

    out = pr._parse_with_adaptive_strategy(
        text="short text",
        source_info={"sender_tag": "hsbc"},
        source_label="HSBC Bank",
        model_name="m",
        provider_name="openai",
        call_llm=fake_call_llm,
    )

    assert len(out) == 1
    assert out[0]["expense_name"] == "A"


def test_parse_with_adaptive_strategy_chunking_and_merge(monkeypatch):
    monkeypatch.setattr(pr.chunking, "should_enable_chunking", lambda *_, **__: True)
    monkeypatch.setattr(pr.chunking, "chunk_text_by_transactions", lambda *_, **__: [("chunk1", [1]), ("chunk2", [2])])

    responses = [
        '{"transactions":[{"date":"2026-01-01","amount":100,"currency":"TWD","expense_name":"A","expense_type":"Other","source":"Bank","confidence":0.8}]}',
        '{"transactions":[{"date":"2026-01-02","amount":200,"currency":"TWD","expense_name":"B","expense_type":"Other","source":"Bank","confidence":0.8}]}'
    ]

    def fake_call_llm(_prompt, _max_tokens):
        return responses.pop(0)

    with patch.object(pr.logger, "info") as mock_info:
        out = pr._parse_with_adaptive_strategy(
            text="large text",
            source_info={"sender_tag": "hsbc", "filename": "wise.pdf"},
            source_label="HSBC Bank",
            model_name="m",
            provider_name="openai",
            call_llm=fake_call_llm,
        )

    assert len(out) == 2
    assert {x["expense_name"] for x in out} == {"A", "B"}
    logged = "\n".join(str(call.args[0]) for call in mock_info.call_args_list if call.args)
    assert "wise.pdf" in logged
    assert "Split text into 2 chunks" in logged
    assert "Processing chunk 1/2" in logged


def test_parse_with_adaptive_strategy_all_chunks_fail(monkeypatch):
    monkeypatch.setattr(pr.chunking, "should_enable_chunking", lambda *_, **__: True)
    monkeypatch.setattr(pr.chunking, "chunk_text_by_transactions", lambda *_, **__: [("chunk1", [1])])

    def fake_call_llm(_prompt, _max_tokens):
        raise RuntimeError("boom")

    with patch.object(pr.logger, "error") as mock_error:
        with pytest.raises(ReceiptParsingError):
            pr._parse_with_adaptive_strategy(
                text="large text",
                source_info={"sender_tag": "hsbc", "filename": "wise.pdf"},
                source_label="HSBC Bank",
                model_name="m",
                provider_name="openai",
                call_llm=fake_call_llm,
            )

    logged = "\n".join(str(call.args[0]) for call in mock_error.call_args_list if call.args)
    assert "wise.pdf" in logged
    assert "Chunk 1 failed" in logged


def test_extract_and_validate_transactions_paths():
    parsed = {
        "transactions": [
            {
                "date": "2026-01-01",
                "amount": "100.5",
                "currency": "TWD",
                "expense_name": "Bank Transaction",
                "expense_type": "InvalidType",
                "source": "X",
                "confidence": "0.7",
            }
        ]
    }

    out = pr._extract_and_validate_transactions(parsed, {"sender_tag": "hsbc"}, "line with 100.50", "m", "openai")
    assert len(out) == 1
    assert out[0]["expense_type"] == "Other"
    assert isinstance(out[0]["amount"], float)

    with pytest.raises(ReceiptParsingError):
        pr._extract_and_validate_transactions({"transactions": ["not-dict"]}, {}, "", "m", "openai")


def test_heuristic_extractors_and_helpers():
    text = """
    2026/02/01 Some merchant TWD 1,000.00
    Statement total TWD 5,000.00
    115/02/03 Another merchant NT$ 200.00
    """

    txs = pr._extract_multiple_transactions_heuristic(text, {"sender_tag": "fubon"})
    assert len(txs) >= 1

    single = pr._extract_single_transaction_heuristic("2026-02-05 NT$350.00", {"sender_tag": "hsbc"})
    assert single["date"] == "2026-02-05"
    assert single["amount"] == 350.00

    tx = {
        "expense_name": "Bank Transaction",
        "amount": 350.0,
        "date": "2026-02-05",
        "currency": "TWD",
        "expense_type": "Other",
        "source": "HSBC",
        "confidence": 0.5,
    }
    pr._enrich_expense_name_from_text(tx, "Uber trip amount 350.00 TWD")
    assert tx["expense_name"] != "Bank Transaction"

    normalized = pr._validate_and_normalize_transaction(
        {
            "date": "bad-date",
            "amount": "not-number",
            "currency": None,
            "expense_type": "not-valid",
            "confidence": "0.6",
        },
        {},
    )
    assert normalized["date"] is None
    assert normalized["amount"] is None
    assert normalized["currency"] == "TWD"
    assert normalized["expense_type"] == "Other"


def test_parse_with_openai_enhanced_success_via_fake_client(monkeypatch):
    fn = pr._parse_with_openai_enhanced

    class FakeCompletions:
        def create(self, **kwargs):
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content='{"transactions":[{"date":"2026-01-01","amount":100,"currency":"TWD","expense_name":"A","expense_type":"Other","source":"S","confidence":0.9}]}'), finish_reason="stop")]
            )

    class FakeChat:
        def __init__(self):
            self.completions = FakeCompletions()

    class FakeOpenAI:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.chat = FakeChat()

    fake_openai_module = types.SimpleNamespace(OpenAI=FakeOpenAI)

    with patch.dict("sys.modules", {"openai": fake_openai_module}):
        out = fn(
            text="2026-01-01 NT$100.00",
            source_info={"sender_tag": "hsbc"},
            llm_config={
                "enabled": True,
                "api_key": "x",
                "base_url": "http://127.0.0.1:30000/v1",
                "model": "qwen",
                "provider": "local",
                "supports_response_format": False,
            },
        )

    assert len(out) == 1
    assert out[0]["expense_name"] == "A"


def test_parse_with_openai_enhanced_disabled_runtime_raises(monkeypatch):
    fn = pr._parse_with_openai_enhanced

    fake_openai_module = types.SimpleNamespace(OpenAI=lambda **_: None)
    with patch.dict("sys.modules", {"openai": fake_openai_module}):
        with pytest.raises(ReceiptParsingError):
            fn(text="x", source_info={}, llm_config={"enabled": False})


_TX_JSON = '{"transactions":[{"date":"2026-01-01","amount":100,"currency":"TWD","expense_name":"A","expense_type":"Other","source":"S","confidence":0.9}]}'
_LLM_CONFIG = {"enabled": True, "api_key": "x", "model": "m", "provider": "openai"}


def _fake_openai(finish_reasons):
    """Fake OpenAI module whose responses carry the given finish_reasons in order."""
    reasons = list(finish_reasons)

    class FakeCompletions:
        def create(self, **_kwargs):
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=_TX_JSON), finish_reason=reasons.pop(0))]
            )

    class FakeOpenAI:
        def __init__(self, **_kwargs):
            self.chat = SimpleNamespace(completions=FakeCompletions())

    return types.SimpleNamespace(OpenAI=FakeOpenAI)


def test_truncated_json_retries_with_forced_chunking(monkeypatch):
    sizes = []
    real_chunk = pr.chunking.chunk_text_by_transactions

    def spy_chunk(text, max_chunk_size, min_transactions_per_chunk):
        sizes.append(max_chunk_size)
        return real_chunk(text, max_chunk_size=max_chunk_size, min_transactions_per_chunk=min_transactions_per_chunk)

    monkeypatch.setattr(pr.chunking, "chunk_text_by_transactions", spy_chunk)
    text = "2026-01-01 NT$100.00 A\n" * 20  # 20 dates, short: first pass is single-shot

    with patch.dict("sys.modules", {"openai": _fake_openai(["length", "stop", "stop", "stop", "stop", "stop"])}):
        out = pr._parse_with_openai_enhanced(text, {"sender_tag": "hsbc"}, _LLM_CONFIG)

    assert out
    assert len(sizes) == 1  # first pass was single-shot, forced pass chunked
    assert sizes[0] < pr.chunking.MAX_CHUNK_SIZE


def test_first_pass_chunk_truncation_triggers_forced_pass(monkeypatch):
    sizes = []
    real_chunk = pr.chunking.chunk_text_by_transactions

    def spy_chunk(text, max_chunk_size, min_transactions_per_chunk):
        sizes.append(max_chunk_size)
        return real_chunk(text, max_chunk_size=max_chunk_size, min_transactions_per_chunk=min_transactions_per_chunk)

    monkeypatch.setattr(pr.chunking, "chunk_text_by_transactions", spy_chunk)
    text = "2026-01-01 NT$100.00 A\n" * 400  # ~9.2k chars (>= 7000): first pass chunks at MAX_CHUNK_SIZE
    assert len(text) >= 7000

    with patch.dict("sys.modules", {"openai": _fake_openai(["length"] + ["stop"] * 50)}):
        out = pr._parse_with_openai_enhanced(text, {"sender_tag": "hsbc"}, _LLM_CONFIG)

    assert out
    assert len(sizes) == 2
    assert sizes[0] == pr.chunking.MAX_CHUNK_SIZE
    assert sizes[1] < sizes[0]


def test_hsbc_statement_text_without_llm_key_returns_heuristic_transactions(monkeypatch):
    # No deterministic parser matches this text; no LLM key -> heuristics
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


def test_parse_receipt_text_large_statement_with_mocked_openai(monkeypatch):
    monkeypatch.setattr(pr, "parse_with_bank_factory", lambda *_: BankParseResult(matched=False))  # exercise the LLM path
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


def test_parse_receipt_text_with_mocked_openai_client(monkeypatch):
    monkeypatch.setattr(pr, "parse_with_bank_factory", lambda *_: BankParseResult(matched=False))  # exercise the LLM path
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("LLM_PROVIDER", "openai")

    with patch("openai.OpenAI") as mock_openai_class:
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(finish_reason="stop", message=MagicMock(content=json.dumps({
                "transactions": [
                    {
                        "date": "2024-01-01",
                        "amount": 100.0,
                        "currency": "TWD",
                        "expense_name": "Test",
                        "expense_type": "Other",
                        "source": "HSBC",
                        "confidence": 0.9,
                    }
                ]
            })))]
        )

        source_info = {"sender_tag": "hsbc", "sender": "HSBC", "filename": "test.pdf"}
        transactions = parse_receipt_text("2024-01-01 NT$100.00 Test", source_info)

    assert len(transactions) == 1
    assert transactions[0]["expense_name"] == "Test"
    assert transactions[0]["amount"] == 100.0


def test_unknown_llm_provider_uses_local_runtime(monkeypatch, caplog):
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    with caplog.at_level(logging.WARNING):
        cfg = pr._get_llm_runtime_config()
    assert (cfg["provider"], cfg["enabled"]) == ("local", True)
    assert "Unknown LLM_PROVIDER='ollama'" in caplog.text
