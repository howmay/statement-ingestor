from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
import re

MONTH_MAP = {
    'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
    'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
}


def _has_keyword(d: str, k: str) -> bool:
    # ASCII keywords match whole words ("ach" must not hit "coach"); CJK keywords are substrings.
    # ASCII-alnum edges, not \b: an adjacent CJK char is a boundary and "/ccp/" still matches "/ccp/4503".
    if not k.isascii():
        return k in d
    left = r'(?<![a-z0-9])' if k[0].isalnum() else ''
    right = r'(?![a-z0-9])' if k[-1].isalnum() else ''
    return re.search(left + re.escape(k) + right, d) is not None


def classify_expense_type(desc: str) -> str:
    d = desc.lower()
    if re.search(r'\bfees?\b', d) or any(_has_keyword(d, k) for k in [
        '自動轉帳繳款', '自動轉帳扣繳', '服務費', '國外交易服務費', '手續費', '年費', '電費', '水費',
        '瓦斯費', '電話費', '信用卡轉', '信用卡款', '利息', '繳款', '扣繳', '自扣', '回饋',
        '中華電信', 'payment',
    ]):
        return 'Bills'
    if any(_has_keyword(d, k) for k in ['uber', 'taxi', 'grab', 'trip', '交通', '計程車', '高鐵', '台鐵', '捷運', '悠遊卡']):
        return 'Transportation'
    if any(_has_keyword(d, k) for k in ['spotify', 'netflix', 'youtube', 'google', 'movie', '電影', '遊戲']):
        return 'Entertainment'
    if any(_has_keyword(d, k) for k in [
        'amazon', 'apple', 'app store', 'itunes', 'pchome', 'momo', 'shopping', '購物', '寶島',
        '全支付', '全聯', '大全聯', '特斯拉',
    ]):
        return 'Shopping'
    return 'Other'


def classify_bank_expense_type(desc: str) -> str:
    d = desc.lower()
    if any(_has_keyword(d, k) for k in ['利息', 'interest', '/ccp/', '卡費']):
        return 'Bills'
    if any(_has_keyword(d, k) for k in ['轉帳', 'global transfer', 'fisc', 'hiba881', '提款', '轉出', '支取', 'ach']):
        return 'Transfer'
    return 'Other'


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
        # Pattern for "DD MMM YYYY" or "MMM YYYY"
        eng_m = re.search(
            r'(?P<day>\d{1,2})?\s*(?P<mon>[A-Za-z]{3,10})\s+(?P<year>\d{4})',
            self.text,
            re.IGNORECASE
        )
        if eng_m:
            year = int(eng_m.group('year'))
            mon_str = eng_m.group('mon').lower()
            month = MONTH_MAP.get(mon_str[:3])
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

    def month_name_day_to_iso(self, day_text: str, mon_text: str, year_text: Optional[str] = None) -> Optional[str]:
        month = MONTH_MAP.get(mon_text.lower()[:3])
        if month is None:
            return None
        try:
            day = int(day_text)
            year = int(year_text) if year_text else self._infer_year_for_month_day(month, day)
            return f"{year:04d}-{month:02d}-{day:02d}"
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
