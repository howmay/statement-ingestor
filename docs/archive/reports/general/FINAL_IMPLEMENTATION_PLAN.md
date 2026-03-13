# Issue #27: 最終實施建議與執行方案

## 📋 執行摘要

根據對 gmail-expense-parser 專案的全面審查，現提供以下關鍵發現和建議：

### 當前狀態
- ✅ **所有功能正常運行** - 44 個測試通過
- ✅ **測試覆蓋率 79%** - 接近 80%+ 目標
- ⚠️ **性能瓶頸明確** - PDF 提取需要 2-3 秒 (目標 1-1.5 秒)
- ✅ **架構基礎良好** - 模塊化設計，插件式銀行解析器

### 主要改進建議 (按優先級)
1. **測試覆蓋率提升** (79% → 85%+) - 高優先級，2-3 天
2. **PDF 性能優化** (2-3秒 → 1秒) - 中優先級，3-4 天  
3. **架構微調** (可維護性) - 低優先級，5-7 天
4. **功能擴展** (銀行解析器) - 長期規劃
5. **文檔完善** (全面) - 中優先級，2-3 天

## 🎯 具體實施計劃

### Phase 1: 測試覆蓋率提升 (Week 1)

#### 目標: 79% → 85%+ (當前 79%，目標 85%)

**關鍵發現**: 現有 79% 覆蓋率是高覆蓋率，但仍有低覆蓋模塊需要改進。

#### 任務 1.1: 修復 ocr/hsbc_ocr.py (56% → 80%)
**時間**: 1 天
**理由**: OCR 模塊覆蓋率最低 (56%)，僅 212 行但影響特定功能。

**具體步驟**:
1. 分析 `src/ocr/hsbc_ocr.py` 未覆蓋代碼
2. 創建/擴展 `test/test_ocr.py`:
   ```python
   def test_hsbc_ocr_extract_text():
       """Test HSBC OCR text extraction."""
       # Mock image preprocessing
       # Test regex patterns for different formats
       # Cover edge cases (missing fields, different formats)
   
   def test_hsbc_ocr_no_text_scenarios():
       """Test handling when no text is detected."""
       # Empty image
       # Invalid format
   ```
3. 測試所有正則表達式分支
4. 測試圖像預處理邏輯

**驗收標準**: 覆蓋率 ≥ 80%

#### 任務 1.2: 修復 pdf/pdf_to_text.py (63% → 85%)
**時間**: 1.5 天
**理由**: PDF 提取是核心功能也是性能瓶頸。

**具体步驟**:
1. 分析未覆蓋分支:
   - 所有 extraction fallback 邏輯
   - 錯誤處理路徑
   - 密碼處理分支

2. 創建 `test/test_pdf_to_text_comprehensive.py`:
   ```python
   def test_extraction_method_selection():
       """Test each extraction method separately."""
       # Test pypdfium2 success/failure
       # Test pdftotext success/failure  
       # Test pdfplumber success/failure
       # Test PyPDF2 fallback
   
   def test_encrypted_pdf_handling():
       """Test password-protected PDFs."""
       # Correct password
       # Incorrect password
       # Multiple password attempts
   
   def test_extraction_error_handling():
       """Test error paths for all methods."""
       # File not found
       # Invalid PDF format
       # Corrupted file
   ```

3. 使用 mock 隔離外部依賴

**驗收標準**: 覆蓋率 ≥ 85%

#### 任務 1.3: 修復 auth/gmail_auth.py (77% → 90%)
**時間**: 1 天
**理由**: 認證模块安全重要，需要完整覆蓋。

**實施**:
1. 補充 `test/test_gmail_auth_comprehensive.py`:
   - Token 文件讀取錯誤
   - 手動認證流程
   - OOB flow
   - 端口配置測試
2. 覆蓋所有異常路徑

**驗收標準**: 覆蓋率 ≥ 90%

#### 任務 1.4: 其餘模塊補強
**時間**: 0.5 天
- `config.py` (66% → 80%) - 配置文件驗證測試
- `utils/progress.py` (65% → 75%) - 進度條所有模式

**總計 Week 1 時間**: 4 天 (有緩衝)

---

### Phase 2: 性能優化 (Week 2)

#### 目標: PDF 處理時間減少 50% (2-3秒 → 1-1.5秒)

**關鍵發現**: PDF 提取佔 60% 處理時間，主要問題在於順序嘗試策略。

#### 任務 2.1: 智能 PDF 提取策略 (核心優化)
**時間**: 2 天
**問題**: 當前實現順序嘗試 4 種方法，每種失敗都等待超時。

**解決方案**: 智能選擇 + 並行嘗試

**Implementation Steps**:

Day 1: 文件特徵分析和策略選擇
```python
# src/pdf/pdf_extractor_enhanced.py
import os
from pathlib import Path
from dataclasses import dataclass

@dataclass
class PDFFeatures:
    file_size: int
    page_count: int
    is_encrypted: bool = False
    has_text_layer: bool = False
    is_scanned: bool = False

class SmartPDFExtractor:
    STRATEGY_PDFIUM = "pdfium"
    STRATEGY_PDFTOTEXT = "pdftotext"
    STRATEGY_PDFPLUMBER = "pdfplumber"
    STRATEGY_PYPDF2 = "pypdf2"
    
    def __init__(self, cache_enabled: bool = True):
        self.cache = {} if cache_enabled else None
        
    def analyze_pdf(self, pdf_path: str) -> PDFFeatures:
        """分析 PDF 特徵以選擇最佳提取策略。"""
        features = PDFFeatures(
            file_size=os.path.getsize(pdf_path),
            page_count=self._get_page_count_quick(pdf_path)
        )
        features.is_encrypted = self._check_encryption(pdf_path)
        features.has_text_layer = self._check_text_layer(pdf_path)
        features.is_scanned = self._estimate_if_scanned(pdf_path)
        return features
    
    def select_strategy(self, features: PDFFeatures, password: str = None) -> str:
        """根據特徵選擇提取策略。"""
        # 如果有密碼，所有方法都需要密碼，選擇最快的
        if password:
            return self.STRATEGY_PDFTOTEXT if shutil.which('pdftotext') else self.STRATEGY_PDFIUM
        
        # 小文件 (快速方法)
        if features.file_size < 500_000:  # < 500KB
            return self.STRATEGY_PDFTOTEXT if shutil.which('pdftotext') else self.STRATEGY_PDFIUM
        
        # 掃描文件 (需要高準確率)
        if features.is_scanned or not features.has_text_layer:
            return self.STRATEGY_PDFPLUMBER
        
        # 普通文件
        return self.STRATEGY_PDFIUM
    
    def extract_text(self, pdf_path: str, password: str = None, 
                     timeout: float = 5.0) -> str:
        """智能提取 PDF 文本。"""
        # Check cache first
        if self.cache:
            cache_key = f"{pdf_path}_{hash(open(pdf_path, 'rb').read())}"
            if cache_key in self.cache:
                return self.cache[cache_key]
        
        features = self.analyze_pdf(pdf_path)
        strategy = self.select_strategy(features, password)
        
        try:
            text = self._extract_with_strategy(pdf_path, strategy, password, timeout)
            if text and text.strip():
                if self.cache:
                    self.cache[cache_key] = text
                return text
        except Exception as e:
            logger.warning(f"Strategy {strategy} failed: {e}")
        
        # 如果選擇的策略失敗，嘗試其他策略
        return self._fallback_extraction(pdf_path, password)
    
    def _fallback_extraction(self, pdf_path: str, password: str = None) -> str:
        """嘗試所有備選策略。"""
        strategies = [
            self.STRATEGY_PDFPLUMBER,  # 最準確
            self.STRATEGY_PYPDF2,      # 最後手段
        ]
        
        for strategy in strategies:
            try:
                text = self._extract_with_strategy(pdf_path, strategy, password, timeout=10.0)
                if text and text.strip():
                    return text
            except Exception:
                continue
        
        raise ValueError(f"All extraction strategies failed for {pdf_path}")
```

Day 2: 集成和測試
1. 修改 `src/pdf/pdf_to_text.py` 使用 `SmartPDFExtractor`
2. 保持向後兼容，作為默認實現
3. 添加性能基準測試
4. 舊代碼保留作為備份

**性能預期**:
- 小文件: 0.2-0.4 秒 (原 2-3 秒)
- 普通文件: 0.5-0.8 秒 (原 2 秒)
- 掃描文件: 1.0-1.2 秒 (原 2.5 秒)
**平均提升**: 50-70%

#### 任務 2.2: 并行處理優化
**時間**: 1.5 天
**發現**: 當前已使用 ThreadPoolExecutor，但 worker 數固定為 4。

**改進**:
1. 根据 CPU 核心數自動調整
```python
def calculate_optimal_workers(task_type: str = "io") -> int:
    cpu_count = os.cpu_count() or 4
    
    if task_type == "io":  # PDF extraction, network I/O
        return min(cpu_count * 2, 16)
    elif task_type == "cpu":  # Image processing, chunking
        return min(cpu_count, 8)
    else:  # LLM calls (mostly I/O bound)
        return min(cpu_count * 2, 20)
```

2. 實現工作隊列和批次處理
```python
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Any
import queue

class BatchProcessor:
    def __init__(self, max_workers: int = None, batch_size: int = 10):
        self.max_workers = max_workers or calculate_optimal_workers()
        self.batch_size = batch_size
        
    def process_batch(self, items: List[Any], func: callable) -> List[Any]:
        """分批處理項目，避免記憶體爆"""
        results = []
        
        for i in range(0, len(items), self.batch_size):
            batch = items[i:i + self.batch_size]
            
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                future_to_item = {executor.submit(func, item): item for item in batch}
                
                for future in as_completed(future_to_item):
                    try:
                        result = future.result(timeout=30)
                        results.append(result)
                    except Exception as e:
                        logger.error(f"Batch item failed: {e}")
                        
        return results
```

3. 應用於 PDF 提取和 LLM 解析

**效果**: 提高吞吐量 30-40%

#### 任務 2.3: 緩存機制增強
**時間**: 1 天
**現狀**: 已有基本緩存，可以改進。

**改進**:
1. 實現 LRU 緩存策略
2. 持久化緩存 (磁盤)
3. 緩存粒細化 (避免過時數據)

```python
from functools import lru_cache
from typing import Optional
import hashlib
import pickle
from pathlib import Path

class EnhancedCache:
    def __init__(self, cache_dir: str = ".cache", max_size: int = 1000):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        self.memory_cache = {}
        
    def _get_file_hash(self, filepath: str) -> str:
        """基於文件內容生成哈希."""
        with open(filepath, 'rb') as f:
            return hashlib.md5(f.read()).hexdigest()
    
    def get(self, key: str, file_hash: str = None) -> Optional[Any]:
        """獲取緩存結果."""
        if file_hash:
            full_key = f"{key}_{file_hash}"
        else:
            full_key = key
            
        # 檢查內存緩存
        if full_key in self.memory_cache:
            return self.memory_cache[full_key]
        
        # 檢查磁盤緩存
        cache_file = self.cache_dir / f"{full_key}.cache"
        if cache_file.exists():
            try:
                with open(cache_file, 'rb') as f:
                    result = pickle.load(f)
                    self.memory_cache[full_key] = result  # 更新內存緩存
                    return result
            except Exception:
                return None
        return None
    
    def set(self, key: str, value: Any, file_hash: str = None):
        """設置緩存."""
        if file_hash:
            full_key = f"{key}_{file_hash}"
        else:
            full_key = key
            
        self.memory_cache[full_key] = value
        
        # 保存到磁盤
        cache_file = self.cache_dir / f"{full_key}.cache"
        try:
            with open(cache_file, 'wb') as f:
                pickle.dump(value, f)
        except Exception as e:
            logger.warning(f"Failed to save cache: {e}")
```

**效果**: 相似 PDF 可以命中緩存，減少 20-30% 處理時間。

#### 任務 2.4: LLM 批次處理
**時間**: 1 天
**發現**: 每個 PDF 都獨立調用 LLM，浪費。

**改進**: 批次處理多個 PDF 提取的文本
```python
def parse_receipts_batch(self, extracted_texts: List[Dict], batch_size: int = 5):
    """批次解析多個收據。"""
    batches = [extracted_texts[i:i+batch_size] 
               for i in range(0, len(extracted_texts), batch_size)]
    
    all_receipts = []
    
    for batch in batches:
        combined_text = "\n---\n".join([
            f"Document {i+1}:\n{item['text']}"
            for i, item in enumerate(batch)
        ])
        
        # Single LLM call for multiple receipts
        prompt = f"""
        Parse the following {len(batch)} receipts. Return JSON array:
        
        {combined_text}
        """
        
        response = llm_call(prompt)
        batch_receipts = parse_llm_response(response)
        
        # Attach source info
        for receipt, original in zip(batch_receipts, batch):
            receipt['source_file'] = original['file_info']['filename']
            
        all_receipts.extend(batch_receipts)
    
    return all_receipts
```

**效果**: 減少 LLM 調用 40-60%

**Week 2 總計**: 5.5 天 (有緩衝)

---

### Phase 3: 架構微調 (Week 3)

#### 目標: 提高可測試性和可維護性

#### 任務 3.1: 依賴注入改進
**時間**: 2 天
**分析**: 當前 `app.py` 直接導入模塊，難以測試。

** Proposed Refactoring**:

1. 定義接口:
```python
# src/interfaces.py
from typing import Protocol, List, Dict, Any

class EmailService(Protocol):
    def search_emails(self, query: str, max_results: int = None) -> List[Dict]:
        ...
    def download_attachments(self, email: Dict) -> List[Dict]:
        ...

class PDFExtractor(Protocol):
    def extract_text(self, pdf_path: str, password: str = None) -> str:
        ...

class LLMClient(Protocol):
    def parse_receipt(self, text: str, context: Dict) -> List[Dict]:
        ...

class OutputWriter(Protocol):
    def write_receipts(self, receipts: List[Dict]) -> str:
        ...
```

2. 重構 `app.py`:
```python
class GmailExpenseParserApp:
    def __init__(
        self,
        email_service: EmailService,
        pdf_extractor: PDFExtractor,
        llm_client: LLMClient,
        output_writer: OutputWriter,
        logger: logging.Logger
    ):
        self.email_service = email_service
        self.pdf_extractor = pdf_extractor
        self.llm_client = llm_client
        self.output_writer = output_writer
        self.logger = logger
        
    def run(self, **kwargs):
        # 使用注入的服務
        emails = self.email_service.search_emails(...)
        # ...
```

3. 提供默認實現:
```python
class DefaultGmailService(EmailService):
    def __init__(self, credentials_path: str):
        self.service = get_gmail_service(credentials_path)
        
    def search_emails(self, ...):
        return search_emails(self.service, ...)
```

**優點**:
- 易於單元測試
- 可以輕鬆替換實現
- 分離關注點

#### 任務 3.2: 配置集中化
**時間**: 1.5 天
**問題**: 配置文件、環境變量分散。

**解決方案**: 使用 Pydantic
```python
# src/config_models.py
from pydantic import BaseSettings, Field
from typing import List, Optional

class AppConfig(BaseSettings):
    # Gmail
    gmail_credentials_path: str = Field("config/credentials.json", env="GMAIL_CREDENTIALS")
    gmail_token_path: str = Field("config/token.json", env="GMAIL_TOKEN")
    
    # LLM
    llm_provider: str = Field("local", env="LLM_PROVIDER")
    openai_api_key: Optional[str] = Field(None, env="OPENAI_API_KEY")
    local_base_url: str = Field("http://0.0.0.0:30000/v1", env="LOCAL_BASE_URL")
    
    # Performance
    max_workers: int = Field(4, env="MAX_WORKERS")
    cache_enabled: bool = Field(True, env="CACHE_ENABLED")
    cache_dir: str = Field(".cache", env="CACHE_DIR")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

# 使用
config = AppConfig()
```

#### 任務 3.3: 錯誤處理標準化
**時間**: 1 天
** Proposed**: 定義統一異常層次

```python
# src/exceptions.py
class GmailExpenseParserError(Exception):
    """Base exception."""
    pass

class AuthenticationError(GmailExpenseParserError):
    pass

class PDFExtractionError(GmailExpenseParserError):
    pass

class LLMError(GmailExpenseParserError):
    pass

class ConfigurationError(GmailExpenseParserError):
    pass

# 各模塊使用特定異常
```

**Week 3 總計**: 4.5 天

---

### Phase 4: 功能擴展和文檔 (Week 4)

#### 任務 4.1: 新增銀行解析器 (2 天)
**建議銀行**:
1. 中國信託銀行 (CTBC) - 常見
2. 台新銀行 (Taishin) - 常見

**Implementation Pattern**:
```python
# src/bank_parsers/ctbc.py
class CTBCParser(BankParserBase):
    BANK_NAME = "CTBC"
    PATTERNS = {
        'date': r'交易日期[：:]\s*(\d{4}/\d{2}/\d{2})',
        'amount': r'金額[：:]\s*NT\$?\s*([\d,]+)',
        'description': r'交易說明[：:]\s*([^\n\r]+)',
    }
    
    def can_parse(self, text: str) -> bool:
        return "中國信託" in text or "CTBC" in text
    
    def parse(self, text: str) -> Dict:
        # 提取並返回標準化格式
        pass

# 更新 factory.py
@parser_for("ctbc")
def register_ctbc_parser():
    from src.bank_parsers.ctbc import CTBCParser
    return CTBCParser
```

#### 任務 4.2: 文檔完善 (2 天)
**需要添加的文檔**:

1. **README.md** (更新)
   - 快速開始指南
   - 配置說明
   - 例項

2. **docs/development.md**
   - 開發環境設置
   - 添加新銀行解析器指南
   - 測試指南

3. **docs/api.md** (Sphinx API 文檔)
   ```bash
   cd docs
   sphinx-apidoc -o source/ ../src
   make html
   ```

4. **docs/deployment.md**
   - 生產部署
   - Docker 容器化
   - 監控和日誌

5. **docs/troubleshooting.md**
   - 常見問題
   - 錯誤代碼
   - 調試技巧

#### 任務 4.3: 最終測試和清理 (1 天)
- 回歸測試所有功能
- 性能基準測試
- 代碼質量檢查 (black, isort, flake8, mypy)
- 更新 CHANGELOG.md

---

## 📊 總時間估計

| Phase | 天數 | 工作日 | 總時間 |
|-------|------|--------|--------|
| Phase 1: 測試覆蓋率 | 4 | 5 天 | Week 1 |
| Phase 2: 性能優化 | 5.5 | 7 天 | Week 2 |
| Phase 3: 架構改進 | 4.5 | 6 天 | Week 3 |
| Phase 4: 文檔和擴展 | 5 | 6 天 | Week 4 |
| **Total** | **19** | **24 天** | **4.8 週** |

**注意**: 上述為樂觀估計 (樂觀 + 緩衝)，實際可能需要 5-6 週。

---

## 🎯 關鍵交付物

### Week 1 完成時
- [ ] 所有模塊測試覆蓋率 ≥ 80%
- [ ] 43+ 單元測試 (? -> 60+)
- [ ] 集成測試覆蓋主流程
- [ ] 測試覆蓋率報告: ≥ 85%

### Week 2 完成時
- [ ] PDF 處理時間減少 50%
- [ ] 緩存系統上線
- [ ] LLM 批次處理實現
- [ ] 性能基準測試報告

### Week 3 完成時
- [ ] 依賴注入架構完成
- [ ] 配置系統集中化
- [ ] 錯誤處理標準化
- [ ] 架構文檔更新

### Week 4 完成時
- [ ] 2 個新銀行解析器
- [ ] 完整文檔套件
- [ ] Docker 容器化 (可選)
- [ ] 最終測試通過率 100%
- [ ] 發布 v0.2.0 版本

---

## 🚀 立即行動清單 (下一步)

### 本週作業 (Ethan 開始)
1. **優先執行 Phase 1**:
   - 開始 `test/test_ocr.py` 擴展
   - 開始 `test/test_pdf_to_text_comprehensive.py`
   - 修復現有失敗測試 (test_gmail_auth_comprehensive.py)

2. ** gather 基準性能數據**:
   ```bash
   python -m pytest test/test_pdf_to_text.py::test_extract_performance -v
   # 或創建基準測試腳本
   ```

3. **準備智能 PDF 提取器**:
   - 創建 `src/pdf/pdf_extractor_enhanced.py`
   - 實現特徵分析函數

4. **代碼審查**: Vesper 審查當前架構和計劃

### Vesper 審查和討論
- 審查本實施計劃
- 確認優先級和時間表
- 批准 Phase 1 開始
- 討論資源需求

---

## 🔧 技術細節 - 智能 PDF 提取器 (最關鍵優化)

### 完整 implementation:

```python
# src/pdf/pdf_extractor_enhanced.py
"""
增強的 PDF 文本提取器，使用智能策略選擇和並行處理。
"""

import os
import shutil
import logging
import hashlib
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

logger = logging.getLogger(__name__)

@dataclass
class PDFFeatures:
    """PDF 文件特徵."""
    file_size: int
    page_count: int
    is_encrypted: bool = False
    has_text_layer: bool = False
    is_scanned: bool = False
    file_hash: str = ""
    
    @classmethod
    def from_file(cls, pdf_path: str) -> 'PDFFeatures':
        """從文件分析特徵."""
        features = cls(
            file_size=os.path.getsize(pdf_path),
            page_count=0,
            file_hash=cls._quick_hash(pdf_path)
        )
        
        # 快速獲取頁數
        features.page_count = cls._get_page_count_fast(pdf_path)
        
        # 檢查加密和文本層 (可能需要完整讀取)
        features.is_encrypted = cls._check_encryption(pdf_path)
        if not features.is_encrypted:
            features.has_text_layer = cls._check_text_layer(pdf_path)
            features.is_scanned = not features.has_text_layer
            
        return features
    
    @staticmethod
    def _quick_hash(pdf_path: str) -> str:
        """快速計算文件哈希 (前 1MB + 尾部 1KB)."""
        file_size = os.path.getsize(pdf_path)
        hasher = hashlib.md5()
        
        with open(pdf_path, 'rb') as f:
            # 讀取開頭
            hasher.update(f.read(min(1024*1024, file_size)))
            
            if file_size > 1024*1024 + 1024:
                # 讀取結尾
                f.seek(-1024, os.SEEK_END)
                hasher.update(f.read())
                
        return hasher.hexdigest()
    
    @staticmethod
    def _get_page_count_fast(pdf_path: str) -> int:
        """快速獲取頁數 (使用 pdfinfo 或 pypdfium2)."""
        # 嘗試 pdfinfo (poppler)
        if shutil.which('pdfinfo'):
            try:
                import subprocess
                result = subprocess.run(
                    ['pdfinfo', pdf_path],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                for line in result.stdout.split('\n'):
                    if line.startswith('Pages:'):
                        return int(line.split(':')[1].strip())
            except Exception:
                pass
        
        # 使用 pypdfium2 快速計數
        try:
            import pypdfium2 as pdfium
            pdf = pdfium.PdfDocument(pdf_path)
            count = len(pdf)
            pdf.close()
            return count
        except Exception:
            return 0
    
    @staticmethod
    def _check_encryption(pdf_path: str) -> bool:
        """檢查 PDF 是否加密."""
        try:
            import pypdfium2 as pdfium
            pdf = pdfium.PdfDocument(pdf_path)
            is_encrypted = pdf.is_encrypted
            pdf.close()
            return is_encrypted
        except Exception:
            return False
    
    @staticmethod
    def _check_text_layer(pdf_path: str) -> bool:
        """檢查 PDF 是否有文本層 (非掃描)."""
        try:
            import pypdfium2 as pdfium
            pdf = pdfium.PdfDocument(pdf_path)
            
            if len(pdf) == 0:
                pdf.close()
                return False
                
            # 檢查第一頁是否有文本
            page = pdf[0]
            textpage = page.get_textpage()
            text = textpage.get_text_range()
            textpage.close()
            page.close()
            pdf.close()
            
            return bool(text and text.strip())
        except Exception:
            return False

class SmartPDFExtractor:
    """智能 PDF 提取器."""
    
    STRATEGY_PDFIUM = "pdfium"
    STRATEGY_PDFTOTEXT = "pdftotext"
    STRATEGY_PDFPLUMBER = "pdfplumber"
    STRATEGY_PYPDF2 = "pypdf2"
    
    def __init__(self, cache_enabled: bool = True, cache_dir: str = ".cache"):
        self.cache_enabled = cache_enabled
        self.cache_dir = Path(cache_dir)
        if cache_enabled:
            self.cache_dir.mkdir(exist_ok=True)
            self.memory_cache = {}
            
    def extract_text(self, pdf_path: str, password: str = None, 
                     timeout: float = 8.0) -> str:
        """提取 PDF 文本 (智能策略)."""
        
        # 檢查緩存
        if self.cache_enabled:
            cached = self._get_from_cache(pdf_path, password)
            if cached:
                logger.debug(f"Cache hit for {pdf_path}")
                return cached
        
        # 分析文件特徵
        features = PDFFeatures.from_file(pdf_path)
        
        # 選擇策略
        strategy = self._select_strategy(features, password)
        logger.info(f"Selected strategy '{strategy}' for {pdf_path} "
                   f"(size: {features.file_size}B, pages: {features.page_count})")
        
        start_time = time.time()
        text = self._extract_with_strategy(pdf_path, strategy, password, timeout)
        elapsed = time.time() - start_time
        
        logger.info(f"Extraction completed in {elapsed:.2f}s using {strategy}")
        
        if text and text.strip():
            if self.cache_enabled:
                self._save_to_cache(pdf_path, password, text)
            return text
            
        # 如果選擇的策略失敗，嘗試備選
        logger.warning(f"Strategy {strategy} failed, trying fallback...")
        return self._fallback_extraction(pdf_path, password)
    
    def _select_strategy(self, features: PDFFeatures, password: str = None) -> str:
        """選擇最佳提取策略."""
        
        # 如果有密碼，使用最快的方法
        if password:
            return self.STRATEGY_PDFTOTEXT if shutil.which('pdftotext') else self.STRATEGY_PDFIUM
        
        # 檢查是否有 pdftotext (最快)
        if shutil.which('pdftotext'):
            # 小文件適合 pdftotext
            if features.file_size < 2_000_000:
                return self.STRATEGY_PDFTOTEXT
        
        # 檢查是否有 pypdfium2 (第二快)
        try:
            import pypdfium2
            # 大文件或可能有複雜佈局時使用 pdfium
            if features.file_size > 5_000_000 or features.page_count > 50:
                return self.STRATEGY_PDFIUM
            # 掃描文件使用 pdfplumber
            if features.is_scanned:
                return self.STRATEGY_PDFPLUMBER
            # 默認使用 pdfium
            return self.STRATEGY_PDFIUM
        except ImportError:
            pass
        
        # 最後檢查 pdfplumber
        try:
            import pdfplumber
            return self.STRATEGY_PDFPLUMBER
        except ImportError:
            pass
        
        # 最後手段 PyPDF2
        return self.STRATEGY_PYPDF2
    
    def _extract_with_strategy(self, pdf_path: str, strategy: str,
                               password: str, timeout: float) -> str:
        """使用指定策略提取文本."""
        
        if strategy == self.STRATEGY_PDFTOTEXT:
            return self._extract_with_pdftotext(pdf_path, password)
        elif strategy == self.STRATEGY_PDFIUM:
            return self._extract_with_pdfium(pdf_path, password)
        elif strategy == self.STRATEGY_PDFPLUMBER:
            return self._extract_with_pdfplumber(pdf_path, password)
        elif strategy == self.STRATEGY_PYPDF2:
            return self._extract_with_pypdf2(pdf_path, password)
        else:
            raise ValueError(f"Unknown strategy: {strategy}")
    
    # ... 保留原有的 _extract_with_* 方法 ...
    
    def _fallback_extraction(self, pdf_path: str, password: str = None) -> str:
        """嘗試所有備選策略."""
        strategies = [
            self.STRATEGY_PDFPLUMBER,  # 最準確
            self.STRATEGY_PDFIUM,
            self.STRATEGY_PDFTOTEXT,
            self.STRATEGY_PYPDF2,
        ]
        
        for strategy in strategies:
            try:
                logger.info(f"Trying fallback strategy: {strategy}")
                text = self._extract_with_strategy(pdf_path, strategy, password, timeout=15.0)
                if text and text.strip():
                    logger.info(f"Fallback strategy {strategy} succeeded")
                    return text
            except Exception as e:
                logger.warning(f"Fallback strategy {strategy} failed: {e}")
                continue
        
        raise ValueError(f"All extraction strategies failed for {pdf_path}")
    
    def _get_cache_key(self, pdf_path: str, password: str) -> str:
        """生成緩存鍵."""
        features = PDFFeatures.from_file(pdf_path)
        key_base = f"{features.file_hash}_{password or 'nopw'}"
        return hashlib.md5(key_base.encode()).hexdigest()[:16]
    
    def _get_from_cache(self, pdf_path: str, password: str) -> Optional[str]:
        """從緩存獲取."""
        key = self._get_cache_key(pdf_path, password)
        
        # 檢查內存緩存
        if key in self.memory_cache:
            return self.memory_cache[key]
        
        # 檢查磁盤緩存
        cache_file = self.cache_dir / f"{key}.txt"
        if cache_file.exists():
            try:
                return cache_file.read_text(encoding='utf-8')
            except Exception:
                return None
        return None
    
    def _save_to_cache(self, pdf_path: str, password: str, text: str):
        """保存到緩存."""
        key = self._get_cache_key(pdf_path, password)
        self.memory_cache[key] = text
        
        cache_file = self.cache_dir / f"{key}.txt"
        try:
            cache_file.write_text(text, encoding='utf-8')
        except Exception as e:
            logger.warning(f"Failed to save cache: {e}")

# 便利函數
def extract_text_from_pdf_enhanced(pdf_path: str, password: str = None, 
                                   cache_enabled: bool = True) -> str:
    """增強的 PDF 文本提取函數."""
    extractor = SmartPDFExtractor(cache_enabled=cache_enabled)
    return extractor.extract_text(pdf_path, password)
```

---

## 📈 追蹤和衡量

### 關鍵性能指標 (KPI)

```python
# metrics/performance_tracker.py
class PerformanceTracker:
    def __init__(self):
        self.metrics = {
            'pdf_extraction_times': [],
            'llm_call_times': [],
            'total_processing_times': [],
            'cache_hit_rates': [],
        }
    
    def record_pdf_time(self, filepath: str, duration: float):
        self.metrics['pdf_extraction_times'].append({
            'file': Path(filepath).name,
            'size': os.path.getsize(filepath),
            'duration': duration,
            'timestamp': time.time()
        })
    
    def get_average_pdf_time(self) -> float:
        times = [m['duration'] for m in self.metrics['pdf_extraction_times'][-100:]]
        return sum(times) / len(times) if times else 0
    
    def generate_report(self) -> str:
        """生成性能報告."""
        avg_pdf = self.get_average_pdf_time()
        return f"""
        Performance Report:
        - Avg PDF extraction: {avg_pdf:.2f}s
        - Total processed: {len(self.metrics['pdf_extraction_times'])}
        - Cache hit rate: {self.get_cache_hit_rate():.1%}
        """
```

### 測試覆蓋率監控

```bash
# 每日自動化 (在 GitHub Actions 或其他 CI)
pytest --cov=src --cov-report=html --cov-report=term
python -c "
import json
with open('coverage.json') as f:
    data = json.load(f)
    covered = data['totals']['percent_covered']
    print(f'Current coverage: {covered}%')
    if covered < 85:
        print('⚠ Coverage below target!')
"
```

---

## ⚠️ 風險和緩解

| 風險 | 影響 | 概率 | 緩解措施 |
|------|------|------|----------|
| 智能策略選擇錯誤 | 性能降低 | 中 | 實現 fallback 機制，記錄策略選擇日誌 |
| 緩存一致性问题 | 錯誤結果 | 低 | 使用文件哈希作為緩存鍵，定期清理 |
| 並發競爭條件 | 數據損壞 | 低 | 使用線程安全數據結構，充分測試 |
| LLM API 變化 | 功能失效 | 中 | 抽象 API 接口，easy to switch providers |
| 新銀行解析器不準確 | 數據錯誤 | 中 | 充分的回歸測試，手動驗證樣本 |

---

## 💡 建議的開發工作流

1. **分支策略**:
   ```
   main (production-ready)
   ├── develop (integration)
   │   ├── feature/performance-optimization
   │   ├── feature/new-bank-parsers
   │   ├── feature/testing-improvements
   │   └── docs/*
   ```

2. **提交規範**: Conventional Commits
   ```
   feat: add intelligent PDF extractor
   fix: resolve OCR parsing bug
   test: improve ocr module coverage
   docs: update API documentation
   refactor: dependency injection for app
   ```

3. **代碼審查**: 所有 PR 需要 Vesper 審查

4. **版本管理**: 遵循 SemVer (v0.2.0)

---

## 📞 溝通檢查點

### 每日 (快速更新)
-  yesterday's progress
- today's plan
- blockers/questions

### 每週 (正式報告)
- 覆蓋率報告
- 性能基準測試
- 本周完成的工作
- 下周計劃

### 里程碑達成
- Week 1: 測試覆蓋率 ≥ 85%
- Week 2: PDF 性能提升 ≥ 50%
- Week 3: 架構改進完成
- Week 4: 所有功能完成，準備發布

---

## 🔚 總結

這是一個有明確目標和可衡量結果的計劃。關鍵是**先完成 Phase 1 (測試)**，然後專注於 **Phase 2 (PDF 性能)**，因為这两個有最高的 ROI。

**優先執行順序**:
1. Week 1: 測試覆蓋率提升 (高優先級，4天)
2. Week 2: 智能 PDF 提取器 (核心優化，2天) + 其餘性能優化
3. Week 3: 架構改進 (4.5天)
4. Week 4: 文檔和新功能 (5天)

建議立即開始 Phase 1 的任務 1.2（pdf_to_text 測試），因為這是瓶頸也是優化的基礎。

---