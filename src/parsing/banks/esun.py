import re
from typing import Dict, List

from .base import BaseBankParser, BankParseResult


class EsunCardParser(BaseBankParser):
    SOURCE = 'Esun Bank'
    CURRENCY = 'TWD'

    # Example rows:
    # 02/05 02/10 Ｐｉ－寶島眼鏡 TWD 2,503
    # 02/06 感謝您辦理本行自動轉帳繳款！ TWD -6,185
    LINE_TWO_DATES = re.compile(
        r'^(?P<tx_md>\d{1,2}/\d{1,2})\s+(?P<post_md>\d{1,2}/\d{1,2})\s+(?P<body>.+?)$'
    )
    LINE_ONE_DATE = re.compile(
        r'^(?P<tx_md>\d{1,2}/\d{1,2})\s+(?P<body>.+?)$'
    )
    CURRENCY_AMOUNT = re.compile(r'(?P<currency>TWD|USD|SGD|HKD)\s+(?P<amount>-?[0-9,]+(?:\.[0-9]+)?)')

    def parse(self) -> BankParseResult:
        txs: List[Dict] = []

        for raw_line in self.text.splitlines():
            line = raw_line.strip()
            if not line or line.startswith('--- Page'):
                continue

            # Skip non-transaction rows with ROC yyyy/mm/dd or ratio-like patterns
            if re.match(r'^\d{3}/\d{1,2}/\d{1,2}', line):
                continue
            if re.search(r'\d+\s*/\s*\d+\s*元', line):
                continue
            if any(k in line for k in ['紅利點數', '統計區間', '到期', '1/3', '2/3', '3/3']):
                continue

            tx_md = None
            body = None

            m2 = self.LINE_TWO_DATES.match(line)
            if m2:
                tx_md = m2.group('tx_md')
                body = m2.group('body').strip()
            else:
                m1 = self.LINE_ONE_DATE.match(line)
                if m1:
                    tx_md = m1.group('tx_md')
                    body = m1.group('body').strip()

            if not tx_md or not body:
                continue

            cm = self.CURRENCY_AMOUNT.search(body)
            if not cm:
                continue

            currency = cm.group('currency')
            amount = self._parse_amount(cm.group('amount'))
            if amount is None:
                continue

            desc = body[:cm.start()].strip() or body
            tx_date = self._month_day_to_iso(tx_md)
            expense_type = _classify_expense_type(desc)

            txs.append(self._build_transaction(
                date=tx_date,
                amount=amount,
                expense_name=desc,
                expense_type=expense_type,
                source=self.SOURCE,
                currency=currency,
                confidence=0.97,
                parsing_method='bank_parser_esun',
                raw_line=line,
                parser_name='EsunCardParser',
            ))

        return BankParseResult(
            matched=True,
            parser_name='EsunCardParser',
            transactions=txs,
            warnings=[],
        )


def _classify_expense_type(desc: str) -> str:
    d = desc.lower()
    if any(k in d for k in ['自動轉帳繳款', '服務費', '費']):
        return 'Bills'
    if any(k in d for k in ['spotify', 'google', 'uber']):
        return 'Entertainment'
    if any(k in d for k in ['pchome', '寶島', '購物']):
        return 'Shopping'
    return 'Other'
