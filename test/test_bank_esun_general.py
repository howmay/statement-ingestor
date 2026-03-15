import pytest
from src.parsing.banks.esun import EsunCardParser

def test_esun_no_consumption_data():
    """
    測試玉山帳單顯示「本期無消費資料」的情況。
    """
    text = "玉山銀行信用卡帳單\n（本期無消費資料）\n如有疑問請洽客服"
    parser = EsunCardParser(text)
    result = parser.parse()
    
    assert result.matched
    assert len(result.transactions) == 0
    # 這裡不應拋出錯誤，且應該被視為成功的解析 (matched=True)
