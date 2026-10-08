"""Statement-level balances: account balances (assets) and card amounts due (liabilities).

Transactions tell you what moved; the summary block of each statement tells you
what you have. One regex rule set per statement layout, selected by a text marker
so a mis-labelled file still lands on the right rule.
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

AMT = r'(-?[0-9,]+(?:\.[0-9]+)?)'


def _num(s: str) -> float:
    return abs(float(s.replace(',', '')))


MONTHS = {m: i for i, m in enumerate(['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC'], 1)}


def _month_end(year: int, month: int) -> str:
    nxt = datetime(year + (month == 12), month % 12 + 1, 1)
    return (nxt - timedelta(days=1)).strftime('%Y-%m-%d')


def _statement_date(text: str, source_info: Dict[str, Any]) -> str:
    """Closing date of the statement: explicit period/filename first, then the latest plausible date."""
    names = f"{source_info.get('filename') or ''} {os.path.basename(str(source_info.get('filepath') or ''))}"
    today = datetime.now()

    m = re.search(r'對帳單(?:資料)?期間[：:]\s*\d{4}/\d{1,2}/\d{1,2}\s*[~～-]\s*(\d{4})/(\d{1,2})/(\d{1,2})', text)
    if m:
        return datetime(*map(int, m.groups())).strftime('%Y-%m-%d')
    m = re.search(r'[Ff]rom \d{1,2} [A-Za-z]{3} \d{4} to (\d{1,2}) ([A-Za-z]{3}) (\d{4})', text)
    if m:
        return datetime(int(m.group(3)), MONTHS[m.group(2).upper()], int(m.group(1))).strftime('%Y-%m-%d')
    m = re.search(r'現值參考日[:：]\s*(\d{4})/(\d{1,2})/(\d{1,2})', text)
    if m:
        return datetime(*map(int, m.groups())).strftime('%Y-%m-%d')
    m = re.search(r'(\d{4})年(\d{1,2})月份', text)
    if m:
        return _month_end(int(m.group(1)), int(m.group(2)))
    m = re.search(r'(\d{3})年(\d{1,2})月\s*信用卡帳單', text)
    if m:
        return _month_end(int(m.group(1)) + 1911, int(m.group(2)))
    m = re.search(r'(\d{2})([A-Z]{3})(\d{4})', names.upper())
    if m and m.group(2) in MONTHS:
        return datetime(int(m.group(3)), MONTHS[m.group(2)], int(m.group(1))).strftime('%Y-%m-%d')
    m = re.search(r'(\d{2})-(\d{2})-(\d{4})', names)
    if m:
        return datetime(int(m.group(3)), int(m.group(2)), int(m.group(1))).strftime('%Y-%m-%d')
    m = re.search(r'_(\d{4})-(\d{2})_', names)
    if m:
        return _month_end(int(m.group(1)), int(m.group(2)))

    candidates = []
    for y, mo, d in re.findall(r'(?<!\d)(\d{4})/(\d{1,2})/(\d{1,2})(?!\d)', text):
        candidates.append((int(y), int(mo), int(d)))
    for d, mo, y in re.findall(r'(?<!\d)(\d{1,2})/(\d{1,2})/(\d{4})(?!\d)', text):
        candidates.append((int(y), int(mo), int(d)))
    for d, mon, y in re.findall(r'(?<!\w)(\d{1,2}) ?([A-Za-z]{3}) ?(\d{4})(?!\d)', text):
        if mon.upper() in MONTHS:
            candidates.append((int(y), MONTHS[mon.upper()], int(d)))
    dates = []
    for y, mo, d in candidates:
        try:
            dt = datetime(y, mo, d)
        except ValueError:
            continue
        if 2000 <= y and dt <= today:
            dates.append(dt)
    return (max(dates) if dates else today).strftime('%Y-%m-%d')


def _taishin(t: str) -> List[tuple]:
    out = []
    m = re.search(r'Richart總資產\s+\$' + AMT, t)
    if m:
        out.append(('Taishin', 'Richart總資產', 'TWD', _num(m.group(1)), 'asset'))
    for m in re.finditer(r'^(新臺幣\S*)\s+(\d{4,}\*+\d+)\s+\$' + AMT, t, re.M):
        out.append(('Taishin', f'{m.group(1)} {m.group(2)}', 'TWD', _num(m.group(3)), 'asset'))
    return out


def _hsbc_tw(t: str) -> List[tuple]:
    out = []
    m = re.search(r'^存款\s+' + AMT + r'$', t, re.M)
    if m:
        out.append(('HSBC Taiwan', '存款合計', 'TWD', _num(m.group(1)), 'asset'))
    m = re.search(r'^信用卡\s+' + AMT + r'$', t, re.M)
    if m and _num(m.group(1)):
        out.append(('HSBC Taiwan', '信用卡', 'TWD', _num(m.group(1)), 'liability'))
    for m in re.finditer(r'^(\S+存款)\s+([A-Z]{3})\s+(\S+)\s+' + AMT + r'\s+' + AMT + r'$', t, re.M):
        out.append(('HSBC Taiwan', f'{m.group(1)} {m.group(3)}', m.group(2), _num(m.group(4)), 'asset'))
    return out


def _esun_bank(t: str) -> List[tuple]:
    out = []
    m = re.search(r'總資產現值\s+' + AMT, t)
    if m:
        out.append(('E.SUN', '總資產現值', 'TWD', _num(m.group(1)), 'asset'))
    for m in re.finditer(r'^(\S+(?:活存|定存))\s+(\d+\*+\d+)\s+([A-Z]{3})\s+' + AMT + r'$', t, re.M):
        out.append(('E.SUN', f'{m.group(1)} {m.group(2)}', m.group(3), _num(m.group(4)), 'asset'))
    return out


def _dbs_tw(t: str) -> List[tuple]:
    return [('DBS Taiwan', f'{m.group(1)} {m.group(2)}', m.group(3), _num(m.group(4)), 'asset')
            for m in re.finditer(r'^(\S+存款)\s+(\S*\*+\S*)\s+([A-Z]{3})\s+' + AMT + r'$', t, re.M)]


def _fubon_bank(t: str) -> List[tuple]:
    out = []
    m = re.search(r'資產總計\s+' + AMT, t)
    if m:
        out.append(('Fubon', '資產總計', 'TWD', _num(m.group(1)), 'asset'))
    for m in re.finditer(r'^(活期存款|外幣活期|定期存款|外幣定存)\s+\S+\s+(\S+)\s+([A-Z]{3})\s+(?:\S*\s+)?' + AMT + r'$', t, re.M):
        out.append(('Fubon', f'{m.group(1)} {m.group(2)}', m.group(3), _num(m.group(4)), 'asset'))
    return out


def _hsbc_sg_composite(t: str) -> List[tuple]:
    out = []
    m = re.search(r'TotalDepositsandInvestments\s+' + AMT, t)
    if m:
        out.append(('HSBC Singapore', 'Deposits & Investments', 'SGD', _num(m.group(1)), 'asset'))
    m = re.search(r'TotalBorrowings\s+' + AMT, t)
    if m and _num(m.group(1)):
        out.append(('HSBC Singapore', 'Borrowings', 'SGD', _num(m.group(1)), 'liability'))
    return out


def _wise(t: str) -> List[tuple]:
    out = []
    for m in re.finditer(r'^\d{1,2} \w{3} \d{4} (.+?) \S+ [\d.,]+ [\d.,]+ ' + AMT + r' ([A-Z]{3})$', t, re.M):
        out.append(('Wise', m.group(1), m.group(3), _num(m.group(2)), 'asset'))
    return out


def _fubon_nano(t: str) -> List[tuple]:
    cur = re.search(r'幣別：([A-Z]{3})', t)
    m = re.search(r'^合計\s+[\d,.]+\s+' + AMT, t, re.M)
    return [('Fubon 奈米投', '參考市值', cur.group(1) if cur else 'USD', _num(m.group(1)), 'asset')] if m else []


def _card_due(bank: str, currency: str, pattern: str):
    def rule(t: str) -> List[tuple]:
        m = re.search(pattern, t)
        return [(bank, '信用卡本期應繳', currency, _num(m.group(1)), 'liability')] if m else []
    return rule


# (text marker that identifies the layout, extractor)
RULES = [
    ('Richart總資產', _taishin),
    ('帳戶總覽 等值新臺幣', _hsbc_tw),
    ('總資產現值', _esun_bank),
    ('帳戶摘要', _dbs_tw),
    ('資產總計', _fubon_bank),
    ('TotalDepositsandInvestments', _hsbc_sg_composite),
    ('Portfolio Value', _wise),
    ('【奈米投】電子對帳單', _fubon_nano),
    ('本期應繳總金額', _card_due('E.SUN', 'TWD', r'本期應繳總金額[：:]?\s*TWD\s*' + AMT)),
    ('本期應繳總額', _card_due('Fubon', 'TWD', r'本期應繳總額\s*' + AMT + r'元')),
    ('Total Due', _card_due('HSBC Singapore', 'SGD', r'Total Due\s+' + AMT)),
]


def extract_balances(text: str, source_info: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Return [{date, bank, account, currency, balance, kind}] found in a statement's summary."""
    text = text or ''
    source_info = source_info or {}
    found: List[tuple] = []
    for marker, rule in RULES:
        if marker in text:
            found.extend(rule(text))
    if not found:
        return []
    date = _statement_date(text, source_info)
    return [{'date': date, 'bank': b, 'account': a, 'currency': c, 'balance': v, 'kind': k} for b, a, c, v, k in found]
