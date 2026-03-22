import pytest
from src.parsing.banks.hsbc_sg import HsbcSgCardParser, HsbcSgBankParser
from src.parsing.banks.factory import get_bank_parser

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
