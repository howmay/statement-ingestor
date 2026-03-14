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

    DETAIL_SECTION_START_KEYWORDS = [
        '交易明細', '每月交易明細', '本月交易明細'
    ]

    DETAIL_SECTION_END_KEYWORDS = [
        '帳 戶 總 覽', '資產總覽', '本月餘額', '本月結餘', '貸款', '定存', '信託'
    ]

    def parse(self) -> BankParseResult:
        txs: List[Dict] = []

        lines = [line.strip() for line in self.text.splitlines()]
        has_detail_heading = any(
            any(k in line for k in self.DETAIL_SECTION_START_KEYWORDS)
            for line in lines if line
        )
        in_detail_section = not has_detail_heading

        for raw_line in lines:
            line = raw_line.strip()
            if not line or line.startswith('--- Page'):
                continue

            if has_detail_heading:
                if any(k in line for k in self.DETAIL_SECTION_START_KEYWORDS):
                    in_detail_section = True
                    continue

                if in_detail_section and any(k in line for k in self.DETAIL_SECTION_END_KEYWORDS):
                    in_detail_section = False
                    continue

                if not in_detail_section:
                    continue

            if any(k in line for k in self.NON_EXPENSE_KEYWORDS):
                continue

            m = self.LINE_PATTERN.match(line)
            if not m:
                continue

            date = _date_slash_to_iso(m.group('date'))
            body = m.group('body').strip()

            # 富邦交易明細通常至少包含「交易金額 + 餘額」兩個數字欄位。
            amount_matches = list(self.AMOUNT_PATTERN.finditer(body))
            if len(amount_matches) < 2:
                continue

            amount = self._parse_amount(amount_matches[0].group('amount'))
            if amount is None:
                continue

            desc = body[:amount_matches[0].start()].strip() or body
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
            txs[-1]['cashflow_side'] = 'expense'

        return BankParseResult(
            matched=True,
            parser_name='FubonBankParser',
            transactions=txs,
            warnings=[],
        )


class FubonCreditCardParser(BaseBankParser):
    SOURCE = 'Fubon Credit Card'
    CURRENCY = 'TWD'

    # Example rows:
    # 12/27 12/30 特約商店 20,990
    # 12/03 12/03 國外交易服務費 TWD 4
    LINE_TWO_DATES = re.compile(
        r'^(?P<tx_md>\d{1,2}/\d{1,2})\s+(?P<post_md>\d{1,2}/\d{1,2})\s+(?P<body>.+?)$'
    )

    LINE_ONE_DATE = re.compile(
        r'^(?P<tx_md>\d{1,2}/\d{1,2})\s+(?P<body>.+?)$'
    )

    CURRENCY_AMOUNT_PATTERN = re.compile(
        r'(?P<currency>TWD|NTD|USD|SGD|HKD|JPY)\s*(?P<amount>-?[0-9,]+(?:\.[0-9]+)?)'
    )
    TRAILING_AMOUNT_PATTERN = re.compile(r'(?P<amount>-?[0-9,]+(?:\.[0-9]+)?)$')

    NON_TRANSACTION_KEYWORDS = [
        '信用卡', '電子帳單', '本期應繳', '最低應繳', '信用額度', '循環利率', '帳單',
        '到期日', '繳款', '回饋', '紅利', '客服', '電話', '頁', 'page',
    ]

    def parse(self) -> BankParseResult:
        txs: List[Dict] = []
        warnings: List[str] = []

        for raw_line in self.text.splitlines():
            line = raw_line.strip()
            if not line or line.startswith('--- Page'):
                continue

            lower_line = line.lower()
            if any(k.lower() in lower_line for k in self.NON_TRANSACTION_KEYWORDS):
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

            tx_date = self._month_day_to_iso(tx_md)

            amount = None
            currency = self.CURRENCY
            desc = body

            curr_matches = list(self.CURRENCY_AMOUNT_PATTERN.finditer(body))
            if curr_matches:
                chosen = curr_matches[-1]
                raw_currency = chosen.group('currency')
                currency = 'TWD' if raw_currency == 'NTD' else raw_currency
                amount = self._parse_amount(chosen.group('amount'))
                desc = body[:chosen.start()].strip() or body
            else:
                am = self.TRAILING_AMOUNT_PATTERN.search(body)
                if am:
                    amount = self._parse_amount(am.group('amount'))
                    desc = body[:am.start()].strip() or body

            if amount is None:
                continue

            if not desc or re.fullmatch(r'-?[0-9,]+(?:\.[0-9]+)?', desc):
                desc = line
                warnings.append(f'Missing or numeric-only description: {line}')

            txs.append(self._build_transaction(
                date=tx_date,
                amount=amount,
                expense_name=desc,
                expense_type=_classify_expense_type(desc),
                source=self.SOURCE,
                currency=currency,
                confidence=0.95 if desc != line else 0.85,
                parsing_method='bank_parser_fubon_card',
                raw_line=line,
                parser_name='FubonCreditCardParser',
            ))

        return BankParseResult(
            matched=True,
            parser_name='FubonCreditCardParser',
            transactions=txs,
            warnings=warnings,
        )


def _date_slash_to_iso(date_str: str) -> str:
    m = re.match(r'^(\d{4})/(\d{1,2})/(\d{1,2})$', date_str)
    if not m:
        return date_str
    y, mo, d = m.groups()
    return f'{int(y):04d}-{int(mo):02d}-{int(d):02d}'


def _classify_expense_type(desc: str) -> str:
    d = desc.lower()
    if any(k in d for k in ['信用卡轉', '利息', '手續費', 'fee']):
        return 'Bills'
    if any(k in d for k in ['uber', '交通', '計程車', '高鐵', '台鐵']):
        return 'Transportation'
    if any(k in d for k in ['spotify', 'netflix', 'youtube']):
        return 'Entertainment'
    if any(k in d for k in ['amazon', 'pchome', 'momo', '購物']):
        return 'Shopping'
    return 'Other'
