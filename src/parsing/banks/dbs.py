import logging
import re
from datetime import datetime
from typing import Dict, List, Optional
from .base import BaseBankParser, BankParseResult

logger = logging.getLogger(__name__)

class DbsSgCardParser(BaseBankParser):
    """Parser for DBS Singapore credit card statements."""
    SOURCE = 'DBS_SG_CreditCard'
    CURRENCY = 'SGD'

    # Example: 01 JAN STARBUCKS 15.00
    LINE_PATTERN = re.compile(
        r'^(?P<day>\d{2})\s+(?P<mon>[A-Z]{3})\s+(?P<desc>.+?)\s+(?P<amount>[0-9,]+\.[0-9]{2})(?P<suffix>CR)?$',
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
                
                year = self._infer_year_for_month_day(mon, day)
                date_iso = f"{year}-{mon:02d}-{day:02d}"
                
                amount = float(m.group('amount').replace(',', ''))
                if m.group('suffix') == 'CR':
                    amount = -amount

                desc = m.group('desc').strip()
                
                txs.append(self._build_transaction(
                    date=date_iso,
                    amount=amount,
                    expense_name=desc,
                    expense_type='Other',
                    source=self.SOURCE,
                    currency=self.CURRENCY,
                    confidence=0.95,
                    parsing_method='bank_parser_dbs_sg_card',
                    raw_line=line,
                    parser_name='DbsSgCardParser'
                ))
                
        return BankParseResult(
            matched=len(txs) > 0,
            parser_name='DbsSgCardParser',
            transactions=txs
        )

class DbsSgBankParser(BaseBankParser):
    """Parser for DBS Singapore bank account statements (Consolidated)."""
    SOURCE = 'DBS_SG_Bank'
    CURRENCY = 'SGD'

    # Support DD/MM/YYYY or DD MMM
    DATE_PATTERN = re.compile(r'^(?P<date>\d{2}/\d{2}/\d{4})|^(?P<day>\d{2})\s+(?P<mon>[A-Z]{3})', re.IGNORECASE)
    
    # Amount pattern for sequential numbers at the end
    AMOUNTS_PATTERN = re.compile(r'(?P<amount>[0-9,]+\.[0-9]{2})\s+(?P<balance>[0-9,]+\.[0-9]{2})$')

    MONTH_MAP = {
        'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6,
        'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12
    }

    def parse(self) -> BankParseResult:
        txs = []
        lines = self.text.splitlines()
        
        current_tx = None
        prev_balance = None
        
        for i, line in enumerate(lines):
            line = line.strip()
            if not line or 'Balance Brought Forward' in line or 'Balance Carried Forward' in line:
                # Extract initial balance if possible
                m_init = re.search(r'Balance Brought Forward\s+[A-Z]{3}\s+(?P<bal>[0-9,]+\.[0-9]{2})', line)
                if m_init:
                    prev_balance = float(m_init.group('bal').replace(',', ''))
                continue

            date_match = self.DATE_PATTERN.match(line)
            if date_match:
                if current_tx:
                    txs.append(self._finalize_tx(current_tx, prev_balance))
                    prev_balance = current_tx['balance']
                
                # Start new transaction
                date_str = date_match.group('date')
                if date_str:
                    # DD/MM/YYYY -> YYYY-MM-DD
                    d, m, y = date_str.split('/')
                    date_iso = f"{y}-{m}-{d}"
                else:
                    d = int(date_match.group('day'))
                    mon = self.MONTH_MAP.get(date_match.group('mon').upper())
                    year = self._infer_year_for_month_day(mon, d)
                    date_iso = f"{year}-{mon:02d}-{d:02d}"
                
                # Remainder of line
                rest = line[date_match.end():].strip()
                
                # Check for amounts at end
                amt_match = self.AMOUNTS_PATTERN.search(rest)
                if amt_match:
                    amount = float(amt_match.group('amount').replace(',', ''))
                    balance = float(amt_match.group('balance').replace(',', ''))
                    desc = rest[:amt_match.start()].strip()
                else:
                    # Maybe amounts are on the next line or split? 
                    # For now, if no amounts, it's just a description part (unlikely for a start line)
                    amount = 0.0
                    balance = 0.0
                    desc = rest
                
                current_tx = {
                    'date': date_iso,
                    'desc_parts': [desc] if desc else [],
                    'amount': amount,
                    'balance': balance,
                    'raw_line': line
                }
            elif current_tx:
                # Continue description or handle extra data
                # If this line has amounts but current_tx has 0, update it?
                amt_match = self.AMOUNTS_PATTERN.search(line)
                if amt_match and current_tx['amount'] == 0:
                    current_tx['amount'] = float(amt_match.group('amount').replace(',', ''))
                    current_tx['balance'] = float(amt_match.group('balance').replace(',', ''))
                    desc = line[:amt_match.start()].strip()
                    if desc: current_tx['desc_parts'].append(desc)
                elif not any(k in line for k in ['Page', 'Total Balance', 'Statement Date']):
                    # Likely a continuation of description
                    # Exclude S/N or Reg lines if possible, or just keep them
                    if not re.match(r'^[A-Z0-9_]{10,}', line) and len(line) > 2:
                        current_tx['desc_parts'].append(line)

        if current_tx:
            txs.append(self._finalize_tx(current_tx, prev_balance))

        # Filter out 0-amount transactions if they are just headers or artifacts
        txs = [t for t in txs if t['amount'] != 0 or 'INTEREST' in t['expense_name'].upper()]

        return BankParseResult(
            matched=len(txs) > 0 or 'DBS Bank' in self.text,
            parser_name='DbsSgBankParser',
            transactions=txs
        )

    def _finalize_tx(self, tx_data: Dict, prev_balance: Optional[float]) -> Dict:
        full_desc = " ".join(tx_data['desc_parts']).strip()
        
        # Decide side
        side = 'expense'
        if prev_balance is not None:
            if abs(tx_data['balance'] - (prev_balance + tx_data['amount'])) < 0.01:
                side = 'income'
            elif abs(tx_data['balance'] - (prev_balance - tx_data['amount'])) < 0.01:
                side = 'expense'
            else:
                # Fallback to keywords if balance chain is broken
                if any(k in full_desc.upper() for k in ['INTEREST', 'DEPOSIT', 'GIRO INWARD', 'PAYNOW-FROM']):
                    side = 'income'
        else:
            # Fallback to keywords
            if any(k in full_desc.upper() for k in ['INTEREST', 'DEPOSIT', 'GIRO INWARD', 'PAYNOW-FROM']):
                side = 'income'

        tx = self._build_transaction(
            date=tx_data['date'],
            amount=tx_data['amount'],
            expense_name=full_desc,
            expense_type='Other',
            source=self.SOURCE,
            currency=self.CURRENCY,
            confidence=0.92,
            parsing_method='bank_parser_dbs_sg_bank',
            raw_line=tx_data['raw_line'],
            parser_name='DbsSgBankParser'
        )
        tx['cashflow_side'] = side
        tx['balance'] = tx_data['balance']
        return tx
