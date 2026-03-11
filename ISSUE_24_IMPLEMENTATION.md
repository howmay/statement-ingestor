# Issue #24 實施方案

## 實施步驟

### 步驟 1: 增強現有 parse_receipt.py 文件

將在現有文件中添加以下增強功能：

1. **增強 JSON 修復函數** (`_fix_truncated_json_enhanced`)
2. **智能文本分塊函數** (`_chunk_text_by_transactions`)
3. **自適應解析策略** (`_parse_with_adaptive_strategy`)
4. **改進的重試邏輯**

### 步驟 2: 更新 retry.py 以支持多階段重試

### 步驟 3: 創建測試文件驗證功能

### 步驟 4: 更新文檔和配置

## 具體實施

### 1. 修改 parse_receipt.py

將在現有文件中添加以下函數：

```python
def _fix_truncated_json_enhanced(json_str: str, context: Dict[str, Any] = None) -> Optional[str]:
    """增強版 JSON 修復函數"""

def _chunk_text_by_transactions(text: str, max_chunk_size: int = 3500) -> List[Tuple[str, List[int]]]:
    """基於交易邊界的智能分塊"""

def _should_enable_chunking(text: str, source_info: Dict[str, Any]) -> bool:
    """判斷是否需要啟用分塊"""

def _parse_with_adaptive_strategy(text: str, source_info: Dict[str, Any]) -> List[Dict[str, Any]]:
    """自適應解析策略"""
```

### 2. 更新 _parse_with_openai_enhanced 函數

修改現有函數以使用新的自適應策略：

```python
@retry_openai
def _parse_with_openai_enhanced(text: str, source_info: Dict[str, Any]) -> List[Dict[str, Any]]:
    """增強版 OpenAI 解析，整合自適應策略"""
    # 使用新的自適應策略
    return _parse_with_adaptive_strategy(text, source_info)
```

### 3. 創建測試文件

創建 `test_issue_24_large_transactions.py` 測試：

1. 模擬大型 HSBC 對帳單
2. 測試 JSON 修復功能
3. 測試文本分塊算法
4. 測試完整解析流程

### 4. 更新配置

在 `.env.example` 中添加新配置選項：

```
# Issue #24: Large transaction handling
ENABLE_ADAPTIVE_CHUNKING=true
MAX_CHUNK_SIZE=3500
MIN_TRANSACTIONS_PER_CHUNK=5
```

## 實施時間表

1. **Day 1**: 實現核心增強函數
2. **Day 2**: 更新現有函數和整合
3. **Day 3**: 創建測試和驗證
4. **Day 4**: 更新文檔和部署

## 風險緩解

1. **分塊過度**: 添加最小交易數限制
2. **API 成本增加**: 僅在必要時啟用分塊
3. **解析一致性**: 添加結果合併和去重邏輯
4. **性能影響**: 添加性能監控和優化選項

---

## 實作進度（2026-03-11）

已完成：
- `parse_receipt.py`
  - 補上 `adaptive strategy` 路徑：`_parse_with_adaptive_strategy()`
  - 分塊決策改為讀取環境設定：`ENABLE_ADAPTIVE_CHUNKING`、`MAX_CHUNK_SIZE`、`MIN_TRANSACTIONS_PER_CHUNK`、`FORCE_CHUNKING_TEXT_LENGTH`
  - 保留向後相容（未設定時使用預設值）
- `retry_enhanced.py`
  - 修正多階段重試 context 注入邏輯，避免對不接受 `context` 參數的函式重試時拋出 `unexpected keyword argument`
  - JSON truncation 重試策略（chunk/reduce_text）可穩定作用於支援 context 的外層函式
- 測試
  - `test_issue_24_large_transactions.py` 修正 strict bank parser 干擾（mock LLM 測試改為 `STRICT_BANK_PARSER=false`）
  - `test_issue_24_comprehensive.py` 全綠

驗證命令：
- `python test_issue_24_large_transactions.py`
- `python test_issue_24_comprehensive.py`
- `python test_bank_parsers.py`