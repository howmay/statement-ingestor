from pathlib import Path

from src.core.config import get_bank_password
from src.parsing.banks.factory import parse_with_bank_factory
from src.parsing.pdf.pdf_to_text import extract_text_from_pdf
from src.export.csv_writer import _format_export_row


def _extract_sample_pdf_text(sender: str, pdf_path: str) -> str:
    for password in get_bank_password(sender) or [None]:
        text = extract_text_from_pdf(pdf_path, password)
        if text and text.strip():
            return text
    raise AssertionError(f"could not extract text from sample PDF: {pdf_path}")


def test_sinopac_sample_pdf_parses_transactions():
    sender = "ebillservice@newebill.banksinopac.com.tw"
    pdf_path = Path("example/bank/永豐銀行信用卡帳單.pdf")

    text = _extract_sample_pdf_text(sender, str(pdf_path))
    result = parse_with_bank_factory(
        text,
        {
            "sender": sender,
            "subject": "2026年2月 永豐銀行信用卡電子帳單",
            "filename": pdf_path.name,
        },
    )

    assert result.matched
    assert result.parser_name == "SinopacCreditCardParser"
    assert len(result.transactions) == 4

    auto_debit = next(
        tx for tx in result.transactions
        if "永豐自扣已入帳" in tx["expense_name"]
    )
    assert auto_debit["date"] == "2026-02-05"
    assert float(auto_debit["amount"]) == -659.0

    amazon = next(
        tx for tx in result.transactions
        if "amazon mktpl" in tx["expense_name"].lower()
    )
    assert amazon["date"] == "2026-01-24"
    assert float(amazon["amount"]) == 89.03
    assert amazon["currency"] == "USD"

    reward = next(
        tx for tx in result.transactions
        if "國內消費回饋" in tx["expense_name"]
    )
    assert float(reward["amount"]) == -11.0


def test_first_bank_sample_pdf_parses_transactions():
    sender = "service@ebill.firstbank.tw"
    pdf_path = Path("example/bank/第一銀行電子對帳單2026年02月.pdf")

    text = _extract_sample_pdf_text(sender, str(pdf_path))
    result = parse_with_bank_factory(
        text,
        {
            "sender": sender,
            "subject": "第一銀行 115年02月 信用卡消費明細",
            "filename": pdf_path.name,
        },
    )

    assert result.matched
    assert result.parser_name == "FirstBankCreditCardParser"
    assert len(result.transactions) == 13

    apple = next(
        tx for tx in result.transactions
        if tx["expense_name"] == "APPLE.COM/BILL"
    )
    assert apple["date"] == "2026-01-07"
    assert float(apple["amount"]) == 300.0

    cashback = next(
        tx for tx in result.transactions
        if "現金回饋" in tx["expense_name"]
    )
    assert float(cashback["amount"]) == -17.0


def test_sinopac_sample_pdf_export_classification():
    sender = "ebillservice@newebill.banksinopac.com.tw"
    pdf_path = Path("example/bank/永豐銀行信用卡帳單.pdf")

    text = _extract_sample_pdf_text(sender, str(pdf_path))
    result = parse_with_bank_factory(
        text,
        {
            "sender": sender,
            "subject": "2026年2月 永豐銀行信用卡電子帳單",
            "filename": pdf_path.name,
        },
    )

    reward = next(
        tx for tx in result.transactions
        if "國內消費回饋" in tx["expense_name"]
    )
    reward_row = _format_export_row(reward)
    assert reward_row["income"] == "11.00"
    assert reward_row["expense"] == ""

    amazon = next(
        tx for tx in result.transactions
        if "amazon mktpl" in tx["expense_name"].lower()
    )
    amazon_row = _format_export_row(amazon)
    assert amazon_row["income"] == ""
    assert amazon_row["expense"] == "89.03"
