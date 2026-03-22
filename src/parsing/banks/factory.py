from __future__ import annotations

from typing import Any, Dict, Optional

from .base import BankParseResult, BaseBankParser
from .hsbc import HsbcTwBankParser, HsbcTwCardParser
from .hsbc_sg import HsbcSgBankParser, HsbcSgCardParser
from .fubon import FubonBankParser, FubonCreditCardParser
from .esun import EsunBankParser, EsunCardParser
from .dbs import DbsSgBankParser, DbsSgCardParser
from .sinopac import SinopacCreditCardParser
from .firstbank import FirstBankCreditCardParser
from .taishin import TaishinBankParser, TaishinCreditCardParser


def get_bank_parser(text: str, source_info: Optional[Dict[str, Any]] = None) -> Optional[BaseBankParser]:
    source_info = source_info or {}
    sender_tag = str(source_info.get('sender_tag', '')).lower()
    sender = str(source_info.get('sender', '')).lower()
    subject = str(source_info.get('subject', '')).lower()
    filename = str(source_info.get('filename', '')).lower()

    bank_hint = ' '.join([sender_tag, sender, subject, filename])
    text_hint = text.lower()[:4000]

    if 'hsbc' in bank_hint or 'hsbc bank (singapore)' in text.lower()[:1000]:
        # Singapore HSBC
        if any(k in bank_hint for k in ['hsbc.com.sg', 'singapore', 'hsbc_sg']) or 'hsbc bank (singapore)' in text.lower()[:1000]:
            is_sg_card = any(k in bank_hint for k in ['credit card', '信用卡']) or any(
                marker in text_hint
                for marker in [
                    'hsbc visa revolution',
                    'post tran account summary',
                    'payment-thankyou',
                ]
            )
            if is_sg_card:
                return HsbcSgCardParser(text, source_info)
            return HsbcSgBankParser(text, source_info)
        
        # Taiwan HSBC
        if any(k in bank_hint for k in ['cards@estatements.hsbc.com.tw', 'credit card', '信用卡']):
            return HsbcTwCardParser(text, source_info)
        return HsbcTwBankParser(text, source_info)

    if 'fubon' in bank_hint or 'taipeifubon' in bank_hint:
        # Fubon has multiple statement types: bank account statement / credit-card statement
        is_credit_card = any(k in bank_hint for k in ['信用卡', 'credit card', 'card statement', 'card'])
        if is_credit_card:
            return FubonCreditCardParser(text, source_info)
        return FubonBankParser(text, source_info)

    if 'esun' in bank_hint or '玉山' in bank_hint:
        is_card = any(k in bank_hint for k in ['信用卡', 'credit card', 'card', '簽帳金融卡', '金融卡', 'debit card'])
        if is_card:
            return EsunCardParser(text, source_info)
        return EsunBankParser(text, source_info)

    if 'dbs' in bank_hint or 'dbs bank' in text.lower()[:4000] or 'consolidated statement' in text[:2000].lower():
        is_card = any(k in bank_hint for k in ['credit card', '信用卡']) or 'card' in filename
        if is_card:
            return DbsSgCardParser(text, source_info)
        return DbsSgBankParser(text, source_info)

    if 'banksinopac' in bank_hint or 'sinopac' in bank_hint or '永豐' in bank_hint:
        return SinopacCreditCardParser(text, source_info)

    if 'ebill.firstbank.tw' in bank_hint or 'firstbank' in bank_hint or '第一銀行' in bank_hint:
        return FirstBankCreditCardParser(text, source_info)

    if 'taishin' in bank_hint or '台新' in bank_hint:
        is_credit_card = any(k in bank_hint for k in ['信用卡', 'credit card', 'card']) and '綜合對帳單' not in bank_hint
        if is_credit_card:
            return TaishinCreditCardParser(text, source_info)
        return TaishinBankParser(text, source_info)

    return None


def parse_with_bank_factory(text: str, source_info: Optional[Dict[str, Any]] = None) -> BankParseResult:
    parser = get_bank_parser(text, source_info)
    if parser is None:
        return BankParseResult(matched=False)
    return parser.parse()
