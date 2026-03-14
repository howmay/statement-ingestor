from pathlib import Path

from src.parsing.csv.statement_csv import parse_csv_statement


SAMPLE_CSV = """Type,Product,Started Date,Completed Date,Description,Amount,Fee,Currency,State,Balance
Exchange,Current,2025-03-16 23:12:00,2025-03-16 23:12:00,Exchanged to TRY,2742.04,27.42,TRY,COMPLETED,2714.62
Card Payment,Current,2025-03-16 23:30:33,2025-03-17 11:49:12,turgame,-312.94,0,TRY,COMPLETED,2401.68
"""


def test_parse_csv_statement_maps_known_columns():
    transactions = parse_csv_statement(
        SAMPLE_CSV,
        {
            "filename": "wallet_statement.csv",
            "sender": "wallet@example.com",
        },
    )

    assert len(transactions) == 2

    exchange = transactions[0]
    assert exchange["date"] == "2025-03-16"
    assert exchange["expense_name"] == "Exchanged to TRY"
    assert float(exchange["amount"]) == 2742.04
    assert exchange["currency"] == "TRY"
    assert exchange["source"] == "CSV Attachment"

    payment = transactions[1]
    assert payment["date"] == "2025-03-17"
    assert payment["expense_name"] == "turgame"
    assert float(payment["amount"]) == -312.94
    assert payment["currency"] == "TRY"


def test_parse_csv_statement_skips_non_completed_rows():
    text = """Type,Completed Date,Description,Amount,Currency,State
Card Payment,2025-03-17 11:49:12,turgame,-312.94,TRY,COMPLETED
Card Payment,2025-03-18 11:49:12,pending row,-100.00,TRY,PENDING
"""

    transactions = parse_csv_statement(text, {"filename": "wallet_statement.csv"})

    assert len(transactions) == 1
    assert transactions[0]["expense_name"] == "turgame"
