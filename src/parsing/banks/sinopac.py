import re
from typing import Dict, List, Optional

from .base import BaseBankParser, BankParseResult


class SinopacCreditCardParser(BaseBankParser):
    SOURCE = "Sinopac Credit Card"
    CURRENCY = "TWD"

    LINE_PATTERN = re.compile(
        r"^(?P<tx_md>\d{1,2}/\d{1,2})\s+"
        r"(?P<post_md>\d{1,2}/\d{1,2})\s+"
        r"(?P<body>.+?)$"
    )
    TRAILING_CURRENCY_PATTERN = re.compile(
        r"(?P<desc>.+?)\s+(?P<country>[A-Z]{2})\s+(?P<currency>[A-Z]{3})\s+"
        r"(?P<amount>-?[0-9,]+(?:\.[0-9]+)?)$"
    )
    TRAILING_AMOUNT_PATTERN = re.compile(r"(?P<amount>-?[0-9,]+(?:\.[0-9]+)?)$")

    SKIP_KEYWORDS = [
        "信用卡電子帳單",
        "帳單說明",
        "您的正卡，本期應繳金額合計",
        "【",
        "幣別",
        "卡號",
        "末四碼",
        "外幣金額",
        "總費用",
        "年百分率",
        "分期未到期",
        "消費日",
        "起息日",
    ]

    def parse(self) -> BankParseResult:
        txs: List[Dict] = []
        lines = self.text.splitlines()
        active_currency = self.CURRENCY
        i = 0

        while i < len(lines):
            line = lines[i].strip()
            i += 1

            if not line or line.startswith("--- Page"):
                continue
            if line in {"臺幣", "新臺幣"}:
                active_currency = "TWD"
                continue
            if line == "美元":
                active_currency = "USD"
                continue
            if any(keyword in line for keyword in self.SKIP_KEYWORDS):
                continue

            match = self.LINE_PATTERN.match(line)
            if not match:
                continue

            tx_date = self._month_day_to_iso(match.group("tx_md"))
            body_parts = [match.group("body").strip()]

            while i < len(lines):
                peek = lines[i].strip()
                if not peek or peek.startswith("--- Page"):
                    i += 1
                    continue
                if self.LINE_PATTERN.match(peek):
                    break
                if any(keyword in peek for keyword in self.SKIP_KEYWORDS):
                    break
                if peek in {"臺幣", "新臺幣", "美元"}:
                    break
                body_parts.append(peek)
                i += 1
                if self.TRAILING_AMOUNT_PATTERN.search(peek):
                    break

            body = " ".join(body_parts)
            body = re.sub(r"^\d{4}\s+", "", body).strip()

            currency = active_currency
            amount: Optional[float] = None
            desc = body

            currency_match = self.TRAILING_CURRENCY_PATTERN.search(body)
            if currency_match:
                desc = currency_match.group("desc").strip()
                currency = currency_match.group("currency").upper()
                amount = self._parse_amount(currency_match.group("amount"))
            else:
                amount_match = self.TRAILING_AMOUNT_PATTERN.search(body)
                if amount_match:
                    desc = body[:amount_match.start()].strip()
                    amount = self._parse_amount(amount_match.group("amount"))

            if amount is None:
                continue

            txs.append(self._build_transaction(
                date=tx_date,
                amount=amount,
                expense_name=desc or body,
                expense_type=_classify_expense_type(desc or body),
                source=self.SOURCE,
                currency=currency,
                confidence=0.96,
                parsing_method="bank_parser_sinopac_card",
                raw_line=line,
                parser_name="SinopacCreditCardParser",
            ))

        return BankParseResult(
            matched=True,
            parser_name="SinopacCreditCardParser",
            transactions=txs,
            warnings=[],
        )


def _classify_expense_type(desc: str) -> str:
    lowered = desc.lower()
    if any(keyword in lowered for keyword in ["amazon", "apple", "全聯", "大全聯"]):
        return "Shopping"
    if any(keyword in lowered for keyword in ["回饋", "手續費", "自扣", "扣繳"]):
        return "Bills"
    return "Other"
