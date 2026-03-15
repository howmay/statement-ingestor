import re
from datetime import datetime
from typing import Dict, List, Optional

from .base import BaseBankParser, BankParseResult


class TaishinCreditCardParser(BaseBankParser):
    SOURCE = "Taishin Credit Card"
    CURRENCY = "TWD"

    LINE_PATTERN = re.compile(
        r"^(?P<tx_date>\d{7})\s+(?P<post_date>\d{7})\s+(?P<body>.+?)$"
    )
    SIGNED_AMOUNT_PATTERN = re.compile(
        r"(?P<desc>.+?)(?P<amount>[－-][0-9,]+(?:\.[0-9]+)?)(?:\s+(?P<trailing>[A-Z]{2}|[0-9]+))?$"
    )
    AMOUNT_WITH_TRAILING_TOKEN_PATTERN = re.compile(
        r"(?P<desc>.+?)\s+(?P<amount>[－-]?[0-9,]+(?:\.[0-9]+)?)\s+(?P<trailing>[A-Z]{2}|[0-9]+)$"
    )
    TRAILING_AMOUNT_PATTERN = re.compile(
        r"(?P<desc>.+?)(?:\s+|(?=[－-]))(?P<amount>[－-]?[0-9,]+(?:\.[0-9]+)?)$"
    )

    DETAIL_HEADER = "消費日 入帳起息日"
    STOP_KEYWORDS = [
        "-------------------------結束-------------------------",
        "【Richart卡",
        "貼 心 提 醒",
        "台端依契約得使用循環信用時",
    ]
    SKIP_KEYWORDS = [
        "消費明細(含消費地)",
        "Richart卡(",
        "卡號末四碼",
        "頁次：",
    ]

    def parse(self) -> BankParseResult:
        txs: List[Dict] = []
        in_detail_section = False

        for raw_line in self.text.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("--- Page"):
                continue

            if self.DETAIL_HEADER in line:
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

            tx_date = _roc_compact_to_iso(match.group("tx_date"))
            body = match.group("body").strip()

            amount: Optional[float] = None
            desc = body

            signed_amount_match = self.SIGNED_AMOUNT_PATTERN.search(body)
            if signed_amount_match:
                desc = signed_amount_match.group("desc").strip()
                amount = _parse_signed_amount(signed_amount_match.group("amount"))
            else:
                amount_match = self.AMOUNT_WITH_TRAILING_TOKEN_PATTERN.search(body)
            if amount is None and amount_match:
                desc = amount_match.group("desc").strip()
                amount = _parse_signed_amount(amount_match.group("amount"))
            elif amount is None:
                trailing_amount_match = self.TRAILING_AMOUNT_PATTERN.search(body)
                if trailing_amount_match:
                    desc = trailing_amount_match.group("desc").strip()
                    amount = _parse_signed_amount(trailing_amount_match.group("amount"))

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
                parsing_method="bank_parser_taishin_card",
                raw_line=line,
                parser_name="TaishinCreditCardParser",
            ))

        return BankParseResult(
            matched=True,
            parser_name="TaishinCreditCardParser",
            transactions=txs,
            warnings=[],
        )


def _roc_compact_to_iso(value: str) -> Optional[str]:
    match = re.match(r"^(?P<year>\d{3})(?P<month>\d{2})(?P<day>\d{2})$", value)
    if not match:
        return None

    year = int(match.group("year")) + 1911
    month = int(match.group("month"))
    day = int(match.group("day"))

    try:
        return datetime(year, month, day).strftime("%Y-%m-%d")
    except ValueError:
        return None


def _parse_signed_amount(raw_amount: str) -> Optional[float]:
    return BaseBankParser._parse_amount(raw_amount.replace("－", "-"))


class TaishinBankParser(BaseBankParser):
    SOURCE = "Taishin Bank"
    CURRENCY = "TWD"

    TWD_SECTION_HEADER = "新臺幣帳戶的往來明細"
    FX_SECTION_HEADER = "外幣帳戶的往來明細"
    STOP_KEYWORDS = ["各產品訊息區", "【公告】"]

    TWD_LINE_PATTERN = re.compile(
        r"^(?P<account>\S+)\s+(?P<date>\d{4}/\d{2}/\d{2})\s+(?P<summary>\S+)\s+(?P<rest>.+)$"
    )
    FX_LINE_PATTERN = re.compile(
        r"^(?P<account>\S+)\s+(?P<date>\d{4}/\d{2}/\d{2})\s+(?P<summary>\S+)\s+"
        r"(?P<currency>[A-Z]{3})\s+\$(?P<expense>[0-9,]+(?:\.[0-9]+)?)\s+"
        r"\$(?P<income>[0-9,]+(?:\.[0-9]+)?)\s+\$(?P<balance>[0-9,]+(?:\.[0-9]+)?)"
        r"(?:\s+(?P<note>.+))?$"
    )
    TWD_NOTELESS_PATTERN = re.compile(
        r"^(?P<summary>.+?)\s+\$(?P<amount>[0-9,]+(?:\.[0-9]+)?)\s+\$(?P<balance>[0-9,]+(?:\.[0-9]+)?)$"
    )
    TWD_WITH_NOTE_PATTERN = re.compile(
        r"^(?P<summary>.+?)\s+\$(?P<amount>[0-9,]+(?:\.[0-9]+)?)\s+\$(?P<balance>[0-9,]+(?:\.[0-9]+)?)\s+(?P<note>.+)$"
    )

    def parse(self) -> BankParseResult:
        txs: List[Dict] = []
        current_section: Optional[str] = None
        pending: Optional[Dict] = None

        for raw_line in self.text.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("--- Page"):
                continue

            if self.TWD_SECTION_HEADER in line:
                if pending:
                    txs.append(self._build_bank_transaction(pending))
                    pending = None
                current_section = "twd"
                continue

            if self.FX_SECTION_HEADER in line:
                if pending:
                    txs.append(self._build_bank_transaction(pending))
                    pending = None
                current_section = "fx"
                continue

            if any(keyword in line for keyword in self.STOP_KEYWORDS):
                if pending:
                    txs.append(self._build_bank_transaction(pending))
                    pending = None
                break

            if current_section == "twd" and line.startswith("帳號 日期 摘要"):
                continue
            if current_section == "fx" and line.startswith("帳號 日期 摘要"):
                continue
            if current_section not in {"twd", "fx"}:
                continue

            parsed = None
            if current_section == "twd":
                parsed = self._parse_twd_line(line)
            else:
                parsed = self._parse_fx_line(line)

            if parsed:
                if pending:
                    txs.append(self._build_bank_transaction(pending))
                pending = parsed
                continue

            if pending:
                pending["note_parts"].append(line)

        if pending:
            txs.append(self._build_bank_transaction(pending))

        return BankParseResult(
            matched=True,
            parser_name="TaishinBankParser",
            transactions=txs,
            warnings=[],
        )

    def _parse_twd_line(self, line: str) -> Optional[Dict]:
        match = self.TWD_LINE_PATTERN.match(line)
        if not match:
            return None

        date = match.group("date").replace("/", "-")
        rest = f'{match.group("summary")} {match.group("rest")}'.strip()

        detail = self.TWD_WITH_NOTE_PATTERN.match(rest)
        note = ""
        if detail:
            summary = detail.group("summary").strip()
            amount = self._parse_amount(detail.group("amount"))
            balance = self._parse_amount(detail.group("balance"))
            note = detail.group("note").strip()
        else:
            detail = self.TWD_NOTELESS_PATTERN.match(rest)
            if not detail:
                return None
            summary = detail.group("summary").strip()
            amount = self._parse_amount(detail.group("amount"))
            balance = self._parse_amount(detail.group("balance"))

        if amount is None or balance is None:
            return None

        side = _infer_bank_cashflow_side(summary, note, amount)

        return {
            "date": date,
            "amount": amount,
            "currency": "TWD",
            "summary": summary,
            "note_parts": [note] if note else [],
            "cashflow_side": side,
            "balance": balance,
        }

    def _parse_fx_line(self, line: str) -> Optional[Dict]:
        match = self.FX_LINE_PATTERN.match(line)
        if not match:
            return None

        expense = self._parse_amount(match.group("expense"))
        income = self._parse_amount(match.group("income"))
        balance = self._parse_amount(match.group("balance"))
        if expense is None or income is None or balance is None:
            return None

        summary = match.group("summary").strip()
        note = (match.group("note") or "").strip()

        if expense > 0:
            amount = expense
            side = "expense"
        else:
            amount = income
            side = "income"

        return {
            "date": match.group("date").replace("/", "-"),
            "amount": amount,
            "currency": match.group("currency"),
            "summary": summary,
            "note_parts": [note] if note else [],
            "cashflow_side": side,
            "balance": balance,
        }

    def _build_bank_transaction(self, data: Dict) -> Dict:
        note = " ".join(part for part in data["note_parts"] if part).strip()
        expense_name = data["summary"]
        if note:
            expense_name = f"{expense_name} {note}".strip()

        tx = self._build_transaction(
            date=data["date"],
            amount=data["amount"],
            expense_name=expense_name,
            expense_type=_classify_bank_expense_type(expense_name),
            source=self.SOURCE,
            currency=data["currency"],
            confidence=0.96,
            parsing_method="bank_parser_taishin_bank",
            raw_line=expense_name,
            parser_name="TaishinBankParser",
        )
        tx["cashflow_side"] = data["cashflow_side"]
        return tx


def _infer_bank_cashflow_side(summary: str, note: str, amount: float) -> str:
    lowered = f"{summary} {note}".lower()
    if any(keyword in lowered for keyword in ["轉入", "存款息", "interest"]):
        return "income"
    if any(keyword in lowered for keyword in ["轉出", "提款", "轉帳", "支取", "卡費"]):
        return "expense"
    return "income" if amount == 0 else "expense"


def _classify_bank_expense_type(desc: str) -> str:
    lowered = desc.lower()
    if any(keyword in lowered for keyword in ["卡費", "利息", "interest"]):
        return "Bills"
    if any(keyword in lowered for keyword in ["提款", "轉帳", "轉出", "支取", "ach"]):
        return "Transfer"
    return "Other"


def _classify_expense_type(desc: str) -> str:
    lowered = desc.lower()
    if any(keyword in lowered for keyword in ["apple", "app store", "itunes"]):
        return "Shopping"
    if any(keyword in lowered for keyword in ["手續費", "服務費", "自動轉帳扣繳", "扣繳", "信用卡款"]):
        return "Bills"
    return "Other"
