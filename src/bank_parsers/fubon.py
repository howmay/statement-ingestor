import re
from typing import Dict, List

from .base import BaseBankParser, BankParseResult


class FubonBankParser(BaseBankParser):
    SOURCE = 'Fubon Bank'
    CURRENCY = 'TWD'

    # Example rows:
    # 2026/02/12 委代扣 1,000.00 台新銀行轉存款 2,580.00
    # 2026/02/24 信用卡轉 2,580.00 台北富邦信用卡款 0.00
    # 00766168****65 2026/02/01 承轉結餘 3,580.00
    LINE_PATTERN = re.compile(
        r'^(?:\S+\s+)?(?P<date>\d{4}/\d{1,2}/\d{1,2})\s+(?P<body>.+?)$'
    )

    AMOUNT_PATTERN = re.compile(r'(?P<amount>-?[0-9,]+(?:\.[0-9]+)?)')

    NON_EXPENSE_KEYWORDS = [
        '承轉結餘', '對帳單期間', '帳 戶 總 覽', '資產', '本月餘額', '貸款', '信用貸款',
        '分期型房貸', '循環型貸款', '定存', '信託', '透支', '組合式商品',
    ]

    def parse(self) -> BankParseResult:
        txs: List[Dict] = []

        for raw_line in self.text.splitlines():
            line = raw_line.strip()
            if not line or line.startswith('--- Page'):
                continue

            if any(k in line for k in self.NON_EXPENSE_KEYWORDS):
                continue

            m = self.LINE_PATTERN.match(line)
            if not m:
                continue

            date = _date_slash_to_iso(m.group('date'))
            body = m.group('body').strip()

            amount_match = self.AMOUNT_PATTERN.search(body)
            if not amount_match:
                continue

            amount = self._parse_amount(amount_match.group('amount'))
            if amount is None:
                continue

            desc = body[:amount_match.start()].strip() or body
            expense_type = _classify_expense_type(desc)

            txs.append(self._build_transaction(
                date=date,
                amount=amount,
                expense_name=desc,
                expense_type=expense_type,
                source=self.SOURCE,
                currency=self.CURRENCY,
                confidence=0.96,
                parsing_method='bank_parser_fubon',
                raw_line=line,
                parser_name='FubonBankParser',
            ))

        return BankParseResult(
            matched=True,
            parser_name='FubonBankParser',
            transactions=txs,
            warnings=[],
        )


def _date_slash_to_iso(date_str: str) -> str:
    m = re.match(r'^(\d{4})/(\d{1,2})/(\d{1,2})$', date_str)
    if not m:
        return date_str
    y, mo, d = m.groups()
    return f'{int(y):04d}-{int(mo):02d}-{int(d):02d}'


def _classify_expense_type(desc: str) -> str:
    d = desc.lower()
    if any(k in d for k in ['信用卡轉', '利息', '手續費']):
        return 'Bills'
    if any(k in d for k in ['uber', '交通', '計程車']):
        return 'Transportation'
    return 'Other'
