import pytest
from src.parsing.banks.hsbc_sg import HsbcSgBankParser

def test_hsbc_sg_full_statement_text():
    """
    Test HSBC Singapore Bank Statement with the full text provided in debug output.
    """
    text = """
EVERYDAY GLOBAL ACC 142-05XXXX-221
Date TransactionDetails Deposits Withdrawals Balance(DR=Debit)
SGD
31Jan2026 BALANCEBROUGHTFORWARD 45,409.32
02Feb2026 SGV02026GO311HZ5
HIB-752664X418761
CHENZHAOHUI
0000000000
BALANCECARRIEDFORWARD 45,409.32
EVERYDAY GLOBAL ACC 142-05XXXX-221
Date TransactionDetails Deposits Withdrawals Balance(DR=Debit)
BALANCEBROUGHTFORWARD 45,409.32
752664X418761
OTHR
REFYIB1-55722 2,000.00 43,409.32
SGV02026JG311HZ6
HIB-214871X917654
CHENZHAOHUI
214871X917654
OTHR
REFYIB1-55724 500.00 42,909.32
03Feb2026 SGV03026DW358MDC
HIB-36232X564476
zngkn
REFIB02-38091 1,450.00 41,459.32
05Feb2026 EVERYDAY+BONUSINTEREST
(NONGST)
REFZDD4-00034 7.04 41,466.36
24Feb2026 CREDITINTEREST
REFZDD4-00048 1.72 41,468.08
26Feb2026 SALA
REFYPB9-96414 11,360.00 52,828.08
CLOSINGBALANCE 52,828.08
"""
    # Simulate the "Details of Your Accounts" section start which is usually higher up
    full_text = "Details of Your Accounts\n" + text
    
    parser = HsbcSgBankParser(full_text)
    result = parser.parse()
    
    assert result.matched
    assert len(result.transactions) == 6
    
    # Verify values
    amounts = [t['amount'] for t in result.transactions]
    assert 2000.0 in amounts
    assert 500.0 in amounts
    assert 1450.0 in amounts
    assert 7.04 in amounts
    assert 1.72 in amounts
    assert 11360.0 in amounts
    
    # Verify sides
    sides = [t['cashflow_side'] for t in result.transactions]
    assert sides == ['expense', 'expense', 'expense', 'income', 'income', 'income']
