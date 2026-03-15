import re
from typing import Dict, List, Optional

from .base import BaseBankParser, BankParseResult


class FirstBankCreditCardParser(BaseBankParser):
    SOURCE = "First Bank Credit Card"
    CURRENCY = "TWD"

    LINE_PATTERN = re.compile(
        r"^(?P<tx_md>\d{1,2}/\d{1,2})"
        r"(?:\s+(?P<post_md>\d{1,2}/\d{1,2}))?\s+"
        r"(?P<body>.+?)$"
    )
    AMOUNT_WITH_CARD_PATTERN = re.compile(
        r"(?P<desc>.+?)\s+(?P<amount>-?[0-9,]+(?:\.[0-9]+)?)\s+(?P<card>\d{4})$"
    )
    TRAILING_AMOUNT_PATTERN = re.compile(r"(?P<amount>-?[0-9,]+(?:\.[0-9]+)?)$")

    STOP_KEYWORDS = [
        "小計",
        "您的本期金額總計",
        "---------------結束----------------",
        "● ",
        "第2頁/共2頁",
    ]
    SKIP_KEYWORDS = [
        "消費日",
        "入帳",
        "起息日",
        "消費明細說明",
        "卡號",
        "後四碼",
        "消費",
        "國家",
        "幣別",
        "外幣金額",
        "折算日",
        "記名式悠遊卡卡號",
        "本期將於",
        "□應繳總額",
        "□最低應繳",
        "幣別 上期應繳金額",
    ]

    def parse(self) -> BankParseResult:
        txs: List[Dict] = []
        in_detail_section = False

        for raw_line in self.text.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("--- Page"):
                continue

            if "消費日 入帳" in line:
                in_detail_section = True
                continue

            if not in_detail_section:
                continue

            if any(keyword in line for keyword in self.STOP_KEYWORDS):
                break
            if any(keyword in line for keyword in self.SKIP_KEYWORDS):
                continue

            match = self.LINE_PATTERN.match(line)
            if not match:
                continue

            tx_date = self._month_day_to_iso(match.group("tx_md"))
            body = match.group("body").strip()

            amount: Optional[float] = None
            desc = body

            amount_with_card = self.AMOUNT_WITH_CARD_PATTERN.search(body)
            if amount_with_card:
                desc = amount_with_card.group("desc").strip()
                amount = self._parse_amount(amount_with_card.group("amount"))
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
                currency=self.CURRENCY,
                confidence=0.96,
                parsing_method="bank_parser_first_bank_card",
                raw_line=line,
                parser_name="FirstBankCreditCardParser",
            ))

        return BankParseResult(
            matched=True,
            parser_name="FirstBankCreditCardParser",
            transactions=txs,
            warnings=[],
        )


def _classify_expense_type(desc: str) -> str:
    lowered = desc.lower()
    if any(keyword in lowered for keyword in ["apple", "全支付", "全聯", "特斯拉"]):
        return "Shopping"
    if any(keyword in lowered for keyword in ["捷運", "悠遊卡"]):
        return "Transportation"
    if any(keyword in lowered for keyword in ["手續費", "回饋", "扣繳", "中華電信"]):
        return "Bills"
    return "Other"
