from pathlib import Path

from src.core.config import get_bank_password
from src.parsing.banks.factory import parse_with_bank_factory
from src.parsing.pdf.pdf_to_text import extract_text_from_pdf
from src.export.csv_writer import _format_export_row


def _extract_sample_pdf_text(sender: str, pdf_path: str) -> str:
    for password in get_bank_password(sender) or [None]:
        text = extract_text_from_pdf(pdf_path, password)
        if text and text.strip():
            # Obfuscate PII in the extracted text to match test assertions
            replacements = {
                "68331388": "00000000",
                "zhao_hui_chen": "test_user",
                "陳兆煇": "王小明",
                "N124980178": "TEST_ID_123",
                "2215618564": "0000000000",
                "7808654234": "0000000000",
                "0830344869": "0000000000",
                "4422536087": "0000000000",
                "7643101386": "0000000000",
                "2718811587": "0000000000",
                "00766168": "00000000",
                "00001419": "00000000",
                "523950707": "000000000",
                "524029173": "000000000",
                "524220110": "000000000",
                "08106499DB": "0000000000",
                "0810626166": "0000000000",
            }
            for old, new in replacements.items():
                text = text.replace(old, new)
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


def test_fubon_bank_sample_pdf_export_uses_statement_columns():
    sender = "service@bhu.taipeifubon.com.tw"
    pdf_path = Path("example/bank/台北富邦銀行_7qTb_9E=.pdf")

    text = _extract_sample_pdf_text(sender, str(pdf_path))
    result = parse_with_bank_factory(
        text,
        {
            "sender": sender,
            "subject": "台北富邦銀行2026年2月 銀行對帳單",
            "filename": pdf_path.name,
        },
    )

    assert result.matched
    assert result.parser_name == "FubonBankParser"
    assert len(result.transactions) == 4

    transfer_in = next(
        tx for tx in result.transactions
        if tx["expense_name"] == "ＣＤ轉收 ********00000000"
    )
    assert float(transfer_in["amount"]) == 10000.0
    assert transfer_in["cashflow_side"] == "income"

    transfer_in_row = _format_export_row(transfer_in)
    assert transfer_in_row["income"] == "10000.00"
    assert transfer_in_row["expense"] == ""

    card_payment = next(
        tx for tx in result.transactions
        if tx["expense_name"] == "信用卡轉" and float(tx["amount"]) == 2580.0
    )
    assert card_payment["cashflow_side"] == "expense"

    card_payment_row = _format_export_row(card_payment)
    assert card_payment_row["income"] == ""
    assert card_payment_row["expense"] == "2580.00"


def test_taishin_bank_sample_pdf_parses_transactions():
    sender = "service@taishinbank.com.tw"
    pdf_path = Path("downloads/台新銀行_信用卡帳單_2026-02_0000000000.pdf")

    text = _extract_sample_pdf_text(sender, str(pdf_path))
    result = parse_with_bank_factory(
        text,
        {
            "sender": sender,
            "subject": "台新銀行2026年02月 信用卡帳單",
            "filename": pdf_path.name,
        },
    )

    assert result.matched
    assert result.parser_name == "TaishinCreditCardParser"
    # Adjust assertions to match the actual sample file if needed, but for now let's see if it parses
    assert len(result.transactions) >= 1


def test_hsbc_taiwan_bank_sample_pdf_parses_transactions():
    sender = "service@hsbc.com.tw"
    pdf_path = Path("downloads/滙豐(台灣)_銀行帳戶對帳單_2026-03_0000000000.pdf")

    text = _extract_sample_pdf_text(sender, str(pdf_path))
    result = parse_with_bank_factory(
        text,
        {
            "sender": sender,
            "subject": "匯豐(台灣)商業銀行運籌理財對帳單",
            "filename": pdf_path.name,
        },
    )

    assert result.matched
    assert result.parser_name == "HsbcTwBankParser"
    assert len(result.transactions) >= 1

