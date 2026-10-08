import csv

from src.parsing.banks.balances import extract_balances
from src.export.csv_writer import export_balances_to_csv


def _rows(text, filename='x.pdf', subject=''):
    return [(b['bank'], b['account'], b['currency'], b['balance'], b['kind']) for b in extract_balances(text, {'filename': filename, 'subject': subject})]


def test_taishin_bank_total_and_accounts():
    text = "您在本行的Richart帳戶總覽\nRichart總資產 $102,039\n帳號類別 帳戶號碼 定存/專案起迄日 定存/專案利率% 帳戶餘額 備註\n新臺幣活存 288810****5696 $83,098 Richart\n合計 $83,098\n現值參考日:2026/08/31\n"
    assert _rows(text) == [('Taishin', 'Richart總資產', 'TWD', 102039.0, 'asset'), ('Taishin', '新臺幣活存 288810****5696', 'TWD', 83098.0, 'asset')]
    assert _rows("Richart總資產 $1\n外幣活存 88875****337 $95,357 Richart\n")[1:] == []


def test_hsbc_tw_bank_overview_and_accounts():
    text = "帳戶總覽 等值新臺幣\n存款 3,815,417\n借款 0\n信用卡 -596\n帳戶概要\n帳戶種類 幣別/帳戶號碼 結餘 等值新臺幣\n活期存款 TWD 716-16XXXX-388 3,336,485 3,336,485\n活期存款 SGD 716-16XXXX-821 10,000 247,793\n09/07/2026 承前結餘 3,339,973\n"
    assert _rows(text) == [
        ('HSBC Taiwan', '存款合計', 'TWD', 3815417.0, 'asset'),
        ('HSBC Taiwan', '信用卡', 'TWD', 596.0, 'liability'),
        ('HSBC Taiwan', '活期存款 716-16XXXX-388', 'TWD', 3336485.0, 'asset'),
        ('HSBC Taiwan', '活期存款 716-16XXXX-821', 'SGD', 10000.0, 'asset'),
    ]


def test_esun_bank_total_and_accounts():
    text = "總資產現值 0 -\n項目 銀行帳號 幣別 存款餘額(元)\n臺幣活存 0141979***057 TWD 9,213.00\n外幣活存 0358958***513 USD 0.00\n"
    assert _rows(text) == [('E.SUN', '總資產現值', 'TWD', 0.0, 'asset'), ('E.SUN', '臺幣活存 0141979***057', 'TWD', 9213.0, 'asset'), ('E.SUN', '外幣活存 0358958***513', 'USD', 0.0, 'asset')]


def test_dbs_tw_account_summary():
    text = "2026年07月份 綜合對帳單\n帳戶摘要\n類別 主帳號 幣別 帳戶餘額\n外幣活期存款 00228**768* SGD 0.00\n活期儲蓄存款 60765**818* TWD 1,234.50\n"
    assert _rows(text) == [('DBS Taiwan', '外幣活期存款 00228**768*', 'SGD', 0.0, 'asset'), ('DBS Taiwan', '活期儲蓄存款 60765**818*', 'TWD', 1234.5, 'asset')]


def test_fubon_bank_total_and_accounts():
    text = "對帳單期間：2026/07/01~2026/07/31\n資產總計 418.00\n活期存款 北屯 00766168****65 TWD 309.00\n外幣活期 北屯 00766168****65 USD 3.38\n"
    assert _rows(text) == [('Fubon', '資產總計', 'TWD', 418.0, 'asset'), ('Fubon', '活期存款 00766168****65', 'TWD', 309.0, 'asset'), ('Fubon', '外幣活期 00766168****65', 'USD', 3.38, 'asset')]


def test_hsbc_sg_composite_totals():
    text = "Your Portfolio at a Glance SGD Equivalent\nTotalDepositsandInvestments 60,268.56\nTotalBorrowings 1,060.03DR\n01Mar2024 BALANCEBROUGHTFORWARD 204,771.21\n"
    assert _rows(text) == [('HSBC Singapore', 'Deposits & Investments', 'SGD', 60268.56, 'asset'), ('HSBC Singapore', 'Borrowings', 'SGD', 1060.03, 'liability')]


def test_wise_portfolio_value():
    text = "Assets Trade Statement\nPortfolio Value\nValue Date Fund Description Fund ISIN Units Price per unit Amount Currency\n31 Aug 2026 LIONGLOBAL SGD MONEY MARKET A SGD SG9999002760 67.15 1.50 100.83 SGD\n"
    assert _rows(text) == [('Wise', 'LIONGLOBAL SGD MONEY MARKET A SGD', 'SGD', 100.83, 'asset')]


def test_fubon_nano_invest_market_value():
    text = "【奈米投】電子對帳單\n信託財產目錄\n幣別：USD 民國 110年09月30日(報告書結算日)\n計畫名稱 投資金額 參考市值 參考損益 投資報酬率\n無聊投投 300.00 310.53 10.53 3.51%\n合計 300.00 310.53 10.53 3.51%\n"
    assert _rows(text) == [('Fubon 奈米投', '參考市值', 'USD', 310.53, 'asset')]


def test_card_dues_are_liabilities():
    assert _rows("這是您 115年07月 信用卡帳單\n本期應繳總金額： TWD 8,622\n") == [('E.SUN', '信用卡本期應繳', 'TWD', 8622.0, 'liability')]
    assert _rows("本期應繳總額 692元\n帳單年月 信用額度\n") == [('Fubon', '信用卡本期應繳', 'TWD', 692.0, 'liability')]
    assert _rows("HSBC VISA REVOLUTION\nStatementperiod TotalDue MinimumPayment PaymentDueDate\nTotal Due 121.06\n") == [('HSBC Singapore', '信用卡本期應繳', 'SGD', 121.06, 'liability')]


def test_statement_date_comes_from_period_text_or_filename():
    d = lambda text, **info: extract_balances(text, info)[0]['date']
    assert d("對帳單期間：2026/07/01~2026/07/31\n資產總計 418.00\n促銷至2026/12/31\n") == '2026-07-31'
    assert d("From 21 JUL 2026 to 20 AUG 2026\nTotal Due 121.06\n") == '2026-08-20'
    assert d("TotalDepositsandInvestments 1.00\n28Feb2026 BALANCEBROUGHTFORWARD 1\n", filename='01MAR2026.pdf') == '2026-03-01'
    assert d("帳戶總覽 等值新臺幣\n存款 5\n09/07/2026 承前結餘 5\n", filename='09-09-2026.pdf') == '2026-09-09'
    assert d("Richart總資產 $1\n現值參考日:2026/08/31\n") == '2026-08-31'
    assert d("這是您 115年07月 信用卡帳單\n本期應繳總金額： TWD 1\n") == '2026-07-31'
    assert d("Richart總資產 $1\n", filepath='/x/台新銀行_銀行帳戶對帳單_2026-08_123.pdf') == '2026-08-31'
    assert d("Portfolio Value\nGenerated on: 07 Sep 2026\n31 Aug 2026 FUND A SGD SG1 1 1 100.83 SGD\n") == '2026-09-07'


def test_no_balance_in_plain_text():
    assert extract_balances("hello world\n", {}) == []


def test_export_balances_appends_and_dedups(tmp_path):
    b = {'date': '2026-08-31', 'bank': 'Taishin', 'account': 'Richart總資產', 'currency': 'TWD', 'balance': 102039.0, 'kind': 'asset', 'source_file': 'a.pdf'}
    path = export_balances_to_csv([b, dict(b)], output_dir=str(tmp_path))
    export_balances_to_csv([dict(b, balance=1.0, date='2026-09-30')], output_dir=str(tmp_path))
    rows = list(csv.DictReader(open(path, encoding='utf-8-sig')))
    assert [(r['date'], r['balance']) for r in rows] == [('2026-08-31', '102039.00'), ('2026-09-30', '1.00')]
