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
    TRAILING_AMOUNT = re.compile(r'(?P<amount>-?[0-9,]+(?:\.[0-9]+)?)$')

    def parse(self) -> BankParseResult:
        # Check for explicit "no transaction" message
        if any(k in self.text for k in ['本期無消費資料', '本期無交易資料']):
            return BankParseResult(
                matched=True,
                parser_name='EsunCardParser',
                transactions=[],
                warnings=['No transactions found in this period (explicitly stated).']
            )

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

            currency = self.CURRENCY
            amount = None
            desc = body

            cm = self.CURRENCY_AMOUNT.search(body)
            if cm:
                currency = cm.group('currency')
                amount = self._parse_amount(cm.group('amount'))
                desc = body[:cm.start()].strip() or body
            else:
                am = self.TRAILING_AMOUNT.search(body)
                if am:
                    amount = self._parse_amount(am.group('amount'))
                    desc = body[:am.start()].strip() or body

            if amount is None:
                continue

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


class EsunBankParser(BaseBankParser):
    """Parser for E.SUN Bank account statements."""
    SOURCE = 'Esun Bank Account'
    CURRENCY = 'TWD'

    # Example: 115/02/27 轉帳入 1,000 5,000
    # Date is usually ROC year YYY/MM/DD
    LINE_PATTERN = re.compile(
        r'^(?P<date>\d{3}/\d{2}/\d{2})\s+(?P<summary>\S+)\s+(?P<body>.+)$'
    )

    def parse(self) -> BankParseResult:
        # Handle "no transaction" scenario if any
        if '本期無交易資料' in self.text or '本期無消費資料' in self.text:
            return BankParseResult(
                matched=True,
                parser_name='EsunBankParser',
                transactions=[],
                warnings=['No transactions found in this period (explicitly stated).']
            )

        txs: List[Dict] = []
        for line in self.text.splitlines():
            line = line.strip()
            if not line: continue
            
            m = self.LINE_PATTERN.match(line)
            if not m: continue
            
            # ROC date to ISO
            roc_year, month, day = map(int, m.group('date').split('/'))
            date_iso = f"{roc_year + 1911}-{month:02d}-{day:02d}"
            
            body = m.group('body').strip()
            amounts = re.findall(r'[0-9,]+(?:\.[0-9]+)?', body)
            if len(amounts) < 2: continue
            
            amount_val = self._parse_amount(amounts[-2])
            summary = m.group('summary')
            
            # Heuristic for side
            side = 'expense'
            if any(k in summary for k in ['入', '息', '存']):
                side = 'income'
            elif any(k in summary for k in ['出', '支', '費', '扣']):
                side = 'expense'

            txs.append(self._build_transaction(
                date=date_iso,
                amount=amount_val,
                expense_name=f"{summary} {body[:body.find(amounts[-2])].strip()}",
                expense_type='Other',
                source=self.SOURCE,
                currency=self.CURRENCY,
                confidence=0.92,
                parsing_method='bank_parser_esun_bank',
                raw_line=line,
                parser_name='EsunBankParser'
            ))
            txs[-1]['cashflow_side'] = side
            
        return BankParseResult(
            matched=len(txs) > 0 or '玉山銀行' in self.text,
            parser_name='EsunBankParser',
            transactions=txs
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
