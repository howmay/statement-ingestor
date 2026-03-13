import types
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

import src.parsing.llm.parse_receipt as pr
from src.parsing.banks.base import BankParseResult
from src.parsing.llm.parse_receipt import ReceiptParsingError


def test_get_llm_runtime_config_local_and_ollama(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "local")
    monkeypatch.setenv("LOCAL_BASE_URL", "http://127.0.0.1:30000")
    monkeypatch.setenv("LOCAL_MODEL", "qwen-test")
    cfg = pr._get_llm_runtime_config()
    assert cfg["provider"] == "local"
    assert cfg["base_url"].endswith("/v1")
    assert cfg["model"] == "qwen-test"

    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    cfg = pr._get_llm_runtime_config()
    assert cfg["provider"] == "ollama"
    assert cfg["enabled"] is True


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


def test_parse_receipt_text_strict_bank_parser_raises_when_zero_transactions(monkeypatch):
    monkeypatch.setenv("STRICT_BANK_PARSER", "true")
    monkeypatch.setattr(pr, "parse_with_bank_factory", lambda *_: BankParseResult(matched=True, parser_name="hsbc", transactions=[]))

    with pytest.raises(ReceiptParsingError):
        pr.parse_receipt_text("statement text", {"sender_tag": "hsbc"})


def test_parse_receipt_text_non_strict_falls_back_to_heuristic(monkeypatch):
    monkeypatch.setenv("STRICT_BANK_PARSER", "false")
    monkeypatch.setattr(pr, "parse_with_bank_factory", lambda *_: BankParseResult(matched=True, parser_name="hsbc", transactions=[]))
    monkeypatch.setattr(pr, "_get_llm_runtime_config", lambda: {"enabled": False})

    out = pr.parse_receipt_text("2026-01-01 NT$100.00", {"sender_tag": "hsbc"})
    assert isinstance(out, list)
    assert len(out) >= 1


def test_parse_receipt_text_llm_failure_falls_back_to_heuristic(monkeypatch):
    monkeypatch.setattr(pr, "parse_with_bank_factory", lambda *_: BankParseResult(matched=False))
    monkeypatch.setattr(pr, "_get_llm_runtime_config", lambda: {"enabled": True, "provider": "openai", "model": "m"})
    monkeypatch.setattr(pr, "_parse_with_openai_enhanced", Mock(side_effect=RuntimeError("llm fail")))

    out = pr.parse_receipt_text("2026-01-01 NT$100.00", {"sender_tag": "hsbc"})
    assert isinstance(out, list)
    assert len(out) >= 1


def test_parse_with_adaptive_strategy_non_chunking(monkeypatch):
    monkeypatch.setattr(pr, "_should_enable_chunking", lambda *_, **__: False)

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
    monkeypatch.setattr(pr, "_should_enable_chunking", lambda *_, **__: True)
    monkeypatch.setattr(pr, "_chunk_text_by_transactions", lambda *_, **__: [("chunk1", [1]), ("chunk2", [2])])

    responses = [
        '{"transactions":[{"date":"2026-01-01","amount":100,"currency":"TWD","expense_name":"A","expense_type":"Other","source":"Bank","confidence":0.8}]}',
        '{"transactions":[{"date":"2026-01-02","amount":200,"currency":"TWD","expense_name":"B","expense_type":"Other","source":"Bank","confidence":0.8}]}'
    ]

    def fake_call_llm(_prompt, _max_tokens):
        return responses.pop(0)

    out = pr._parse_with_adaptive_strategy(
        text="large text",
        source_info={"sender_tag": "hsbc"},
        source_label="HSBC Bank",
        model_name="m",
        provider_name="openai",
        call_llm=fake_call_llm,
    )

    assert len(out) == 2
    assert {x["expense_name"] for x in out} == {"A", "B"}


def test_parse_with_adaptive_strategy_all_chunks_fail(monkeypatch):
    monkeypatch.setattr(pr, "_should_enable_chunking", lambda *_, **__: True)
    monkeypatch.setattr(pr, "_chunk_text_by_transactions", lambda *_, **__: [("chunk1", [1])])

    def fake_call_llm(_prompt, _max_tokens):
        raise RuntimeError("boom")

    with pytest.raises(ReceiptParsingError):
        pr._parse_with_adaptive_strategy(
            text="large text",
            source_info={"sender_tag": "hsbc"},
            source_label="HSBC Bank",
            model_name="m",
            provider_name="openai",
            call_llm=fake_call_llm,
        )


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


def test_parse_multiple_receipts_continues_on_error(monkeypatch):
    calls = {"n": 0}

    def fake_parse(text, source):
        calls["n"] += 1
        if text == "bad":
            raise RuntimeError("bad")
        return [{"expense_name": text}]

    monkeypatch.setattr(pr, "parse_receipt_text", fake_parse)

    out = pr.parse_multiple_receipts(["ok1", "bad", "ok2"], [{}, {}, {}])
    assert len(out) == 2
    assert calls["n"] == 3


def test_parse_with_openai_enhanced_success_via_fake_client(monkeypatch):
    # Use undecorated function body to focus on logic.
    fn = pr._parse_with_openai_enhanced.__wrapped__

    class FakeCompletions:
        def create(self, **kwargs):
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content='{"transactions":[{"date":"2026-01-01","amount":100,"currency":"TWD","expense_name":"A","expense_type":"Other","source":"S","confidence":0.9}]}'))]
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
    fn = pr._parse_with_openai_enhanced.__wrapped__

    fake_openai_module = types.SimpleNamespace(OpenAI=lambda **_: None)
    with patch.dict("sys.modules", {"openai": fake_openai_module}):
        with pytest.raises(ReceiptParsingError):
            fn(text="x", source_info={}, llm_config={"enabled": False})
