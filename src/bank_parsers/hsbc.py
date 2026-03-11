import re
from typing import Dict, List

from .base import BaseBankParser, BankParseResult


class HsbcTwCardParser(BaseBankParser):
    SOURCE = 'HSBC'
    CURRENCY = 'TWD'

    # Example rows:
    # 12/27 12/30 20,990
    # 11/29 12/01 GOOGLE *Google One SGP SINGAPORE 11/29 TWD 8,250 TWD 8,250
    # 12/03 12/03 國外交易服務費 TWD 4
    LINE_PATTERN = re.compile(
        r'^(?P<tx_md>\d{1,2}/\d{1,2})\s+'
        r'(?P<post_md>\d{1,2}/\d{1,2})\s+'
        r'(?P<body>.+?)$'
    )

    CURRENCY_AMOUNT_PATTERN = re.compile(r'(?P<currency>TWD|USD|SGD|HKD)\s+(?P<amount>-?[0-9,]+(?:\.[0-9]+)?)')
    TRAILING_AMOUNT_PATTERN = re.compile(r'(?P<amount>-?[0-9,]+(?:\.[0-9]+)?)$')

    def parse(self) -> BankParseResult:
        txs: List[Dict] = []
        warnings: List[str] = []

        for raw_line in self.text.splitlines():
            line = raw_line.strip()
            if not line or line.startswith('--- Page'):
                continue

            # Skip obvious non-transaction lines
            if any(k in line for k in ['對帳單', '信用額度', '循環利率', 'EMAIL:', 'OTP', '2/2 O', '1/2 O']):
                continue

            m = self.LINE_PATTERN.match(line)
            if not m:
                continue

            tx_date = self._month_day_to_iso(m.group('tx_md'))
            body = m.group('body').strip()

            amount = None
            currency = self.CURRENCY
            desc = body

            # Prefer explicit currency amount segment
            curr_matches = list(self.CURRENCY_AMOUNT_PATTERN.finditer(body))
            if curr_matches:
                chosen = curr_matches[-1]
                currency = chosen.group('currency')
                amount = self._parse_amount(chosen.group('amount'))
                desc = body[:chosen.start()].strip()
                if not desc:
                    desc = body
            else:
                # Fallback: line ending amount
                am = self.TRAILING_AMOUNT_PATTERN.search(body)
                if not am:
                    continue
                amount = self._parse_amount(am.group('amount'))
                desc = body[:am.start()].strip() or body

            if amount is None:
                continue

            if not desc or re.fullmatch(r'-?[0-9,]+(?:\.[0-9]+)?', desc):
                desc = line
                warnings.append(f'Missing or numeric-only description: {line}')

            expense_type = _classify_expense_type(desc)
            confidence = 0.97 if desc and desc != line else 0.86

            txs.append(self._build_transaction(
                date=tx_date,
                amount=amount,
                expense_name=desc,
                expense_type=expense_type,
                source=self.SOURCE,
                currency=currency,
                confidence=confidence,
                parsing_method='bank_parser_hsbc',
                raw_line=line,
                parser_name='HsbcTwCardParser',
            ))

        return BankParseResult(
            matched=True,
            parser_name='HsbcTwCardParser',
            transactions=txs,
            warnings=warnings,
        )


def _classify_expense_type(desc: str) -> str:
    d = desc.lower()
    if any(k in d for k in ['uber', 'taxi', '交通', 'trip', '高鐵', '台鐵']):
        return 'Transportation'
    if any(k in d for k in ['spotify', 'netflix', 'youtube', 'movie', '電影', '遊戲']):
        return 'Entertainment'
    if any(k in d for k in ['amazon', 'pchome', 'momo', '寶島', 'shopping', '購物']):
        return 'Shopping'
    if any(k in d for k in ['國外交易服務費', '手續費', 'fee', 'payment', '繳款']):
        return 'Bills'
    return 'Other'
