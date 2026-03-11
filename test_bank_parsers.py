#!/usr/bin/env python3
"""Quick deterministic parser tests."""

from src.bank_parsers.factory import parse_with_bank_factory


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


if __name__ == '__main__':
    test_hsbc_parse()
    test_esun_parse()
    test_fubon_parse()
    print('All parser tests passed ✅')
