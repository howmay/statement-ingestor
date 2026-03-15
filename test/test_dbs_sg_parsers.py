import pytest
from src.parsing.banks.dbs import DbsSgCardParser, DbsSgBankParser
from src.parsing.banks.factory import get_bank_parser

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
        'subject': 'Your Monthly Statement',
        'filename': 'test_user_Statement_0000000000.pdf'
    }
    parser = get_bank_parser(text, source_info)
    assert isinstance(parser, DbsSgBankParser)
    
    result = parser.parse()
    assert result.matched
    assert len(result.transactions) == 2
    
    t1 = result.transactions[0]
    assert t1['date'] == f"{datetime.now().year}-03-01"
    assert t1['amount'] == 1000.00
    assert t1['cashflow_side'] == 'income'
    
    t2 = result.transactions[1]
    assert t2['amount'] == 200.00
    assert t2['cashflow_side'] == 'expense'

from datetime import datetime
