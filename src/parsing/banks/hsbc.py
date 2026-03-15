import logging
import re
from typing import Dict, List, Optional

from .base import BaseBankParser, BankParseResult
from src.parsing.ocr.hsbc_ocr import enrich_hsbc_transactions_with_ocr

logger = logging.getLogger(__name__)


class HsbcTwCardParser(BaseBankParser):
    SOURCE = 'HSBC'
    CURRENCY = 'TWD'

    # TW style: 12/27 12/30 20,990
    LINE_MMDD_PATTERN = re.compile(
        r'^(?P<tx_md>\d{1,2}/\d{1,2})\s+'
        r'(?P<post_md>\d{1,2}/\d{1,2})\s+'
        r'(?P<body>.+?)$'
    )

    CURRENCY_BEFORE_AMOUNT = re.compile(
        r'(?P<currency>TWD|NTD|USD|HKD|JPY)\s*(?P<amount>-?[0-9,]+(?:\.[0-9]+)?)(?P<suffix>CR|DR)?',
        re.IGNORECASE,
    )
    AMOUNT_BEFORE_CURRENCY = re.compile(
        r'(?P<amount>-?[0-9,]+(?:\.[0-9]+)?)(?P<suffix>CR|DR)?\s*(?P<currency>TWD|NTD|USD|HKD|JPY)',
        re.IGNORECASE,
    )
    TRAILING_AMOUNT_PATTERN = re.compile(
        r'(?P<amount>-?[0-9,]+(?:\.[0-9]+)?)(?P<suffix>CR|DR)?$',
        re.IGNORECASE,
    )

    NON_TRANSACTION_KEYWORDS = [
        '對帳單', '信用額度', '循環利率', 'email:', 'otp',
        'minimum payment', 'payment due', 'statement date',
        'credit limit', 'contact us', 'customer service',
    ]

    def parse(self) -> BankParseResult:
        txs: List[Dict] = []
        warnings: List[str] = []

        for raw_line in self.text.splitlines():
            line = raw_line.strip()
            if not line or line.startswith('--- Page'):
                continue

            if any(k in line.lower() for k in self.NON_TRANSACTION_KEYWORDS):
                continue

            tx_date: Optional[str] = None
            body: Optional[str] = None

            m_mmdd = self.LINE_MMDD_PATTERN.match(line)
            if m_mmdd:
                tx_date = self._month_day_to_iso(m_mmdd.group('tx_md'))
                body = m_mmdd.group('body').strip()

            if not tx_date or not body:
                continue

            amount = None
            currency = self.CURRENCY
            desc = body

            # Prefer explicit currency+amount in line
            currency_matches = list(self.CURRENCY_BEFORE_AMOUNT.finditer(body))
            amount_currency_matches = list(self.AMOUNT_BEFORE_CURRENCY.finditer(body))

            chosen_match = None
            chosen_mode = None
            if currency_matches:
                chosen_match = currency_matches[-1]
                chosen_mode = 'currency_before'
            if amount_currency_matches:
                # If both exist, prefer the one later in line (usually final amount column)
                if (chosen_match is None) or (amount_currency_matches[-1].start() > chosen_match.start()):
                    chosen_match = amount_currency_matches[-1]
                    chosen_mode = 'amount_before'

            if chosen_match is not None:
                if chosen_mode == 'currency_before':
                    raw_currency = chosen_match.group('currency').upper()
                    raw_amount = chosen_match.group('amount')
                    suffix = (chosen_match.group('suffix') or '').upper()
                else:
                    raw_currency = chosen_match.group('currency').upper()
                    raw_amount = chosen_match.group('amount')
                    suffix = (chosen_match.group('suffix') or '').upper()

                currency = 'TWD' if raw_currency == 'NTD' else raw_currency
                amount = self._parse_amount(raw_amount)
                if amount is not None:
                    amount = _apply_dr_cr_sign(amount, suffix)

                desc = body[:chosen_match.start()].strip() or body
            else:
                # Fallback: line-ending amount (currency inferred)
                am = self.TRAILING_AMOUNT_PATTERN.search(body)
                if not am:
                    continue

                amount = self._parse_amount(am.group('amount'))
                if amount is None:
                    continue

                suffix = (am.group('suffix') or '').upper()
                amount = _apply_dr_cr_sign(amount, suffix)
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

        # OCR fallback for rows where merchant description is missing in PDF text layer
        try:
            enriched = enrich_hsbc_transactions_with_ocr(txs, self.source_info)
            if enriched > 0:
                warnings.append(f'ocr_enriched_descriptions={enriched}')
        except Exception as e:
            logger.warning(f'HSBC OCR enrichment error: {e}')

        return BankParseResult(
            matched=True,
            parser_name='HsbcTwCardParser',
            transactions=txs,
            warnings=warnings,
        )


class HsbcTwBankParser(BaseBankParser):
    SOURCE = 'HSBC Taiwan Bank'
    CURRENCY = 'TWD'

    TWD_HEADER = '新臺幣活期存款'
    FX_HEADER = '外幣綜合存款'
    COLUMN_HEADER = '日期 交易明細 存入 支出 結餘'
    STOP_KEYWORDS = ['交易總額', '資料結束']
    DATE_LINE = re.compile(r'^(?P<date>\d{2}/\d{2}/\d{4})\s+(?P<body>.+)$')
    AMOUNT_TAIL = re.compile(
        r'(?P<body>.+?)\s+(?P<deposit>[0-9,]+(?:\.[0-9]+)?)\s+(?P<balance>[0-9,]+(?:\.[0-9]+)?)$'
    )
    DEPOSIT_WITH_WITHDRAWAL_TAIL = re.compile(
        r'(?P<body>.+?)\s+(?P<deposit>[0-9,]+(?:\.[0-9]+)?)\s+(?P<withdrawal>[0-9,]+(?:\.[0-9]+)?)\s+(?P<balance>[0-9,]+(?:\.[0-9]+)?)$'
    )

    def parse(self) -> BankParseResult:
        txs: List[Dict] = []
        section: Optional[str] = None
        currency = self.CURRENCY
        pending: Optional[Dict] = None

        for raw_line in self.text.splitlines():
            line = raw_line.strip()
            if not line or line.startswith('--- Page'):
                continue

            if self.TWD_HEADER in line:
                if pending:
                    txs.append(self._finalize_bank_tx(pending))
                    pending = None
                section = 'twd'
                currency = 'TWD'
                continue

            if self.FX_HEADER in line:
                if pending:
                    txs.append(self._finalize_bank_tx(pending))
                    pending = None
                section = 'fx'
                continue

            if line == self.COLUMN_HEADER:
                continue

            if line.startswith('結餘 '):
                if pending:
                    txs.append(self._finalize_bank_tx(pending))
                    pending = None
                continue

            if section == 'fx' and line in {'新加坡幣', '日圓', '美金'}:
                if pending:
                    txs.append(self._finalize_bank_tx(pending))
                    pending = None
                currency = {
                    '新加坡幣': 'SGD',
                    '日圓': 'JPY',
                    '美金': 'USD',
                }[line]
                continue

            if any(keyword in line for keyword in self.STOP_KEYWORDS):
                if pending:
                    txs.append(self._finalize_bank_tx(pending))
                    pending = None
                if '資料結束' in line:
                    break
                continue

            if line in {'新臺幣', '.F'}:
                continue
            if section not in {'twd', 'fx'}:
                continue

            parsed = self._parse_date_line(line, currency)
            if parsed:
                if pending:
                    txs.append(self._finalize_bank_tx(pending))
                pending = parsed
                continue

            if pending:
                pending['detail_lines'].append(line)

        if pending:
            txs.append(self._finalize_bank_tx(pending))

        return BankParseResult(
            matched=True,
            parser_name='HsbcTwBankParser',
            transactions=txs,
            warnings=[],
        )

    def _parse_date_line(self, line: str, currency: str) -> Optional[Dict]:
        match = self.DATE_LINE.match(line)
        if not match:
            return None

        date = _tw_bank_date_to_iso(match.group('date'))
        body = match.group('body').strip()

        if '承前結餘' in body:
            return None

        return {
            'date': date,
            'body': body,
            'currency': currency,
            'detail_lines': [],
        }

    def _finalize_bank_tx(self, pending: Dict) -> Dict:
        full_body = ' '.join([pending['body'], *pending['detail_lines']]).strip()
        parsed = self._parse_bank_amounts(full_body)

        amount = parsed['amount']
        cashflow_side = parsed['cashflow_side']
        desc = parsed['description']

        tx = self._build_transaction(
            date=pending['date'],
            amount=amount,
            expense_name=desc,
            expense_type=_classify_bank_expense_type(desc),
            source=self.SOURCE,
            currency=pending['currency'],
            confidence=0.95,
            parsing_method='bank_parser_hsbc_tw_bank',
            raw_line=full_body,
            parser_name='HsbcTwBankParser',
        )
        tx['cashflow_side'] = cashflow_side
        return tx

    def _parse_bank_amounts(self, full_body: str) -> Dict[str, object]:
        match = self.DEPOSIT_WITH_WITHDRAWAL_TAIL.search(full_body)
        if match:
            deposit = self._parse_amount(match.group('deposit')) or 0.0
            withdrawal = self._parse_amount(match.group('withdrawal')) or 0.0
            desc = match.group('body').strip()
            if deposit > 0 and withdrawal > 0:
                # HSBC TW text layer can append both sides when FX transfer metadata wraps.
                if _looks_like_income(desc):
                    return {'amount': deposit, 'cashflow_side': 'income', 'description': desc}
                if _looks_like_expense(desc):
                    return {'amount': withdrawal, 'cashflow_side': 'expense', 'description': desc}
                return {'amount': withdrawal, 'cashflow_side': 'expense', 'description': desc}

        match = self.AMOUNT_TAIL.search(full_body)
        if not match:
            return {'amount': 0.0, 'cashflow_side': 'expense', 'description': full_body}

        first = self._parse_amount(match.group('deposit')) or 0.0
        second = self._parse_amount(match.group('balance')) or 0.0
        desc = match.group('body').strip()

        if _looks_like_income(desc):
            return {'amount': first, 'cashflow_side': 'income', 'description': desc}

        if _looks_like_expense(desc):
            return {'amount': first, 'cashflow_side': 'expense', 'description': desc}

        if second >= first:
            return {'amount': first, 'cashflow_side': 'expense', 'description': desc}
        return {'amount': first, 'cashflow_side': 'income', 'description': desc}


def _apply_dr_cr_sign(amount: float, suffix: str) -> float:
    # Credit notation: CR -> negative (refund/inflow)
    if suffix == 'CR':
        return -abs(amount)
    if suffix == 'DR':
        return abs(amount)
    return amount


def _classify_expense_type(desc: str) -> str:
    d = desc.lower()
    if any(k in d for k in ['uber', 'taxi', '交通', 'trip', '高鐵', '台鐵', 'grab']):
        return 'Transportation'
    if any(k in d for k in ['spotify', 'netflix', 'youtube', 'movie', '電影', '遊戲']):
        return 'Entertainment'
    if any(k in d for k in ['amazon', 'pchome', 'momo', '寶島', 'shopping', '購物']):
        return 'Shopping'
    if any(k in d for k in ['國外交易服務費', '手續費', 'fee', 'payment', '繳款']):
        return 'Bills'
    return 'Other'


def _tw_bank_date_to_iso(date_str: str) -> Optional[str]:
    m = re.match(r'^(?P<day>\d{2})/(?P<month>\d{2})/(?P<year>\d{4})$', date_str)
    if not m:
        return None
    return f"{m.group('year')}-{m.group('month')}-{m.group('day')}"


def _looks_like_income(desc: str) -> bool:
    lowered = desc.lower()
    if '至 ' in desc or 'to ' in lowered:
        return False
    return any(k in lowered for k in ['存入利息', '從 ', 'global transfer'])


def _looks_like_expense(desc: str) -> bool:
    lowered = desc.lower()
    return any(k in lowered for k in ['to ', '至 ', 'fisc', '/ccp/'])


def _classify_bank_expense_type(desc: str) -> str:
    lowered = desc.lower()
    if any(k in lowered for k in ['利息', 'interest', '/ccp/']):
        return 'Bills'
    if any(k in lowered for k in ['轉帳', 'global transfer', 'fisc', 'hiba881']):
        return 'Transfer'
    return 'Other'
