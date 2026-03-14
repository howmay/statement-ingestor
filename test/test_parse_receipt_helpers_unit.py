from src.parsing.llm.parse_receipt import (
    _calculate_max_tokens,
    _extract_json_payload,
    _fix_truncated_json_enhanced,
    _merge_transaction_results,
)


def test_parse_receipt_extract_json_payload_wrapper():
    raw = 'prefix {"transactions": []}'
    assert _extract_json_payload(raw).startswith('{')


def test_parse_receipt_fix_truncated_json_wrapper():
    fixed = _fix_truncated_json_enhanced('{"transactions": [{"date": "2026-01-01"')
    assert fixed is not None


def test_parse_receipt_calculate_max_tokens_wrapper():
    assert _calculate_max_tokens(1000) >= 1000
    assert _calculate_max_tokens(100000) == 4000


def test_parse_receipt_merge_wrapper():
    out = _merge_transaction_results([
        [{'date': '2026-01-01', 'amount': 1.0, 'expense_name': 'x'}],
        [{'date': '2026-01-01', 'amount': 1.0, 'expense_name': 'x'}],
    ])
    assert len(out) == 1
