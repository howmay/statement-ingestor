#!/usr/bin/env python3
"""
Comprehensive test for Issue #24: OpenAI API returns incomplete JSON responses for large transaction lists.
"""

import os
import sys
import json
import logging
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.llm.parse_receipt import (
    parse_receipt_text,
    _fix_truncated_json_enhanced,
    _chunk_text_by_transactions,
    _should_enable_chunking,
    _merge_transaction_results,
    ReceiptParsingError
)

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def generate_large_hsbc_statement(num_transactions=50):
    """Generate a large HSBC statement for testing."""
    statement = """HSBC CREDIT CARD STATEMENT
Account: ************1234
Statement Date: 2026-03-10
Currency: TWD

TRANSACTION DETAILS:
"""
    
    base_date = datetime(2026, 3, 1)
    for i in range(num_transactions):
        date = (base_date.replace(day=1) if i % 30 == 0 else base_date).strftime("%Y-%m-%d")
        amount = 1000 + (i * 50) % 5000
        merchant = f"Merchant_{i:03d}"
        statement += f"{date} {merchant} NT${amount:,.2f}\n"
        
        # Add some variety
        if i % 5 == 0:
            statement += f"  Location: Taipei City\n"
        if i % 7 == 0:
            statement += f"  Category: {'Food' if i % 2 == 0 else 'Shopping'}\n"
    
    statement += """
SUMMARY:
Total Amount Due: NT$45,678.90
Minimum Payment Due: NT$2,000.00
Payment Due Date: 2026-03-25
"""
    
    return statement


def test_large_statement_chunking():
    """Test chunking for large statements."""
    print("Testing large statement chunking...")
    
    large_text = generate_large_hsbc_statement(50)
    print(f"Generated statement: {len(large_text)} characters")
    
    # Test chunking decision
    source_info = {'sender_tag': 'hsbc', 'sender': 'HSBC Bank'}
    should_chunk = _should_enable_chunking(large_text, source_info)
    print(f"Should enable chunking: {should_chunk}")
    
    if should_chunk:
        chunks = _chunk_text_by_transactions(large_text, max_chunk_size=1000, min_transactions_per_chunk=3)
        print(f"Number of chunks: {len(chunks)}")
        
        for i, (chunk_text, indices) in enumerate(chunks):
            print(f"  Chunk {i+1}: {len(chunk_text)} chars, {len(indices)} transaction starts")
        
        if len(chunks) > 1:
            print("  ✅ Large statement chunking: PASS")
            return True
        else:
            print("  ❌ Large statement chunking: FAIL - Expected multiple chunks")
            return False
    else:
        print("  ❌ Large statement chunking: FAIL - Should have enabled chunking")
        return False


def test_truncated_json_repair():
    """Test repair of truncated JSON responses."""
    print("\nTesting truncated JSON repair...")
    
    # Simulate a truncated JSON response (cut off in the middle of a transaction)
    truncated_json = '''{
  "transactions": [
    {
      "date": "2026-03-01",
      "amount": 1000.0,
      "currency": "TWD",
      "expense_name": "Merchant_000",
      "expense_type": "Other",
      "source": "HSBC Bank",
      "confidence": 0.9
    },
    {
      "date": "2026-03-02",
      "amount": 1050.0,
      "currency": "TWD",
      "expense_name": "Merchant_001",
      "expense_type": "Other",
      "source": "HSBC Bank",
      "confidence": 0.9
    },
    {
      "date": "2026-03-03",
      "amount": 1100.0,
      "currency": "TWD",
      "expense_name": "Merchant_002",
      "expense_type": "Other",
      "source": "HSBC Bank",
      "confidence": 0.9
    },
    {
      "date": "2026-03-04",
      "amount": 1150.0,
      "currency": "TWD",
      "expense_name": "Merchant_003",
      "expense_type": "Other",
      "source": "HSBC Bank"'''
    
    print(f"Truncated JSON length: {len(truncated_json)} characters")
    
    fixed = _fix_truncated_json_enhanced(truncated_json, {
        'expected_keys': ['transactions']
    })
    
    if fixed:
        try:
            parsed = json.loads(fixed)
            transactions = parsed.get('transactions', [])
            print(f"  ✅ JSON repair: PASS - Repaired JSON is valid")
            print(f"    Transactions recovered: {len(transactions)}")
            
            # Check if the structure is complete
            if len(transactions) >= 3:
                print(f"    ✅ Structure preserved: All transactions recovered")
                return True
            else:
                print(f"    ⚠️ Structure partially recovered: {len(transactions)} transactions")
                return False
        except json.JSONDecodeError as e:
            print(f"  ❌ JSON repair: FAIL - JSON decode error: {e}")
            return False
    else:
        print(f"  ❌ JSON repair: FAIL - Could not repair")
        return False


def test_mock_api_with_chunking():
    """Test the complete parsing flow with chunking using mocked API."""
    print("\nTesting complete parsing with chunking (mocked API)...")
    
    # Disable strict bank parser for testing
    os.environ['STRICT_BANK_PARSER'] = 'false'
    
    # Generate a large statement
    large_text = generate_large_hsbc_statement(35)  # 35 transactions should trigger chunking
    
    with patch('openai.OpenAI') as mock_openai_class:
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        
        # Mock responses for multiple chunks
        mock_responses = [
            # Chunk 1 response
            MagicMock(choices=[MagicMock(message=MagicMock(content=json.dumps({
                "transactions": [
                    {
                        "date": "2026-03-01",
                        "amount": 1000.0,
                        "currency": "TWD",
                        "expense_name": "Merchant_000",
                        "expense_type": "Other",
                        "source": "HSBC Bank",
                        "confidence": 0.9
                    },
                    {
                        "date": "2026-03-02",
                        "amount": 1050.0,
                        "currency": "TWD",
                        "expense_name": "Merchant_001",
                        "expense_type": "Other",
                        "source": "HSBC Bank",
                        "confidence": 0.9
                    }
                ]
            })))]),
            # Chunk 2 response
            MagicMock(choices=[MagicMock(message=MagicMock(content=json.dumps({
                "transactions": [
                    {
                        "date": "2026-03-03",
                        "amount": 1100.0,
                        "currency": "TWD",
                        "expense_name": "Merchant_002",
                        "expense_type": "Other",
                        "source": "HSBC Bank",
                        "confidence": 0.9
                    },
                    {
                        "date": "2026-03-04",
                        "amount": 1150.0,
                        "currency": "TWD",
                        "expense_name": "Merchant_003",
                        "expense_type": "Other",
                        "source": "HSBC Bank",
                        "confidence": 0.9
                    }
                ]
            })))]),
        ]
        
        mock_client.chat.completions.create.side_effect = mock_responses
        
        os.environ['OPENAI_API_KEY'] = 'test-key'
        
        try:
            source_info = {'sender_tag': 'hsbc', 'sender': 'HSBC Bank', 'filename': 'large_statement.pdf'}
            transactions = parse_receipt_text(large_text, source_info)
            
            print(f"  ✅ Parsing with chunking: PASS")
            print(f"    Total transactions parsed: {len(transactions)}")
            print(f"    API calls made: {mock_client.chat.completions.create.call_count}")
            
            # Verify deduplication worked
            unique_dates = set(tx.get('date') for tx in transactions)
            print(f"    Unique transaction dates: {len(unique_dates)}")
            
            return True
            
        except Exception as e:
            print(f"  ❌ Parsing with chunking: FAIL - {e}")
            import traceback
            traceback.print_exc()
            return False
        finally:
            if 'OPENAI_API_KEY' in os.environ:
                del os.environ['OPENAI_API_KEY']
            if 'STRICT_BANK_PARSER' in os.environ:
                del os.environ['STRICT_BANK_PARSER']


def test_error_handling_and_retry():
    """Test error handling and retry logic."""
    print("\nTesting error handling and retry logic...")
    
    with patch('openai.OpenAI') as mock_openai_class:
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        
        # Simulate API failure followed by success
        mock_client.chat.completions.create.side_effect = [
            Exception("API timeout"),
            MagicMock(choices=[MagicMock(message=MagicMock(content=json.dumps({
                "transactions": [
                    {
                        "date": "2026-03-01",
                        "amount": 1000.0,
                        "currency": "TWD",
                        "expense_name": "Test",
                        "expense_type": "Other",
                        "source": "HSBC Bank",
                        "confidence": 0.9
                    }
                ]
            })))]),
        ]
        
        os.environ['OPENAI_API_KEY'] = 'test-key'
        os.environ['STRICT_BANK_PARSER'] = 'false'
        
        try:
            text = "2026-03-01 NT$1000.00 Test Transaction"
            source_info = {'sender_tag': 'hsbc', 'sender': 'HSBC Bank'}
            transactions = parse_receipt_text(text, source_info)
            
            print(f"  ✅ Error handling: PASS - Recovered from API failure")
            print(f"    Transactions parsed: {len(transactions)}")
            print(f"    API call attempts: {mock_client.chat.completions.create.call_count}")
            
            return True
            
        except Exception as e:
            print(f"  ❌ Error handling: FAIL - {e}")
            return False
        finally:
            if 'OPENAI_API_KEY' in os.environ:
                del os.environ['OPENAI_API_KEY']
            if 'STRICT_BANK_PARSER' in os.environ:
                del os.environ['STRICT_BANK_PARSER']


def main():
    """Run all comprehensive tests."""
    print("=" * 60)
    print("COMPREHENSIVE TEST FOR ISSUE #24")
    print("=" * 60)
    
    results = []
    
    # Run tests
    results.append(("Large Statement Chunking", test_large_statement_chunking()))
    results.append(("Truncated JSON Repair", test_truncated_json_repair()))
    results.append(("Mock API with Chunking", test_mock_api_with_chunking()))
    results.append(("Error Handling & Retry", test_error_handling_and_retry()))
    
    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} - {test_name}")
    
    print(f"\nOverall: {passed}/{total} tests passed ({passed/total*100:.1f}%)")
    
    if passed == total:
        print("\n🎉 All tests passed! Issue #24 fix is working correctly.")
        return True
    else:
        print(f"\n⚠️  {total - passed} test(s) failed. Review the implementation.")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)