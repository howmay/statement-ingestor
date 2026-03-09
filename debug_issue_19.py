#!/usr/bin/env python3
"""
Debug script for Issue #19: PDF parsing incomplete (only summary extracted).
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.llm.parse_receipt import parse_receipt_text

def test_actual_bank_statement_text():
    """Test with actual bank statement text patterns."""
    
    # Sample text from actual bank statement (simplified)
    # This is the type of text that might be extracted from encrypted PDFs
    actual_statement_text = """
    台北富邦銀行 對帳單
    對帳單期間：2026/02/01~2026/02/28
    客戶：陳兆煇
    帳號：1234567890123456
    
    帳戶總覽：
    存款總額：NT$ 6,269.00
    台幣存款：NT$ 6,164.00
    外幣存款：NT$ 105.00
    
    交易明細：
    日期        摘要                    金額
    2026/02/01  台新銀行轉存款          NT$ 1,000.00
    2026/02/03  信用卡繳款              NT$ 8,546.00
    2026/02/05  網路購物-AMAZON         NT$ 2,350.00
    2026/02/07  餐飲費-星巴克           NT$ 180.00
    2026/02/10  交通費-UBER             NT$ 320.00
    2026/02/15  電信費-中華電信         NT$ 1,199.00
    2026/02/20  保險費-富邦人壽         NT$ 3,500.00
    
    本月支出合計：NT$ 17,095.00
    帳戶餘額：NT$ 6,269.00
    """
    
    test_source = {
        'sender': 'service@bhu.taipeifubon.com.tw',
        'sender_tag': 'fubon',
        'filename': '銀行對帳單.PDF',
        'subject': '台北富邦銀行電子對帳單'
    }
    
    print("Testing actual bank statement text parsing...")
    print("=" * 60)
    
    # Force heuristic parsing (simulate no OpenAI API key)
    original_api_key = os.environ.get('OPENAI_API_KEY')
    if original_api_key:
        os.environ['OPENAI_API_KEY'] = 'dummy_key_to_force_heuristic'
    
    try:
        result = parse_receipt_text(actual_statement_text, test_source)
        print(f"Extracted {len(result)} transaction(s):")
        
        if len(result) > 1:
            print("✅ SUCCESS: Multiple transactions extracted!")
            for i, tx in enumerate(result):
                print(f"  {i+1}. {tx.get('date')} - {tx.get('expense_name')[:50]}: {tx.get('amount')} {tx.get('currency')} (confidence: {tx.get('confidence'):.2f})")
        else:
            print("⚠️  WARNING: Only single transaction extracted")
            for i, tx in enumerate(result):
                print(f"  {i+1}. {tx.get('date')} - {tx.get('expense_name')[:50]}: {tx.get('amount')} {tx.get('currency')} (confidence: {tx.get('confidence'):.2f})")
            
            # Check what was extracted
            if result[0].get('expense_name') == 'Bank Statement Transaction':
                print("\n❌ PROBLEM: Only extracted generic 'Bank Statement Transaction'")
                print("   This suggests heuristic parsing fell back to single transaction extraction")
            else:
                print(f"\nℹ️  INFO: Extracted: {result[0].get('expense_name')}")
        
        # Analyze the text to see what patterns should be matched
        print("\n" + "=" * 60)
        print("Text analysis for transaction patterns:")
        
        lines = actual_statement_text.split('\n')
        transaction_lines = []
        for line in lines:
            # Look for lines with date patterns and amounts
            if '2026/' in line and ('NT$' in line or 'NTD' in line):
                transaction_lines.append(line.strip())
        
        print(f"Found {len(transaction_lines)} potential transaction lines in text:")
        for line in transaction_lines:
            print(f"  - {line}")
            
    finally:
        if original_api_key:
            os.environ['OPENAI_API_KEY'] = original_api_key
    
    return len(result) > 1

def test_problematic_text():
    """Test with text that might cause problems."""
    
    # Text that might cause the heuristic to fail
    problematic_text = """
    對帳單期間：2026/02/01~2026/02/28
    若您對本對帳單有任何疑問，
    請洽詢本行客服 02-8751-6665
    陳兆煇 君 啟
    或洽北屯分行為您服務
    連絡電話：0424228336
    帳 戶 總 覽
    資產 本月餘額(折合台幣) 貸款 本月餘額(折合台幣)
    存款 6,269.00 分期型房貸 ­
    台幣存款 6,164.00 循環型貸款 ­
    外幣存款 105.00
    """
    
    test_source = {
        'sender': 'service@bhu.taipeifubon.com.tw',
        'sender_tag': 'fubon',
        'filename': '銀行對帳單.PDF',
        'subject': '台北富邦銀行電子對帳單'
    }
    
    print("\n" + "=" * 60)
    print("Testing problematic text (only summary, no transaction details)...")
    
    # Force heuristic parsing
    original_api_key = os.environ.get('OPENAI_API_KEY')
    if original_api_key:
        os.environ['OPENAI_API_KEY'] = 'dummy_key_to_force_heuristic'
    
    try:
        result = parse_receipt_text(problematic_text, test_source)
        print(f"Extracted {len(result)} transaction(s):")
        
        for i, tx in enumerate(result):
            print(f"  {i+1}. {tx.get('date')} - {tx.get('expense_name')[:50]}: {tx.get('amount')} {tx.get('currency')} (confidence: {tx.get('confidence'):.2f})")
        
        if result[0].get('expense_name') == 'Bank Statement Transaction':
            print("\n❌ CONFIRMED: This text only extracts generic summary")
            print("   Reason: Text contains only account summary, no transaction details")
            print("   Solution: Need to handle PDFs where transaction details are on separate pages")
            
    finally:
        if original_api_key:
            os.environ['OPENAI_API_KEY'] = original_api_key
    
    return result

if __name__ == '__main__':
    print("Debugging Issue #19: PDF parsing incomplete")
    print("=" * 60)
    
    # Test 1: Ideal bank statement text
    success1 = test_actual_bank_statement_text()
    
    # Test 2: Problematic text (only summary)
    result2 = test_problematic_text()
    
    print("\n" + "=" * 60)
    print("CONCLUSION:")
    
    if success1:
        print("✅ Multi-transaction extraction works when text contains transaction details")
    else:
        print("❌ Multi-transaction extraction fails even with transaction details")
    
    if result2[0].get('expense_name') == 'Bank Statement Transaction':
        print("✅ Issue confirmed: PDFs with only summary text extract generic transaction")
        print("\nROOT CAUSE ANALYSIS:")
        print("1. Some bank statement PDFs have transaction details on separate pages")
        print("2. PDF extraction might only get first page or summary page")
        print("3. Encrypted PDFs might fail to extract any text")
        print("\nSOLUTIONS:")
        print("1. Improve PDF extraction to get all pages")
        print("2. Handle encrypted PDFs with passwords from config")
        print("3. Add better error reporting for failed PDF extraction")
    
    print("\n" + "=" * 60)