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
    """HSBC SG statement style: 30Dec 27Dec DESCRIPTION 18.98 / 15.00CR."""
    text = """
30Dec 27Dec NETFLIX.COM SINGAPORE 18.98
02Jan 31Dec AMAZON SG 15.00CR
03Jan 01Jan UBER *TRIP SINGAPORE SGD 12.30
"""
    source = {
        'sender_tag': 'hsbc',
        'sender': 'cardstatements@hsbc.com.sg',
        'subject': 'HSBC Singapore Credit Card eStatement 2026/01',
    }

    result = parse_with_bank_factory(text, source)
    assert result.matched
    assert result.parser_name == 'HsbcSgCardParser'
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
00000000****65 2026/02/01 承轉結餘 3,580.00
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
00000000****65 2026/02/01 承轉結餘 3,580.00
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


def test_fubon_statement_infers_income_and_expense_from_running_balance():
    text = """
帳號 日期 摘要 支出 收入 餘額
00000000****65 2026/02/01 承轉結餘 3,580.00
2026/02/12 委代扣 1,000.00 台新銀行轉存款 2,580.00
2026/02/24 信用卡轉 2,580.00 台北富邦信用卡款 0.00
2026/02/24 ＣＤ轉收 ********00000000 10,000.00 10,000.00
2026/02/25 信用卡轉 3,836.00 台北富邦信用卡款 6,164.00
"""
    source = {
        'sender_tag': 'fubon',
        'sender': 'service@bhu.taipeifubon.com.tw',
        'subject': '台北富邦銀行2026年2月 銀行對帳單',
    }

    result = parse_with_bank_factory(text, source)

    assert result.matched
    assert result.parser_name == 'FubonBankParser'
    assert len(result.transactions) == 4

    transfer_in = next(tx for tx in result.transactions if tx['expense_name'] == 'ＣＤ轉收 ********00000000')
    assert float(transfer_in['amount']) == 10000.0
    assert transfer_in['cashflow_side'] == 'income'

    card_payment = next(
        tx for tx in result.transactions
        if tx['expense_name'] == '信用卡轉' and float(tx['amount']) == 2580.0
    )
    assert card_payment['cashflow_side'] == 'expense'


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


def test_taishin_credit_card_statement():
    text = """
台新銀行信用卡帳單(補印)
115年02月
消費日 入帳起息日 消費明細(含消費地) 新臺幣金額 外幣折算日 消費地 幣別 外幣金額
1150202 1150202 台新銀行帳戶自動轉帳扣繳台新信用卡款 -11,940
Richart卡(原@GoGo虛擬御璽) (卡號末四碼:2800)
1150122 1150123 APPLE.COM/BILL080009 30 IE
1150130 1150203 APPLE.COM/BILL080009 80 IE
1150130 1150203 國外交易服務費－80.00 1
1150205 1150210 財團法人忠義社會福利事業基TAIPEI 600 TW
-------------------------結束-------------------------
"""
    source = {
        'sender_tag': 'taishin',
        'sender': 'service@taishinbank.com.tw',
        'subject': '台新銀行115年02月信用卡帳單',
        'filename': '台新銀行_von9JKE=.pdf',
    }

    result = parse_with_bank_factory(text, source)

    assert result.matched
    assert result.parser_name == 'TaishinCreditCardParser'
    assert len(result.transactions) == 5

    autopay = next(
        tx for tx in result.transactions
        if '自動轉帳扣繳' in tx['expense_name']
    )
    assert autopay['date'] == '2026-02-02'
    assert float(autopay['amount']) == -11940.0

    apple = next(
        tx for tx in result.transactions
        if tx['expense_name'] == 'APPLE.COM/BILL080009' and float(tx['amount']) == 30.0
    )
    assert apple['date'] == '2026-01-22'

    fx_fee = next(
        tx for tx in result.transactions
        if '國外交易服務費' in tx['expense_name']
    )
    assert float(fx_fee['amount']) == -80.0
    assert fx_fee['expense_type'] == 'Bills'


def test_taishin_bank_statement():
    text = """
台 新 銀 行 綜 合 對 帳 單 2026年01月
您在本行的交易往來
新臺幣帳戶的往來明細
帳號 日期 摘要 支票號碼 支出金額 存入金額 帳戶餘額 備註
288810****5696 2026/01/02 CD轉出 $20,000 $120,375
數位跨行808-00000000**
**2057
288810****5696 2026/01/05 CD提款 $2,000 $118,375 ATM/跨行交易
288810****5696 2026/01/05 媒體轉帳 $1,714 $116,661 台新卡費王小明
288810****5696 2026/01/12 媒體轉入 $1,000 $117,661 其他 ACH 轉入
288810****5696 2026/01/26 轉帳支取 $1,652 $116,009 一卡通電支儲值
288810****5696 2026/01/30 存款息 $73 $116,082
外幣帳戶的往來明細
帳號 日期 摘要 幣別 支出金額 存入金額 帳戶餘額 備註
88875****337 2026/01/01 INTEREST JPY $0 $1 $95,340
88875****337 2026/01/01 INTEREST USD $0 $0 $0.08
各產品訊息區
"""
    source = {
        'sender_tag': 'taishin',
        'sender': 'service@taishinbank.com.tw',
        'subject': '台新銀行2026年01月 綜合對帳單',
        'filename': '台新銀行_NhuIh4k=.pdf',
    }

    result = parse_with_bank_factory(text, source)

    assert result.matched
    assert result.parser_name == 'TaishinBankParser'
    assert len(result.transactions) == 8

    transfer_out = next(
        tx for tx in result.transactions
        if tx['date'] == '2026-01-02'
    )
    assert float(transfer_out['amount']) == 20000.0
    assert transfer_out['cashflow_side'] == 'expense'
    assert '數位跨行808-00000000** **2057' in transfer_out['expense_name']

    transfer_in = next(
        tx for tx in result.transactions
        if tx['date'] == '2026-01-12'
    )
    assert float(transfer_in['amount']) == 1000.0
    assert transfer_in['cashflow_side'] == 'income'

    interest_twd = next(
        tx for tx in result.transactions
        if tx['date'] == '2026-01-30'
    )
    assert float(interest_twd['amount']) == 73.0
    assert interest_twd['cashflow_side'] == 'income'
    assert interest_twd['currency'] == 'TWD'

    interest_jpy = next(
        tx for tx in result.transactions
        if tx['currency'] == 'JPY'
    )
    assert float(interest_jpy['amount']) == 1.0
    assert interest_jpy['cashflow_side'] == 'income'


def test_hsbc_taiwan_bank_statement():
    text = """
交易明細
 新臺幣活期存款 716-16XXXX-388
日期 交易明細 存入 支出 結餘
新臺幣
09/01/2026 承前結餘 2,007,659
23/01/2026 23JAN26 HIBA881 09:52:42
TW 6166 FISC 0000000000
HIB -RANDOM_STRING_123
TO 012 0000000000000000
REF A881-00915 2,500 2,005,159
28/01/2026 /CCP/450307XXXXXX3278
/CCP/450307XXXXXX3278
REF B502-03622 59,258 1,945,901
從 716-168331-821 SGD
/CBC/692/S/A_692250A
轉帳 SGD 20275.58
匯率為 SGD/TWD 24.6601526
REF YWC3-10374 499,999 2,445,900
30/01/2026 從 716-168331-821 SGD
/CBC/692/S/A_692250A
轉帳 SGD 20365.44
匯率為 SGD/TWD 24.5513425
REF YWC1-12887 499,999 2,945,899
存入利息
REF ZDD4-00070 1,097 2,946,996
02/02/2026 從 716-168331-821 SGD
/CBC/692/S/A_692250A
轉帳 SGD 20187.21
匯率為 SGD/TWD 24.7681121
REF YWC5-13719 499,999 3,446,995
06/02/2026 06FEB26 HIBA881 10:06:55
TW 99DB FISC 0000000000
HIB -RANDOM_STRING_456
TO 012 0000000000000000
REF A881-01141 2,500 3,444,495
結餘 3,444,495
 外幣綜合存款 716-16XXXX-821
日期 交易明細 存入 支出 結餘
新加坡幣
09/01/2026 承前結餘 0.00
28/01/2026 GLOBAL TRANSFER
GPA854M314
REF EB06-02424 100,000.00 100,000.00
至 716-168331-388 TWD
/CBC/692/S/A_692250A
HIB - 000000000
REF YWC3-10374 20,275.58 79,724.42
30/01/2026 至 716-168331-388 TWD
/CBC/692/S/A_692250A
HIB - 000000000
REF YWC1-12887 20,365.44 59,358.98
02/02/2026 至 716-168331-388 TWD
/CBC/692/S/A_692250A
HIB - 000000000
REF YWC5-13719 20,187.21 39,171.77
結餘 39,171.77
資料結束
"""
    source = {
        'sender_tag': 'hsbc_tw',
        'sender': 'service@hsbc.com.tw',
        'subject': '匯豐(台灣)商業銀行運籌理財對帳單',
        'filename': 'HSBC_Taiwan_LEFZ2Tc=.pdf',
    }

    result = parse_with_bank_factory(text, source)

    assert result.matched
    assert result.parser_name == 'HsbcTwBankParser'
    assert len(result.transactions) == 8

    transfer_out = next(
        tx for tx in result.transactions
        if tx['date'] == '2026-01-23'
    )
    assert float(transfer_out['amount']) == 2500.0
    assert transfer_out['cashflow_side'] == 'expense'
    assert 'FISC 0000000000' in transfer_out['expense_name']

    interest = next(
        tx for tx in result.transactions
        if tx['date'] == '2026-01-30' and float(tx['amount']) == 1097.0
    )
    assert interest['cashflow_side'] == 'income'
    assert interest['expense_type'] == 'Bills'

    fx_out = next(
        tx for tx in result.transactions
        if tx['date'] == '2026-01-28' and tx['currency'] == 'SGD' and float(tx['amount']) == 20275.58
    )
    assert fx_out['cashflow_side'] == 'expense'


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
    test_taishin_credit_card_statement()
    test_taishin_bank_statement()
    test_hsbc_taiwan_bank_statement()
    print('All parser tests passed ✅')
