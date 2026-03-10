#!/usr/bin/env python3
"""
展示 Issue #23 所有增強功能的整合展示。
"""
import os
import sys
import time
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def showcase_all_enhancements():
    """展示所有增強功能。"""
    print("=" * 70)
    print("GMAIL-EXPENSE-PARSER - ISSUE #23 增強功能展示")
    print("=" * 70)
    print("展示項目:")
    print("  1. 結構化日誌記錄系統")
    print("  2. API 重試機制")
    print("  3. 進度指示器")
    print("  4. 配置驗證器")
    print("  5. 優雅降級策略")
    print("=" * 70)
    
    # 1. 結構化日誌記錄
    print("\n🔍 1. 結構化日誌記錄系統")
    print("-" * 40)
    
    from src.utils.logger import setup_logging, get_logger
    
    # 設置日誌記錄（同時輸出到檔案和控制台）
    setup_logging(
        log_level='INFO',
        log_format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        date_format='%H:%M:%S',
        log_dir='logs',
        log_to_file=True,
        log_to_console=True
    )
    
    logger = get_logger(__name__)
    logger.info("應用程式啟動", version="1.0.0", enhancements="Issue#23")
    logger.debug("除錯資訊", component="展示", state="運行中")
    logger.warning("示範警告", items=5, limit=10)
    
    print("✅ 日誌已輸出到控制台和 logs/ 目錄")
    
    # 2. API 重試機制
    print("\n🔄 2. API 重試機制")
    print("-" * 40)
    
    from src.utils.retry import APIRetry, RetryConfig
    
    # 創建自定義重試配置
    custom_config = RetryConfig(
        max_retries=3,
        base_delay=0.5,
        max_delay=5.0,
        exponential_base=2.0,
        jitter=True
    )
    
    retry_handler = APIRetry(config=custom_config)
    
    # 模擬失敗的 API 呼叫
    api_call_count = 0
    
    def simulate_api_call():
        nonlocal api_call_count
        api_call_count += 1
        if api_call_count < 3:
            raise ConnectionError(f"API 連接失敗 (嘗試 {api_call_count})")
        return {"status": "success", "data": "API 回應資料"}
    
    try:
        print("模擬 API 呼叫 (前 2 次會失敗)...")
        result = retry_handler.execute(simulate_api_call)
        print(f"✅ API 呼叫成功: {result}")
        print(f"   總嘗試次數: {api_call_count}")
    except Exception as e:
        print(f"❌ API 呼叫失敗: {e}")
    
    # 3. 進度指示器
    print("\n📊 3. 進度指示器")
    print("-" * 40)
    
    from src.utils.progress import ProgressIndicator, ProgressStyle, track_progress
    
    print("展示不同風格的進度指示器:")
    
    # 風格 1: 進度條
    print("\n  a) 進度條風格:")
    with ProgressIndicator(total=20, description="處理項目", style=ProgressStyle.BAR) as progress:
        for i in range(20):
            time.sleep(0.05)
            progress.update(1)
    
    # 風格 2: 旋轉器
    print("\n  b) 旋轉器風格:")
    with ProgressIndicator(total=15, description="下載檔案", style=ProgressStyle.SPINNER) as progress:
        for i in range(15):
            time.sleep(0.1)
            progress.update(1)
    
    # 風格 3: 追蹤迭代
    print("\n  c) 追蹤迭代:")
    items = ["檔案1.pdf", "檔案2.pdf", "檔案3.pdf", "檔案4.pdf", "檔案5.pdf"]
    processed = []
    
    for item in track_progress(items, description="處理檔案"):
        time.sleep(0.2)
        processed.append(f"已處理: {item}")
    
    print(f"✅ 已處理 {len(processed)} 個檔案")
    
    # 4. 配置驗證器
    print("\n🔧 4. 配置驗證器")
    print("-" * 40)
    
    from src.utils.config_validator import ConfigValidator
    
    validator = ConfigValidator()
    is_valid = validator.validate_all()
    
    if is_valid:
        print("✅ 配置驗證通過: 所有設定正確")
    else:
        print("❌ 配置驗證失敗: 請檢查設定")
    
    # 5. 優雅降級策略
    print("\n🛡️  5. 優雅降級策略")
    print("-" * 40)
    
    print("模擬 LLM 解析失敗時的優雅降級:")
    
    def simulate_llm_parsing(text):
        """模擬 LLM 解析。"""
        # 第一次嘗試: OpenAI API (模擬失敗)
        raise Exception("OpenAI API 暫時不可用")
    
    def heuristic_fallback(text):
        """啟發式回退解析。"""
        # 簡單的啟發式解析
        return {
            "transactions": [{
                "amount": 100.0,
                "currency": "TWD",
                "description": "啟發式解析結果",
                "confidence": 0.7
            }]
        }
    
    receipt_text = "範例收據文字..."
    
    try:
        print("  嘗試主要方法 (LLM 解析)...")
        result = simulate_llm_parsing(receipt_text)
        print("  ✅ 主要方法成功")
    except Exception as e:
        print(f"  ⚠ 主要方法失敗: {e}")
        print("  切換到回退方法 (啟發式解析)...")
        result = heuristic_fallback(receipt_text)
        print(f"  ✅ 回退方法成功: 找到 {len(result['transactions'])} 筆交易")
    
    # 總結
    print("\n" + "=" * 70)
    print("🎉 增強功能展示完成!")
    print("=" * 70)
    print("\n已實現的增強功能:")
    print("  ✓ 結構化日誌記錄 - 用於更好的除錯和監控")
    print("  ✓ API 重試機制 - 提高可靠性和容錯能力")
    print("  ✓ 進度指示器 - 改善使用者體驗")
    print("  ✓ 配置驗證器 - 防止配置錯誤")
    print("  ✓ 優雅降級 - 確保服務持續可用")
    print("\n這些增強功能已整合到:")
    print("  • main_enhanced.py - 增強的主應用程式")
    print("  • main_enhanced_integrated.py - 整合版本")
    print("  • 所有相關模組 (gmail_auth.py, fetch_emails.py, 等)")
    print("\n原始 main.py 保持不變，確保向後兼容性。")
    print("=" * 70)
    
    logger.info("增強功能展示完成", tests_passed=5, status="success")

if __name__ == "__main__":
    showcase_all_enhancements()