#!/usr/bin/env python3
"""
Test script for multiple transaction extraction from bank statements.
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.llm.parse_receipt import parse_receipt_text

def test_bank_statement_parsing():
    """Test parsing of bank statement with multiple transactions."""
    
    # Sample bank statement text (simplified)
    bank_statement_text = """
    HSBC Credit Card Statement
    Statement Date: 2024-12-31
    Card Number: **** **** **** 1234
    
    Transaction Details:
    
    11/29 12/01 GOOGLE *Google One SGP SINGAPORE 11/29 TWD 8,250
    12/03 12/03 Spotify P3D0790DDD SWE Stockholm 12/03 TWD 298
    12/05 12/05 UBER *UBER TRIP USA San Francisco 12/05 TWD 350
    12/07 12/07 AMAZON *AMAZON PRIME USA Seattle 12/07 TWD 1,250
    11/29 12/01 國外交易服務費 TWD 123
    
    Summary:
    Total Amount Due: TWD 10,271
    Due Date: 2025-01-15
    """
    
    test_source = {
        'sender': 'HSBC@mail.hsbc.com.sg',
        'sender_tag': 'hsbc_sg',
        'filename': 'hsbc_statement.pdf',
        'subject': 'Your HSBC Credit Card Statement - December 2024'
    }
    
    print("Testing bank statement parsing with multiple transactions...")
    print("=" * 60)
    
    try:
        # First test with OpenAI API (if available)
        print("\n1. Testing with OpenAI API (if configured)...")
        try:
            result = parse_receipt_text(bank_statement_text, test_source)
            print(f"   ✓ OpenAI parsing successful")
            print(f"   Extracted {len(result)} transaction(s):")
            for i, tx in enumerate(result):
                print(f"   {i+1}. {tx.get('date')} - {tx.get('expense_name')}: {tx.get('amount')} {tx.get('currency')}")
        except Exception as e:
            print(f"   ✗ OpenAI parsing failed (expected if no API key): {e}")
        
        # Test heuristic parsing (should always work)
        print("\n2. Testing heuristic parsing (fallback)...")
        # Temporarily remove OpenAI API key to force heuristic parsing
        original_api_key = os.environ.get('OPENAI_API_KEY')
        if original_api_key:
            os.environ['OPENAI_API_KEY'] = 'dummy_key_to_force_heuristic'
        
        try:
            result = parse_receipt_text(bank_statement_text, test_source)
            print(f"   ✓ Heuristic parsing successful")
            print(f"   Extracted {len(result)} transaction(s):")
            for i, tx in enumerate(result):
                print(f"   {i+1}. {tx.get('date')} - {tx.get('expense_name')}: {tx.get('amount')} {tx.get('currency')} (confidence: {tx.get('confidence'):.2f})")
            
            # Verify we extracted multiple transactions
            if len(result) > 1:
                print(f"\n   ✅ SUCCESS: Multiple transactions extracted ({len(result)} found)")
            else:
                print(f"\n   ⚠️  WARNING: Only {len(result)} transaction extracted (expected multiple)")
                
        finally:
            # Restore original API key
            if original_api_key:
                os.environ['OPENAI_API_KEY'] = original_api_key
        
        # Test with simpler bank statement format
        print("\n3. Testing simpler bank statement format...")
        simple_statement = """
        Bank Statement
        Date: 2024-12-01
        
        Transactions:
        12/01 NT$ 350.00 Uber ride from Taipei Station
        12/02 NT$ 1,250.00 Amazon purchase
        12/03 NT$ 298.00 Spotify subscription
        12/04 NT$ 8,250.00 Google Cloud services
        
        Total: NT$ 10,148.00
        """
        
        simple_source = {
            'sender': 'bank@example.com',
            'sender_tag': 'bank_tw',
            'filename': 'statement.pdf',
            'subject': 'Monthly Statement'
        }
        
        if original_api_key:
            os.environ['OPENAI_API_KEY'] = 'dummy_key_to_force_heuristic'
        
        try:
            result = parse_receipt_text(simple_statement, simple_source)
            print(f"   ✓ Simple format parsing successful")
            print(f"   Extracted {len(result)} transaction(s)")
            for i, tx in enumerate(result):
                print(f"   {i+1}. {tx.get('date')} - {tx.get('expense_name')}: {tx.get('amount')} {tx.get('currency')}")
        finally:
            if original_api_key:
                os.environ['OPENAI_API_KEY'] = original_api_key
        
        print("\n" + "=" * 60)
        print("Test completed successfully!")
        
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True

if __name__ == '__main__':
    success = test_bank_statement_parsing()
    sys.exit(0 if success else 1)