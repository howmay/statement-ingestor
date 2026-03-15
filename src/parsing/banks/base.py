from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
import re


@dataclass
class BankParseResult:
    matched: bool
    parser_name: Optional[str] = None
    transactions: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


class BaseBankParser:
    """Base class for deterministic bank statement parsers."""

    SOURCE = "Unknown"
    CURRENCY = "TWD"

    def __init__(self, text: str, source_info: Optional[Dict[str, Any]] = None):
        self.text = text or ""
        self.source_info = source_info or {}
        self.reference_date = self._infer_reference_date()

    def parse(self) -> BankParseResult:
        raise NotImplementedError

    def _infer_reference_date(self) -> datetime:
        """
        Infer reference date from statement text/subject.
        Used to infer year for MM/DD style transaction rows.
        """
        # 1) Prefer full Gregorian date in extracted text (YYYY/MM/DD)
        m = re.search(r'(\d{4})/(\d{1,2})/(\d{1,2})', self.text)
        if m:
            try:
                return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except ValueError:
                pass

        # 2) English date patterns (e.g. 28 Feb 2024 or February 2024)
        month_map = {
            'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
            'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
            'january': 1, 'february': 2, 'march': 3, 'april': 4, 'june': 6,
            'july': 7, 'august': 8, 'september': 9, 'october': 10, 'november': 11, 'december': 12
        }
        # Pattern for "DD MMM YYYY" or "MMM YYYY"
        eng_m = re.search(
            r'(?P<day>\d{1,2})?\s*(?P<mon>[A-Za-z]{3,10})\s+(?P<year>\d{4})',
            self.text,
            re.IGNORECASE
        )
        if eng_m:
            year = int(eng_m.group('year'))
            mon_str = eng_m.group('mon').lower()
            month = month_map.get(mon_str) or month_map.get(mon_str[:3])
            if month:
                day = int(eng_m.group('day')) if eng_m.group('day') else 1
                try:
                    return datetime(year, month, day)
                except ValueError:
                    pass

        subject = str(self.source_info.get('subject', ''))

        # 2) Subject pattern with ROC year (e.g. 115年01月)
        m = re.search(r'(\d{3,4})年\s*(\d{1,2})月', subject)
        if m:
            year = int(m.group(1))
            month = int(m.group(2))
            if year < 1911:
                year += 1911
            try:
                return datetime(year, month, 1)
            except ValueError:
                pass

        # 3) Subject Gregorian year-month fallback
        m = re.search(r'(\d{4})[/-](\d{1,2})', subject)
        if m:
            try:
                return datetime(int(m.group(1)), int(m.group(2)), 1)
            except ValueError:
                pass

        return datetime.now()

    def _infer_year_for_month_day(self, month: int, day: int) -> int:
        year = self.reference_date.year

        # Typical statement case: Jan statement includes previous Dec transactions.
        if month > self.reference_date.month:
            year -= 1

        # Guard rail (should not raise for valid data here)
        if month < 1 or month > 12:
            return self.reference_date.year
        if day < 1 or day > 31:
            return self.reference_date.year

        return year

    def _month_day_to_iso(self, month_day: str) -> Optional[str]:
        m = re.match(r'^(\d{1,2})/(\d{1,2})$', month_day.strip())
        if not m:
            return None

        month = int(m.group(1))
        day = int(m.group(2))
        year = self._infer_year_for_month_day(month, day)

        try:
            return datetime(year, month, day).strftime('%Y-%m-%d')
        except ValueError:
            return None

    @staticmethod
    def _parse_amount(raw_amount: str) -> Optional[float]:
        if raw_amount is None:
            return None
        cleaned = raw_amount.replace(',', '').strip()
        if cleaned in {'', '-', '--'}:
            return None
        try:
            return float(cleaned)
        except ValueError:
            return None

    @staticmethod
    def _build_transaction(
        *,
        date: Optional[str],
        amount: Optional[float],
        expense_name: str,
        expense_type: str,
        source: str,
        currency: str,
        confidence: float,
        parsing_method: str,
        raw_line: str,
        parser_name: str,
    ) -> Dict[str, Any]:
        return {
            'date': date,
            'amount': amount,
            'currency': currency,
            'expense_name': expense_name[:120] if expense_name else 'Transaction',
            'expense_type': expense_type,
            'source': source,
            'confidence': confidence,
            'raw_text_snippet': raw_line[:200],
            'parsed_at': datetime.now().isoformat(),
            'llm_model': None,
            'parsing_method': parsing_method,
            'parser_name': parser_name,
        }
