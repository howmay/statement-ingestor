import csv
import io
from datetime import datetime
from typing import Any, Dict, List, Optional


def parse_csv_statement(text: str, source_info: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    source_info = source_info or {}
    if not text or not text.strip():
        return []

    reader = csv.DictReader(io.StringIO(text))
    transactions: List[Dict[str, Any]] = []

    for row in reader:
        state = str(row.get("State") or "").strip().upper()
        if state and state != "COMPLETED":
            continue

        amount = _parse_float(row.get("Amount"))
        if amount is None:
            continue

        date = _parse_datetime_to_date(row.get("Completed Date")) or _parse_datetime_to_date(row.get("Started Date"))
        description = str(row.get("Description") or "CSV Transaction").strip() or "CSV Transaction"
        currency = str(row.get("Currency") or "TWD").strip() or "TWD"

        transactions.append(
            {
                "date": date,
                "amount": amount,
                "cashflow_side": _infer_cashflow_side(amount),
                "currency": currency,
                "expense_name": description[:120],
                "expense_type": "Other",
                "source": "CSV Attachment",
                "confidence": 0.99,
                "raw_text_snippet": str(row),
                "parsed_at": datetime.now().isoformat(),
                "llm_model": None,
                "parsing_method": "csv_statement_parser",
                "parser_name": "CsvStatementParser",
            }
        )

    return transactions


def _parse_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    raw = str(value).strip().replace(",", "")
    if raw == "":
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _infer_cashflow_side(amount: float) -> Optional[str]:
    if amount > 0:
        return "income"
    if amount < 0:
        return "expense"
    return None


def _parse_datetime_to_date(value: Any) -> Optional[str]:
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None

    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None
