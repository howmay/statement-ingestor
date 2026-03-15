import pytest
from src.parsing.banks.hsbc_sg import HsbcSgCardParser

def test_hsbc_sg_card_v2_parsing():
    """
    Test HSBC Singapore Credit Card parsing with the real text format discovered.
    """
    text = """
23Jan 22Jan TAOBAO Singapore SG 120.31
Total Account Balance
2.79
28Jan 28Jan PAYMENT-THANKYOU 282.30CR (incl GST)
.
09Feb 07Feb Grab*A-8VXKST8GX8JEAV 0.40
Singapore SG Minimum Payment 2.79
.
14Feb 13Feb Grab*A-8VQJLPHW2THDAV 29.90
Singapore SG CREDIT LIMIT AND INTEREST RATES
20Feb 20Feb FINANCECHARGE 2.49
"""
    parser = HsbcSgCardParser(text)
    result = parser.parse()
    
    assert result.matched
    # Expected transactions: 120.31, -282.30, 0.40, 29.90, 2.49
    assert len(result.transactions) == 5
    
    t1 = result.transactions[0]
    assert t1['amount'] == 120.31
    assert 'TAOBAO' in t1['expense_name']
    
    t2 = result.transactions[1]
    assert t2['amount'] == -282.30
    assert 'PAYMENT-THANKYOU' in t2['expense_name']
    
    t5 = result.transactions[4]
    assert t5['amount'] == 2.49
    assert 'FINANCECHARGE' in t5['expense_name']
