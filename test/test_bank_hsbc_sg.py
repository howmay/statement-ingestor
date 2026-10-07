from src.parsing.banks.hsbc_sg import HsbcSgBankParser, HsbcSgCardParser
from src.parsing.banks.factory import get_bank_parser


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


def test_hsbc_sg_card_statement_text():
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


def test_hsbc_sg_card_parser():
    text = "30Dec 27Dec NETFLIX.COM 18.98\n31Dec 28Dec STARBUCKS 15.00CR"
    source_info = {
        'subject': 'HSBC Singapore Credit Card eStatement 2026/01',
        'sender': 'cardstatements@hsbc.com.sg',
        'filename': 'HSBC_SG_信用卡帳單_0000000000.pdf'
    }
    parser = get_bank_parser(text, source_info)
    assert isinstance(parser, HsbcSgCardParser)
    
    result = parser.parse()
    assert result.matched
    assert len(result.transactions) == 2
    
    t1 = result.transactions[0]
    assert t1['date'] == '2025-12-27'  # Dec in Jan statement -> prev year
    assert t1['amount'] == 18.98
    assert 'NETFLIX.COM' in t1['expense_name']
    
    t2 = result.transactions[1]
    assert t2['date'] == '2025-12-28'
    assert t2['amount'] == -15.00  # CR means payment/refund
    assert 'STARBUCKS' in t2['expense_name']

def test_hsbc_sg_bank_parser():
    text = "EVERYDAY GLOBAL ACC 142-05XXXX-221\n27 Feb INTEREST 0.15 1,234.56\n28 Feb GIRO IN 1000.00 2,234.56"
    source_info = {
        'subject': 'HSBC Personal Banking Statement',
        'sender': 'hsbc@hsbc.com.sg',
        'filename': 'HSBC_SG_28FEB2026_0000000000.pdf'
    }
    parser = get_bank_parser(text, source_info)
    assert isinstance(parser, HsbcSgBankParser)
    
    result = parser.parse()
    assert result.matched
    assert len(result.transactions) == 2
    
    t1 = result.transactions[0]
    assert t1['date'] == '2026-02-27'
    assert t1['amount'] == 0.15
    assert t1['cashflow_side'] == 'income'
    
    t2 = result.transactions[1]
    assert t2['date'] == '2026-02-28'
    assert t2['amount'] == 1000.00
    assert t2['cashflow_side'] == 'income'


def test_hsbc_sg_bank_parser_marks_supported_statement_as_matched_even_when_no_transactions():
    text = "HSBC Bank (Singapore) Limited\nPersonal Banking Statement\nDate Transaction Details Deposits Withdrawals Balance"
    source_info = {
        'subject': 'HSBC Personal Banking Statement',
        'sender': 'service@mail.hsbc.com.sg',
        'filename': '20260322.pdf',
        'sender_tag': 'hsbc_sg_mail',
    }

    parser = get_bank_parser(text, source_info)
    assert isinstance(parser, HsbcSgBankParser)

    result = parser.parse()
    assert result.matched is True
    assert result.transactions == []
