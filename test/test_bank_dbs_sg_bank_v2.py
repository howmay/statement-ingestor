import pytest
from src.parsing.banks.dbs import DbsSgBankParser

def test_dbs_sg_bank_v2_parsing():
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
