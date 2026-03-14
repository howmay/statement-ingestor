from __future__ import annotations

from typing import Any, Dict, Optional

from .base import BankParseResult, BaseBankParser
from .hsbc import HsbcTwCardParser
from .fubon import FubonBankParser, FubonCreditCardParser
from .esun import EsunCardParser
from .dbs import DbsSgCardParser
from .sinopac import SinopacCreditCardParser
from .firstbank import FirstBankCreditCardParser


def get_bank_parser(text: str, source_info: Optional[Dict[str, Any]] = None) -> Optional[BaseBankParser]:
    source_info = source_info or {}
    sender_tag = str(source_info.get('sender_tag', '')).lower()
    sender = str(source_info.get('sender', '')).lower()
    subject = str(source_info.get('subject', '')).lower()

    bank_hint = ' '.join([sender_tag, sender, subject])

    if 'hsbc' in bank_hint:
        return HsbcTwCardParser(text, source_info)

    if 'fubon' in bank_hint or 'taipeifubon' in bank_hint:
        # Fubon has multiple statement types: bank account statement / credit-card statement
        is_credit_card = any(k in bank_hint for k in ['信用卡', 'credit card', 'card statement', 'card'])
        if is_credit_card:
            return FubonCreditCardParser(text, source_info)
        return FubonBankParser(text, source_info)

    if 'esun' in bank_hint or sender_tag == '_bank':
        return EsunCardParser(text, source_info)

    if 'dbs' in bank_hint:
        return DbsSgCardParser(text, source_info)

    if 'banksinopac' in bank_hint or 'sinopac' in bank_hint or '永豐' in bank_hint:
        return SinopacCreditCardParser(text, source_info)

    if 'ebill.firstbank.tw' in bank_hint or 'firstbank' in bank_hint or '第一銀行' in bank_hint:
        return FirstBankCreditCardParser(text, source_info)

    return None


def parse_with_bank_factory(text: str, source_info: Optional[Dict[str, Any]] = None) -> BankParseResult:
    parser = get_bank_parser(text, source_info)
    if parser is None:
        return BankParseResult(matched=False)
    return parser.parse()
