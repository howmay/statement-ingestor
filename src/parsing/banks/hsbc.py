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

    # SG style: 27Dec 30Dec NETFLIX.COM 18.98
    # Also supports: 27 Dec 30 Dec NETFLIX.COM 18.98
    LINE_MON_PATTERN = re.compile(
        r'^(?P<tx_day>\d{1,2})\s*(?P<tx_mon>[A-Za-z]{3})\s+'
        r'(?P<post_day>\d{1,2})\s*(?P<post_mon>[A-Za-z]{3})\s+'
        r'(?P<body>.+?)$',
        re.IGNORECASE,
    )

    CURRENCY_BEFORE_AMOUNT = re.compile(
        r'(?P<currency>TWD|NTD|USD|SGD|HKD|JPY)\s*(?P<amount>-?[0-9,]+(?:\.[0-9]+)?)(?P<suffix>CR|DR)?',
        re.IGNORECASE,
    )
    AMOUNT_BEFORE_CURRENCY = re.compile(
        r'(?P<amount>-?[0-9,]+(?:\.[0-9]+)?)(?P<suffix>CR|DR)?\s*(?P<currency>TWD|NTD|USD|SGD|HKD|JPY)',
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

    MONTH_MAP = {
        'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4,
        'may': 5, 'jun': 6, 'jul': 7, 'aug': 8,
        'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
    }

    def parse(self) -> BankParseResult:
        txs: List[Dict] = []
        warnings: List[str] = []

        default_currency = self._infer_default_currency()

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
            else:
                m_mon = self.LINE_MON_PATTERN.match(line)
                if m_mon:
                    tx_date = self._month_name_day_to_iso(m_mon.group('tx_day'), m_mon.group('tx_mon'))
                    body = m_mon.group('body').strip()

            if not tx_date or not body:
                continue

            amount = None
            currency = default_currency
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

    def _month_name_day_to_iso(self, day_text: str, mon_text: str) -> Optional[str]:
        month = self.MONTH_MAP.get(mon_text.lower()[:3])
        if month is None:
            return None

        try:
            day = int(day_text)
        except ValueError:
            return None

        year = self._infer_year_for_month_day(month, day)
        try:
            return f"{year:04d}-{month:02d}-{day:02d}"
        except Exception:
            return None

    def _infer_default_currency(self) -> str:
        subject = str(self.source_info.get('subject', '')).lower()
        sender = str(self.source_info.get('sender', '')).lower()
        sender_tag = str(self.source_info.get('sender_tag', '')).lower()
        hint = ' '.join([subject, sender, sender_tag])

        if any(k in hint for k in ['singapore', '.sg', 'sg statement', 'hsbc.com.sg']):
            return 'SGD'

        return self.CURRENCY


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
