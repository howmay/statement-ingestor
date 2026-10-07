import json

import pytest

from src.parsing.llm import json_repair


def test_extract_json_payload_from_fenced_text():
    raw = """Here is output:\n```json\n{\"transactions\": []}\n```"""
    assert json_repair.extract_json_payload(raw) == '{"transactions": []}'


def test_fix_truncated_json_enhanced_recovers_structure():
    truncated = '{"transactions": [{"date": "2026-01-01", "amount": 100.0}'
    fixed = json_repair.fix_truncated_json_enhanced(truncated, {"expected_keys": ["transactions"]})
    assert fixed is not None

    parsed = json.loads(fixed)
    assert "transactions" in parsed
    assert isinstance(parsed["transactions"], list)
    assert parsed["transactions"][0]["date"] == "2026-01-01"


def test_finalize_fixed_json_fills_missing_fields():
    parsed = {"transactions": [{"date": "2026-01-01", "amount": 10.0}]}
    fixed = json_repair.finalize_fixed_json(parsed, '{}', {"expected_keys": ["transactions"]})

    obj = json.loads(fixed)
    tx = obj["transactions"][0]
    assert tx["currency"] is None
    assert tx["expense_name"] is None
    assert tx["source"] is None


@pytest.mark.parametrize('truncated, amount', [
    ('{"transactions": [{"date": "2024-01-01", "amount": 100.0}', 100.0),
    ('{"transactions": [{"date": "2024-01-01", "description": "Unfinished', None),
    ('{"transactions": [{"date": "2024-01-01", "amount":', None),
    ('{"transactions": [{"date": "2024-01-01", "amount": 100.0},]', 100.0),
])
def test_fix_truncated_json_enhanced_repairs_common_truncations(truncated, amount):
    fixed = json_repair.fix_truncated_json_enhanced(truncated, {'expected_keys': ['transactions']})

    txs = json.loads(fixed)['transactions']
    assert len(txs) == 1
    assert txs[0]['date'] == '2024-01-01'
    assert txs[0]['amount'] == amount


def test_fix_truncated_json_enhanced_keeps_complete_objects_before_truncation():
    truncated = '''{
  "transactions": [
    {"date": "2026-03-03", "amount": 2880.0, "currency": "TWD", "expense_name": "Credit Card Payment"},
    {"date": "2026-02-27", "amount": 1200.0, "currency": "TWD", "expense_name": "Grocery Store"'''

    fixed = json_repair.fix_truncated_json_enhanced(truncated, {'expected_keys': ['transactions']})

    txs = json.loads(fixed)['transactions']
    assert [t['expense_name'] for t in txs] == ['Credit Card Payment', 'Grocery Store']
