import logging
import re
from datetime import datetime
from typing import Dict, List, Optional
from .base import BaseBankParser, BankParseResult

logger = logging.getLogger(__name__)

class DbsSgCardParser(BaseBankParser):
    """Parser for DBS Singapore credit card statements."""
    SOURCE = 'DBS_SG'
    CURRENCY = 'SGD'

    # Example: 01 JAN STARBUCKS 15.00
    LINE_PATTERN = re.compile(
        r'^(?P<day>\d{2})\s+(?P<mon>[A-Z]{3})\s+(?P<desc>.+?)\s+(?P<amount>[0-9,]+\.[0-9]{2})$',
        re.IGNORECASE
    )

    MONTH_MAP = {
        'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6,
        'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12
    }

    def parse(self) -> BankParseResult:
        txs = []
        for line in self.text.splitlines():
            line = line.strip()
            if not line: continue
            
            m = self.LINE_PATTERN.match(line)
            if m:
                day = int(m.group('day'))
                mon_str = m.group('mon').upper()
                mon = self.MONTH_MAP.get(mon_str)
                if not mon: continue
                
                # Assume current year for statement (or infer from context if possible)
                year = datetime.now().year
                date_iso = f"{year}-{mon:02d}-{day:02d}"
                
                amount = float(m.group('amount').replace(',', ''))
                
                txs.append({
                    'date': date_iso,
                    'amount': amount,
                    'currency': self.CURRENCY,
                    'expense_name': m.group('desc').strip(),
                    'expense_type': 'Other',
                    'source': self.SOURCE,
                    'confidence': 0.95
                })
                
        return BankParseResult(matched=len(txs) > 0, transactions=txs)
