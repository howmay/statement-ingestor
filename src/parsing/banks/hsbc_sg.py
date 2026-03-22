import logging
import re
from datetime import datetime
from typing import Dict, List, Optional

from .base import BaseBankParser, BankParseResult

logger = logging.getLogger(__name__)


class HsbcSgCardParser(BaseBankParser):
    SOURCE = 'HSBC Singapore'
    CURRENCY = 'SGD'

    # SG CC style: 23Jan 22Jan DESCRIPTION AMOUNT
    # Date pattern: DDMon
    LINE_PATTERN = re.compile(
        r'^(?P<post_day>\d{1,2})(?P<post_mon>[A-Za-z]{3})\s+'
        r'(?P<tx_day>\d{1,2})(?P<tx_mon>[A-Za-z]{3})\s+'
        r'(?P<body>.+?)$',
        re.IGNORECASE,
    )

    MONTH_MAP = {
        'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4,
        'may': 5, 'jun': 6, 'jul': 7, 'aug': 8,
        'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
    }

    def parse(self) -> BankParseResult:
        txs: List[Dict] = []
        
        # Section detection (optional, some extractions might not have clean headers)
        in_summary_section = True 
        
        for raw_line in self.text.splitlines():
            line = raw_line.strip()
            if not line or line.startswith('--- Page'):
                continue

            # Section start/end detection - make it more flexible
            if 'ACCOUNT SUMMARY' in line.upper():
                in_summary_section = True
                continue
            if 'REWARDS SUMMARY' in line.upper() or 'CREDIT LIMIT AND INTEREST' in line.upper():
                # We usually don't want to stop immediately because some layouts are weird
                pass
                
            if not in_summary_section:
                continue

            m = self.LINE_PATTERN.match(line)
            if not m:
                continue

            tx_date = self._month_name_day_to_iso(m.group('tx_day'), m.group('tx_mon'))
            body = m.group('body').strip()

            if not tx_date or not body:
                continue

            # Amount extraction: [NUMBER] [CR]?
            # Note: CR might have a space before it or be adjacent.
            amount_match = re.search(r'(?P<amount>[0-9,]+\.[0-9]{2})\s*(?P<suffix>CR)?(?:\s*\(incl\s*GST\))?.*$', body, re.IGNORECASE)
            if not amount_match:
                continue

            amount = self._parse_amount(amount_match.group('amount'))
            if amount is None:
                continue

            if amount_match.group('suffix') and amount_match.group('suffix').upper() == 'CR':
                amount = -amount

            desc = body[:amount_match.start()].strip()

            txs.append(self._build_transaction(
                date=tx_date,
                amount=amount,
                expense_name=desc,
                expense_type='Other',
                source=self.SOURCE,
                currency=self.CURRENCY,
                confidence=0.95,
                parsing_method='bank_parser_hsbc_sg_card',
                raw_line=line,
                parser_name='HsbcSgCardParser',
            ))

        return BankParseResult(
            matched=len(txs) > 0 or 'HSBC VISA REVOLUTION' in self.text,
            parser_name='HsbcSgCardParser',
            transactions=txs,
        )

    def _month_name_day_to_iso(self, day_text: str, mon_text: str) -> Optional[str]:
        month = self.MONTH_MAP.get(mon_text.lower()[:3])
        if month is None:
            return None
        try:
            day = int(day_text)
            year = self._infer_year_for_month_day(month, day)
            return f"{year:04d}-{month:02d}-{day:02d}"
        except Exception:
            return None


class HsbcSgBankParser(BaseBankParser):
    SOURCE = 'HSBC Singapore Bank'
    CURRENCY = 'SGD'

    # Support DDMonYYYY (e.g., 02Feb2026) or DD Mon (e.g., 27 Feb)
    DATE_PATTERN = re.compile(
        r'^(?P<day>\d{1,2})(?P<mon>[A-Za-z]{3})(?P<year>\d{4})?'
        r'|^(?P<day2>\d{1,2})\s+(?P<mon2>[A-Za-z]{3})',
        re.IGNORECASE
    )

    MONTH_MAP = {
        'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4,
        'may': 5, 'jun': 6, 'jul': 7, 'aug': 8,
        'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
    }

    def parse(self) -> BankParseResult:
        txs: List[Dict] = []
        lines = self.text.splitlines()
        normalized_text = self.text.upper()
        
        # Only parse between these headers, but default to True if we see account identifier
        in_details_section = 'EVERYDAY GLOBAL ACC' in self.text.upper()
        
        current_tx = None
        prev_balance = None
        
        logger.info(f"Parsing HSBC SG Bank Statement, total lines: {len(lines)}")
        
        for line_idx, line in enumerate(lines):
            line = line.strip()
            if not line or '--- Page' in line: continue
            
            # Section detection
            upper_line = line.upper().replace(' ', '')
            if 'DETAILSOFYOURACCOUNTS' in upper_line:
                in_details_section = True
                logger.debug(f"Entered details section at line {line_idx+1}")
                continue
            
            if not in_details_section:
                # If we see a date-like line and we are already identified as HSBC SG,
                # we might have missed the header.
                if self.DATE_PATTERN.match(line) and 'EVERYDAY GLOBAL ACC' in self.text.upper():
                    in_details_section = True
                else:
                    continue
            
            # Re-check for end section if we just entered or are in section
            if 'CLOSINGBALANCE' in upper_line or 'ENDOFSTATEMENT' in upper_line:
                # End section
                if current_tx:
                    txs.append(self._finalize_tx(current_tx, prev_balance))
                    current_tx = None
                in_details_section = False
                logger.debug(f"Exited details section at line {line_idx+1}")
                continue

            # Initial balance detection
            if 'BALANCEBROUGHTFORWARD' in upper_line:
                parts = re.findall(r'[0-9,]+\.[0-9]{2}', line)
                if parts:
                    prev_balance = self._parse_amount(parts[-1])
                    logger.debug(f"Found brought forward balance: {prev_balance}")
                continue

            m = self.DATE_PATTERN.match(line)
            amounts = re.findall(r'[0-9,]+\.[0-9]{2}', line)
            
            # Skip noise lines that look like headers but contain amounts
            if any(k in upper_line for k in ['TOTALDEPOSITS', 'TOTALBORROWINGS', 'CREDITLIMIT']):
                continue

            is_new_tx_with_date = bool(m)
            # A same-day tx starts only if current tx already has a balance/amount
            is_new_tx_same_day = bool(not m and amounts and current_tx and current_tx['balance'] is not None)
            
            if is_new_tx_with_date or is_new_tx_same_day:
                if current_tx:
                    txs.append(self._finalize_tx(current_tx, prev_balance))
                    prev_balance = current_tx['balance']
                
                if is_new_tx_with_date:
                    # Parse date
                    day = m.group('day') or m.group('day2')
                    mon_str = (m.group('mon') or m.group('mon2')).lower()[:3]
                    month = self.MONTH_MAP.get(mon_str)
                    if not month: continue
                    
                    year_str = m.group('year')
                    year = int(year_str) if year_str else self._infer_year_for_month_day(month, int(day))
                    date_iso = f"{year:04d}-{month:02d}-{int(day):02d}"
                    
                    # Remainder of line
                    rest = line[m.end():].strip()
                    amounts_in_line = re.findall(r'[0-9,]+\.[0-9]{2}', rest)
                    
                    if amounts_in_line:
                        balance = self._parse_amount(amounts_in_line[-1])
                        amount_val = self._parse_amount(amounts_in_line[-2]) if len(amounts_in_line) > 1 else 0.0
                        desc = rest[:rest.find(amounts_in_line[0])].strip()
                    else:
                        balance = None
                        amount_val = 0.0
                        desc = rest

                    current_tx = {
                        'date': date_iso,
                        'desc_parts': [desc] if desc else [],
                        'amount': amount_val,
                        'balance': balance,
                        'raw_line': line
                    }
                else:
                    # Same day additional transaction
                    balance = self._parse_amount(amounts[-1])
                    amount_val = self._parse_amount(amounts[-2]) if len(amounts) > 1 else 0.0
                    
                    # Find description (everything before the first amount)
                    desc = line[:line.find(amounts[0])].strip()
                    
                    current_tx = {
                        'date': txs[-1]['date'] if txs else datetime.now().strftime('%Y-%m-%d'),
                        'desc_parts': [desc] if desc else [],
                        'amount': amount_val,
                        'balance': balance,
                        'raw_line': line
                    }
            elif current_tx:
                # Continuation of multi-line transaction
                if amounts and current_tx['balance'] is None:
                    current_tx['balance'] = self._parse_amount(amounts[-1])
                    if len(amounts) > 1 and current_tx['amount'] == 0:
                        current_tx['amount'] = self._parse_amount(amounts[-2])
                    
                    desc_extra = line[:line.find(amounts[0])].strip()
                    if desc_extra: current_tx['desc_parts'].append(desc_extra)
                elif not any(k in line.upper() for k in ['CLOSING BALANCE', 'TOTAL', 'STATEMENT', 'BALANCECARRIEDFORWARD']):
                    current_tx['desc_parts'].append(line)

        if current_tx:
            txs.append(self._finalize_tx(current_tx, prev_balance))

        logger.info(f"HSBC SG Bank Parser finished, found {len(txs)} raw transactions")

        # Filter out invalid or zero-amount non-interest transactions
        valid_txs = [t for t in txs if t['amount'] != 0 or 'INTEREST' in t['expense_name'].upper()]
        matched_signature = any(
            marker in normalized_text
            for marker in [
                'EVERYDAY GLOBAL ACC',
                'HSBC BANK (SINGAPORE)',
                'HSBC BANK (SINGAPORE) LIMITED',
                'PERSONAL BANKING STATEMENT',
                'DETAILS OF YOUR ACCOUNTS',
                'TRANSACTIONDETAILS',
            ]
        )
        
        return BankParseResult(
            matched=len(valid_txs) > 0 or matched_signature,
            parser_name='HsbcSgBankParser',
            transactions=valid_txs,
        )

    def _finalize_tx(self, tx_data: Dict, prev_balance: Optional[float]) -> Dict:
        full_desc = " ".join(tx_data['desc_parts']).strip()
        amount = tx_data['amount']
        balance = tx_data['balance']
        
        side = 'expense'
        if prev_balance is not None and balance is not None:
            # Running balance check
            if balance > prev_balance:
                side = 'income'
                if amount == 0: amount = round(balance - prev_balance, 2)
            else:
                side = 'expense'
                if amount == 0: amount = round(prev_balance - balance, 2)
        else:
            # Fallback to keywords
            if any(k in full_desc.upper() for k in ['INTEREST', 'DEPOSIT', 'SALARY', 'SALA']):
                side = 'income'

        tx = self._build_transaction(
            date=tx_data['date'],
            amount=amount,
            expense_name=full_desc,
            expense_type='Other',
            source=self.SOURCE,
            currency=self.CURRENCY,
            confidence=0.92,
            parsing_method='bank_parser_hsbc_sg_bank',
            raw_line=tx_data['raw_line'],
            parser_name='HsbcSgBankParser'
        )
        tx['cashflow_side'] = side
        tx['balance'] = balance
        return tx
