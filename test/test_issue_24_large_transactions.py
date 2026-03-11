#!/usr/bin/env python3
"""
Test for Issue #24: OpenAI API returns incomplete JSON responses for large transaction lists.
"""

import os
import sys
import json
import logging
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.llm.parse_receipt import (
    parse_receipt_text,
    _fix_truncated_json,
    _fix_truncated_json_enhanced,
    _chunk_text_by_transactions,
    _should_enable_chunking,
    _merge_transaction_results,
    ReceiptParsingError
)

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def test_json_repair_basic():
    """Test basic JSON repair functionality."""
    print("Testing basic JSON repair...")
    
    test_cases = [
        ('{"transactions": [{"date": "2024-01-01", "amount": 100.0}', 
         '{"transactions": [{"date": "2024-01-01", "amount": 100.0}]}'),
        ('{"transactions": [{"date": "2024-01-01", "description": "Unfinished',
         '{"transactions": [{"date": "2024-01-01", "description": "Unfinished"}]}'),
        ('{"transactions": [{"date": "2024-01-01", "amount":',
         '{"transactions": [{"date": "2024-01-01", "amount": null}]}'),
        ('{"transactions": [{"date": "2024-01-01", "amount": 100.0},]',
         '{"transactions": [{"date": "2024-01-01", "amount": 100.0}]}'),
    ]
    
    for i, (input_json, expected) in enumerate(test_cases):
        result = _fix_truncated_json_enhanced(input_json, {'expected_keys': ['transactions']})
        if result:
            try:
                parsed = json.loads(result)
                print(f"  Test {i+1}: PASS - Repaired JSON is valid")
            except json.JSONDecodeError:
                print(f"  Test {i+1}: FAIL - Repaired JSON is invalid")
        else:
            print(f"  Test {i+1}: FAIL - Could not repair")
    
    print("Basic JSON repair tests completed\n")


def test_json_repair_complex():
    """Test complex JSON repair with nested structures."""
    print("Testing complex JSON repair...")
    
    truncated_json = '''{
  "transactions": [
    {
      "date": "2026-03-03",
      "amount": 2880.0,
      "currency": "TWD",
      "expense_name": "Credit Card Payment",
      "expense_type": "Other",
      "source": "HSBC Bank",
      "confidence": 0.9
    },
    {
      "date": "2026-02-27",
      "amount": 1200.0,
      "currency": "TWD",
      "expense_name": "Grocery Store",
      "expense_type": "Food",
      "source": "HSBC Bank"'''
    
    fixed = _fix_truncated_json_enhanced(truncated_json, {
        'expected_keys': ['transactions']
    })
    
    if fixed:
        try:
            parsed = json.loads(fixed)
            print(f"  Complex repair: PASS - JSON is valid")
            print(f"    Transactions found: {len(parsed.get('transactions', []))}")
        except json.JSONDecodeError as e:
            print(f"  Complex repair: FAIL - JSON decode error: {e}")
    else:
        print(f"  Complex repair: FAIL - Could not repair")
    
    print("Complex JSON repair tests completed\n")


def test_text_chunking():
    """Test text chunking algorithms."""
    print("Testing text chunking...")
    
    sample_text = """HSBC BANK CREDIT CARD STATEMENT
2026-03-03 NT$2,880.00 Credit Card Payment
2026-03-02 NT$1,500.00 Restaurant ABC
2026-03-01 NT$3,200.00 Online Store XYZ
2026-02-28 NT$850.00 Metro Transportation
2026-02-27 NT$1,200.00 Supermarket DEF
2026-02-26 NT$750.00 Coffee Shop
2026-02-25 NT$2,100.00 Electronics Store
2026-02-24 NT$950.00 Pharmacy
2026-02-23 NT$1,800.00 Clothing Store
"""
    
    chunks = _chunk_text_by_transactions(sample_text, max_chunk_size=100, min_transactions_per_chunk=2)
    
    print(f"Number of chunks created: {len(chunks)}")
    for i, (chunk_text, indices) in enumerate(chunks):
        print(f"  Chunk {i+1}: {len(chunk_text)} chars, {len(indices)} transaction starts")
    
    if len(chunks) > 1:
        print("  Chunking: PASS")
    else:
        print("  Chunking: FAIL")
    
    print("Text chunking tests completed\n")


def test_transaction_merging():
    """Test transaction merging and deduplication."""
    print("Testing transaction merging...")
    
    transactions1 = [
        {'date': '2024-01-01', 'amount': 100.0, 'expense_name': 'A'},
        {'date': '2024-01-02', 'amount': 50.0, 'expense_name': 'B'}
    ]
    
    transactions2 = [
        {'date': '2024-01-01', 'amount': 100.0, 'expense_name': 'A'}, # Duplicate
        {'date': '2024-01-03', 'amount': 200.0, 'expense_name': 'C'}
    ]
    
    merged = _merge_transaction_results([transactions1, transactions2])
    
    print(f"Original: 4, Merged: {len(merged)}")
    if len(merged) == 3:
        print("  Merging: PASS")
    else:
        print("  Merging: FAIL")
    
    print("Transaction merging tests completed\n")


def test_mock_openai_parsing():
    """Test the complete parsing flow with mocked OpenAI API."""
    print("Testing complete parsing flow with mocked API...")
    
    # Patch the function that uses OpenAI instead of the class import
    with patch('openai.OpenAI') as mock_openai_class:
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content=json.dumps({
                "transactions": [
                    {
                        "date": "2024-01-01",
                        "amount": 100.0,
                        "currency": "TWD",
                        "expense_name": "Test",
                        "expense_type": "Other",
                        "source": "HSBC",
                        "confidence": 0.9
                    }
                ]
            })))]
        )
        
        os.environ['OPENAI_API_KEY'] = 'test-key'
        os.environ['STRICT_BANK_PARSER'] = 'false'
        
        try:
            text = "2024-01-01 NT$100.00 Test"
            source_info = {'sender_tag': 'hsbc', 'sender': 'HSBC', 'filename': 'test.pdf'}
            transactions = parse_receipt_text(text, source_info)
            print(f"  Parsing test: PASS - {len(transactions)} transactions parsed")
        except Exception as e:
            print(f"  Parsing test: FAIL - {e}")
            import traceback
            traceback.print_exc()
        finally:
            if 'OPENAI_API_KEY' in os.environ:
                del os.environ['OPENAI_API_KEY']
            if 'STRICT_BANK_PARSER' in os.environ:
                del os.environ['STRICT_BANK_PARSER']
    
    print("Mock API parsing tests completed\n")


if __name__ == "__main__":
    test_json_repair_basic()
    test_json_repair_complex()
    test_text_chunking()
    test_transaction_merging()
    test_mock_openai_parsing()
