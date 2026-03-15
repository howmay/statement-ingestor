import pytest
from src.parsing.banks.factory import get_bank_parser
from src.parsing.banks.dbs import DbsSgBankParser

def test_dbs_sg_bank_detection_from_content():
    """
    模擬使用者手動下載的檔案（寄件人是自己，檔名無 DBS），
    驗證是否能從 PDF 內文識別出 DBS Bank Parser。
    """
    text = "DBS Bank Ltd\nAccount Statement for 083-034486-9\n01 MAR GIRO INWARD 100.00 5000.00"
    source_info = {
        'sender': 'user@example.com',
        'subject': 'Fwd: Statement',
        'filename': 'test_user_Statement_0000000000.pdf'
    }
    
    parser = get_bank_parser(text, source_info)
    assert isinstance(parser, DbsSgBankParser), "應該識別為 DbsSgBankParser"

def test_dbs_sg_bank_detection_from_content_further_down():
    """
    模擬 DBS Bank 出現在內文較後方的情境。
    """
    text = "Some random header\n" * 50 + "DBS Bank Ltd\nAccount Statement\n01 MAR GIRO INWARD 100.00 5000.00"
    source_info = {
        'sender': 'me',
        'subject': 'Statement',
        'filename': 'test_user_Statement_0000000000.pdf'
    }
    
    parser = get_bank_parser(text, source_info)
    assert isinstance(parser, DbsSgBankParser), "即使關鍵字在後方也應識別為 DbsSgBankParser"

def test_dbs_sg_bank_year_inference_from_text_old_year():
    """
    驗證是否能從內文的日期 (例如 2024 年) 正確推斷交易年份，即使當前是 2026 年。
    """
    text = "DBS Bank\nDate of Statement: 28 Feb 2024\n01 FEB GIRO 100.00 5000.00"
    parser = DbsSgBankParser(text)
    result = parser.parse()
    
    assert result.matched
    tx = result.transactions[0]
    assert tx['date'].startswith('2024-02'), f"交易年份應推斷為 2024, 得到 {tx['date']}"
