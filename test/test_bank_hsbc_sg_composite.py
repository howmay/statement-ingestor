import pytest
from src.parsing.banks.hsbc_sg import HsbcSgBankParser

def test_hsbc_sg_composite_statement_parsing():
    """
    Test HSBC Singapore Composite Statement parsing with real text snippet.
    """
    text = """
EVERYDAY GLOBAL ACC 142-05XXXX-221
Date TransactionDetails Deposits Withdrawals Balance(DR=Debit)
BALANCEBROUGHTFORWARD 45,409.32
02Feb2026 REFYIB1-55722 2,000.00 43,409.32
REFYIB1-55724 500.00 42,909.32
REFIB02-38091 1,450.00 41,459.32
05Feb2026 EVERYDAY+BONUSINTEREST
REFZDD4-00034 7.04 41,466.36
26Feb2026 SALA
REFYPB9-96414 11,360.00 52,828.08
"""
    parser = HsbcSgBankParser(text)
    result = parser.parse()
    
    assert result.matched
    # Expected transactions: 2,000.00, 500.00, 1,450.00, 7.04, 11,360.00
    assert len(result.transactions) == 5
    
    # Verify sides
    sides = [t['cashflow_side'] for t in result.transactions]
    assert sides == ['expense', 'expense', 'expense', 'income', 'income']
