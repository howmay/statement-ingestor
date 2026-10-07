from src.parsing.banks.factory import get_bank_parser
from src.parsing.banks.dbs import DbsSgBankParser, DbsSgCardParser


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


def test_dbs_sg_bank_statement_text():
    """
    Test DBS Singapore Bank Statement parsing with real text snippet.
    """
    text = """
Balance Brought Forward SGD 414.95
02/02/2026 Advice FAST Payment / Receipt 2,000.00 2,414.95
752664X418761
20260202HSBCSGS2BRT0012621
OTHER
02/02/2026 Debit Card Transaction 23.51 2,891.44
BBMSL GUIJI TST HONG KONG HKG 30JAN
4628-4500-7146-3468 HKD140.00
"""
    parser = DbsSgBankParser(text)
    result = parser.parse()
    
    assert result.matched
    assert len(result.transactions) == 2
    
    t1 = result.transactions[0]
    assert t1['date'] == '2026-02-02'
    assert t1['amount'] == 2000.00
    assert t1['cashflow_side'] == 'income'
    assert 'Advice FAST Payment' in t1['expense_name']
    
    t2 = result.transactions[1]
    assert t2['date'] == '2026-02-02'
    assert t2['amount'] == 23.51
    assert t2['cashflow_side'] == 'expense'
    assert 'Debit Card Transaction' in t2['expense_name']
    assert 'BBMSL GUIJI TST' in t2['expense_name']


def test_dbs_sg_card_parser():
    text = "DBS BANK\n01 JAN STARBUCKS 15.00\n02 JAN AMAZON SG 20.00CR"
    source_info = {
        'subject': 'DBS Credit Card Statement',
        'filename': 'DBS_Credit_Card.pdf'
    }
    parser = get_bank_parser(text, source_info)
    assert isinstance(parser, DbsSgCardParser)
    
    result = parser.parse()
    assert result.matched
    assert len(result.transactions) == 2
    
    t1 = result.transactions[0]
    assert t1['amount'] == 15.00
    assert 'STARBUCKS' in t1['expense_name']
    
    t2 = result.transactions[1]
    assert t2['amount'] == -20.00
    assert 'AMAZON SG' in t2['expense_name']

def test_dbs_sg_bank_parser():
    text = "DBS BANK Account Statement\n01 MAR GIRO INWARD PAYNOW-FROM 1,000.00 5,000.00\n02 MAR IBANK WITHDRAWAL 200.00 4,800.00"
    # DBS keyword in text, Statement in filename
    source_info = {
        'subject': 'Your Monthly Statement 2026-03',
        'filename': 'test_user_Statement_0000000000.pdf'
    }
    parser = get_bank_parser(text, source_info)
    assert isinstance(parser, DbsSgBankParser)
    
    result = parser.parse()
    assert result.matched
    assert len(result.transactions) == 2
    
    t1 = result.transactions[0]
    assert t1['date'] == "2026-03-01"
    assert t1['amount'] == 1000.00
    assert t1['cashflow_side'] == 'income'
    
    t2 = result.transactions[1]
    assert t2['amount'] == 200.00
    assert t2['cashflow_side'] == 'expense'
