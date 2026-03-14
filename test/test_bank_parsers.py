#!/usr/bin/env python3
"""Quick deterministic parser tests."""

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from src.parsing.banks.factory import parse_with_bank_factory
from src.parsing.ocr.hsbc_ocr import _extract_rows_from_ocr_text, _clean_ocr_desc


def test_hsbc_parse():
    text = """
--- Page 2 ---
12/27 12/30 20,990
12/03 12/03 Spotify P3D0790DDD SWE Stockholm 12/03 TWD 298 TWD 298
12/03 12/03 國外交易服務費 TWD 4
"""
    source = {
        'sender_tag': 'hsbc',
        'sender': 'cards@estatements.hsbc.com.tw',
        'subject': '115年01月滙豐Live+現金回饋卡信用卡帳單',
    }

    result = parse_with_bank_factory(text, source)
    assert result.matched
    assert result.parser_name == 'HsbcTwCardParser'
    assert len(result.transactions) == 3

    target = [t for t in result.transactions if abs(float(t['amount']) - 20990.0) < 0.01][0]
    assert target['date'] == '2025-12-27'
    assert '12/27 12/30 20,990' in target['expense_name']


def test_hsbc_tw_statement_table_style():
    """HSBC TW statement style: date/date/amount without description text."""
    text = """
12/30 12/30 -1,061
12/27 12/30 20,990
01/01 01/06 4,262
01/05 01/08 575
"""
    source = {
        'sender_tag': 'hsbc',
        'sender': 'cards@estatements.hsbc.com.tw',
        'subject': '115年01月滙豐Live+現金回饋卡信用卡帳單',
    }

    result = parse_with_bank_factory(text, source)
    assert result.matched
    assert result.parser_name == 'HsbcTwCardParser'
    assert len(result.transactions) == 4

    dec_tx = [t for t in result.transactions if abs(float(t['amount']) - 20990.0) < 0.01][0]
    assert dec_tx['date'] == '2025-12-27'

    jan_tx = [t for t in result.transactions if abs(float(t['amount']) - 4262.0) < 0.01][0]
    assert jan_tx['date'] == '2026-01-01'


def test_hsbc_sg_credit_card_statement_style():
    """HSBC SG statement style: 27Dec 30Dec DESCRIPTION 18.98 / 15.00CR."""
    text = """
27Dec 30Dec NETFLIX.COM SINGAPORE 18.98
31Dec 02Jan AMAZON SG 15.00CR
01Jan 03Jan UBER *TRIP SINGAPORE SGD 12.30
"""
    source = {
        'sender_tag': 'hsbc',
        'sender': 'cardstatements@hsbc.com.sg',
        'subject': 'HSBC Singapore Credit Card eStatement 2026/01',
    }

    result = parse_with_bank_factory(text, source)
    assert result.matched
    assert result.parser_name == 'HsbcTwCardParser'
    assert len(result.transactions) == 3

    # Cross-year date inference from Jan statement: Dec -> previous year
    dec_tx = [t for t in result.transactions if abs(float(t['amount']) - 18.98) < 0.01][0]
    assert dec_tx['date'] == '2025-12-27'
    assert dec_tx['currency'] == 'SGD'

    # CR should be treated as negative
    credit_tx = [t for t in result.transactions if 'amazon' in t['expense_name'].lower()][0]
    assert abs(float(credit_tx['amount']) + 15.00) < 0.01


def test_hsbc_ocr_row_extraction_parser():
    text = """
03/03 03/03 CARREFOUR TAIPEI 2,880
02/11 02/24 NETFLIX.COM 100
02/14 02/24 REFUND 15.00CR
"""
    rows = _extract_rows_from_ocr_text(text)
    assert len(rows) == 3
    assert rows[0]['tx_md'] == '03/03'
    assert abs(rows[0]['amount'] - 2880.0) < 0.01
    assert abs(rows[2]['amount'] + 15.0) < 0.01


def test_hsbc_ocr_desc_cleanup():
    assert _clean_ocr_desc(' |「APE綠界-中華民國人TaipeiCi') == 'APE綠界-中華民國人TaipeiCi'
    assert _clean_ocr_desc('“|匯豐銀行自動扣款') == '匯豐銀行自動扣款'


def test_esun_parse():
    text = """
01/06 感謝您辦理本行自動轉帳繳款！ TWD -8,668
12/21 12/24 Ｐｉ－ＰＣＨＯＭＥ２４Ｈ購物－３Ｄ TWD 5,990
"""
    source = {
        'sender_tag': '_bank',
        'sender': 'estatement@esunbank.com',
        'subject': '玉山銀行2025年12月信用卡電子帳單',
    }

    result = parse_with_bank_factory(text, source)
    assert result.matched
    assert result.parser_name == 'EsunCardParser'
    assert len(result.transactions) == 2


def test_esun_statement_page_style():
    """Esun statement style with ROC header noise and page markers."""
    text = """
115/03/09 7.88%
1,000 元 至 115/03
115/02/21 10,000 / 100,000 元
1/3
02/06 感謝您辦理本行自動轉帳繳款！ TWD -6,185
02/21 02/21 ＵＢｅａｒ卡一般消費１％現金回饋 TWD -2
02/05 02/10 Ｐｉ－寶島眼鏡 TWD 2,503
02/10 02/13 Ｐｉ－寶島眼鏡 退貨 TWD -3,100
02/03 02/03 Spotify P3EFC3AD4D SWE Stockholm 02/03 TWD 298 TWD 298
02/03 02/03 國外交易服務費 TWD 4
2/3
"""
    source = {
        'sender_tag': '_bank',
        'sender': 'estatement@esunbank.com',
        'subject': '玉山銀行2026年2月信用卡電子帳單',
    }

    result = parse_with_bank_factory(text, source)
    assert result.matched
    assert result.parser_name == 'EsunCardParser'
    assert len(result.transactions) == 6

    refund = [t for t in result.transactions if '退貨' in t['expense_name']][0]
    assert abs(float(refund['amount']) + 3100.0) < 0.01


def test_fubon_parse():
    text = """
00766168****65 2026/02/01 承轉結餘 3,580.00
2026/02/12 委代扣 1,000.00 台新銀行轉存款 2,580.00
2026/02/24 信用卡轉 2,580.00 台北富邦信用卡款 0.00
"""
    source = {
        'sender_tag': 'fubon',
        'sender': 'service@bhu.taipeifubon.com.tw',
        'subject': '台北富邦銀行2026年2月 銀行對帳單',
    }

    result = parse_with_bank_factory(text, source)
    assert result.matched
    assert result.parser_name == 'FubonBankParser'
    assert len(result.transactions) == 2
    assert result.transactions[0]['cashflow_side'] == 'expense'
    assert result.transactions[1]['cashflow_side'] == 'expense'


def test_fubon_transaction_detail_section_only():
    text = """
帳 戶 總 覽
對帳單期間：2026/02/01~2026/02/28
交易明細
00766168****65 2026/02/01 承轉結餘 3,580.00
2026/02/12 委代扣 1,000.00 台新銀行轉存款 2,580.00
2026/02/24 信用卡轉 2,580.00 台北富邦信用卡款 0.00
本月餘額
"""
    source = {
        'sender_tag': 'fubon',
        'sender': 'service@bhu.taipeifubon.com.tw',
        'subject': '台北富邦銀行2026年2月 銀行對帳單',
    }

    result = parse_with_bank_factory(text, source)
    assert result.matched
    assert result.parser_name == 'FubonBankParser'
    assert len(result.transactions) == 2
    assert result.transactions[0]['expense_name'] == '委代扣'
    assert result.transactions[1]['expense_name'] == '信用卡轉'
    assert result.transactions[0]['cashflow_side'] == 'expense'
    assert result.transactions[1]['cashflow_side'] == 'expense'


def test_fubon_credit_card_statement():
    text = """
台北富邦銀行信用卡電子帳單
12/30 12/30 -1,061
12/27 12/30 特約商店消費 20,990
01/01 01/06 國外交易服務費 TWD 45
"""
    source = {
        'sender_tag': 'fubon',
        'sender': 'creditcard@taipeifubon.com.tw',
        'subject': '台北富邦銀行2026年1月 信用卡電子帳單',
    }

    result = parse_with_bank_factory(text, source)
    assert result.matched
    assert result.parser_name == 'FubonCreditCardParser'
    assert len(result.transactions) == 3

    target = [t for t in result.transactions if abs(float(t['amount']) - 20990.0) < 0.01][0]
    assert target['date'] == '2025-12-27'


if __name__ == '__main__':
    test_hsbc_parse()
    test_hsbc_tw_statement_table_style()
    test_hsbc_sg_credit_card_statement_style()
    test_hsbc_ocr_row_extraction_parser()
    test_hsbc_ocr_desc_cleanup()
    test_esun_parse()
    test_esun_statement_page_style()
    test_fubon_parse()
    test_fubon_transaction_detail_section_only()
    test_fubon_credit_card_statement()
    print('All parser tests passed ✅')
