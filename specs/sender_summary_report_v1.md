# Gmail Expense Parser - 按 Sender/銀行分類的解析摘要報告 (PRD v1.0)

## 文件資訊
- **專案名稱**: Gmail Expense Parser
- **功能名稱**: Sender Summary Report (按 Sender/銀行分類的解析摘要報告)
- **版本**: v1.0
- **作者**: Julian (PM Agent)
- **日期**: 2026-03-16
- **目標讀者**: Developer (Ethan)
- **狀態**: 待實作

## 1. 需求概述

### 1.1 背景
目前 `app.py` 的 `run()` 方法在執行結尾僅顯示總體統計數字（emails_found, pdfs_downloaded, receipts_parsed, errors, warnings），無法直觀看出各銀行/發送者的 PDF 解析狀況。

### 1.2 目標
在 Gmail 爬蟲執行結尾，打印一份 **按 sender/銀行分類的解析摘要報告**，提供以下資訊：
1. 按銀行/發送者分類的處理結果
2. 每個分類下的檔案清單與狀態
3. 成功與失敗的詳細計數
4. 失敗原因標註

### 1.3 預期輸出格式
```
============================================================
📊 PDF 解析摘要報告
============================================================

🏦 HSBC_TW (cards.estatements.hsbc.com.tw)
   檔名:
   - 202412_Statement.pdf ✅
   - 202411_Statement.pdf ✅
   - 202410_Statement.pdf ❌ (解析失敗)
   成功: 2 筆 | 失敗: 1 筆

🏦 Fubon_TW (bhu.taipeifubon.com.tw)
   檔名:
   - 電子帳單_Dec2024.pdf ✅
   成功: 1 筆 | 失敗: 0 筆

🏦 EsunBank (service@esunbank.com)
   檔名:
   - estatement_202412.pdf ❌ (文字提取失敗)
   成功: 0 筆 | 失敗: 1 筆

============================================================
總計: 成功 3 筆 | 失敗 2 筆
============================================================
```

## 2. 現有架構分析

### 2.1 核心流程 (`src/app.py`)
```python
class GmailExpenseParserApp:
    def run(self):
        self.validate_configuration()
        self.authenticate()
        self.fetch_emails()
        self.download_attachments()      # 下載 PDF
        self.extract_texts()             # 提取文字
        self.parse_receipts()            # 解析收據
        self.export_results()            # 匯出結果
```

### 2.2 關鍵資料結構
- `self.downloaded_files`: List[Dict] - 下載的檔案資訊
- `self.extracted_texts`: List[Dict] - 提取的文字結果
- `self.parsed_receipts`: List[Dict] - 解析的收據結果
- `self.stats`: Dict - 統計數字

### 2.3 Sender Tag 邏輯 (`src/fetch/download_pdfs.py`)
```python
def extract_sender_tag(sender: str) -> str:
    # 從 sender email 提取有意義的標籤
    # 例如: "cards.estatements.hsbc.com.tw" -> "hsbc_tw_cards"
    # 支援銀行域名模式匹配
```

## 3. 修改檔案與具體改動

### 3.1 主要修改檔案
| 檔案 | 修改內容 | 影響範圍 |
|------|---------|---------|
| `src/app.py` | 新增資料結構、追蹤方法、報告方法 | 核心 |
| `src/fetch/download_pdfs.py` | 無需修改 | - |

### 3.2 具體改動詳解

#### 3.2.1 新增資料結構 (`src/app.py`)
在 `GmailExpenseParserApp.__init__()` 中新增：

```python
# Per-sender tracking for summary report
# Key: sender_tag (e.g., 'hsbc_tw_cards', 'fubon_tw_bhu')
# Value: {
#   'sender_display': str,        # 原始 sender (e.g., '"台北富邦銀行" <service@bhu...>')
#   'sender_tag': str,            # sender_tag from extract_sender_tag()
#   'domain': str,                # email domain (提取自 sender)
#   'files': [
#     {
#       'original_filename': str,  # email 上的原始檔名
#       'status': 'pending' | 'success' | 'extract_fail' | 'parse_fail' | 'download_fail',
#       'error': str | None,       # 失敗原因（如有）
#       'filepath': str | None     # 下載後的檔案路徑（如有）
#     }
#   ]
# }
self.sender_summary: Dict[str, Dict] = {}
```

#### 3.2.2 新增追蹤方法 (`src/app.py`)
```python
def _track_file(self, file_info: Dict, status: str, error: str = None):
    """Track file processing status for summary report."""
    sender_tag = file_info.get('sender_tag', 'unknown')
    sender = file_info.get('sender', 'Unknown')
    original_filename = file_info.get('filename', 'unknown.pdf')
    filepath = file_info.get('filepath')
    
    # 初始化 sender 分類
    if sender_tag not in self.sender_summary:
        domain = sender.split('@')[1] if '@' in sender else 'unknown'
        self.sender_summary[sender_tag] = {
            'sender_display': sender,
            'sender_tag': sender_tag,
            'domain': domain,
            'files': []
        }
    
    # 檢查是否已追蹤此檔案（避免重複）
    existing_files = self.sender_summary[sender_tag]['files']
    for f in existing_files:
        if f['original_filename'] == original_filename:
            # 更新現有檔案的狀態
            f['status'] = status
            f['error'] = error
            if filepath:
                f['filepath'] = filepath
            return
    
    # 新增檔案追蹤
    self.sender_summary[sender_tag]['files'].append({
        'original_filename': original_filename,
        'status': status,
        'error': error,
        'filepath': filepath
    })
```

#### 3.2.3 修改 `download_attachments()` 方法
在 `download_attachments()` 中，對每個下載結果進行追蹤：

```python
def download_attachments(self) -> bool:
    # ... 現有程式碼 ...
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(batch_download_pdfs, self.service, [email]): email for email in self.emails}
        
        for future in as_completed(futures):
            try:
                downloaded_files = future.result()
                all_downloaded_files.extend(downloaded_files)
                
                # 追蹤成功下載的檔案
                for file_info in downloaded_files:
                    self._track_file(file_info, 'pending')
                    
            except Exception as e:
                email = futures[future]
                self.log('error', f"✗ Failed to download attachments for email {email.get('id', 'unknown')}: {e}")
                self.stats['errors'] += 1
                
                # 追蹤下載失敗的檔案（從 email metadata 構造最小的 file_info）
                sender = email.get('sender', 'Unknown')
                sender_tag = extract_sender_tag(sender)  # 需要 import
                subject = email.get('subject', 'No Subject')
                
                # 從 subject 推斷可能的檔名（如果無法取得原始附件檔名）
                # 策略：使用 subject 的前 30 個字元，移除特殊字元，加上 .pdf 副檔名
                inferred_filename = self._infer_filename_from_subject(subject)
                
                # 建立失敗的 file_info 用於追蹤
                failed_file_info = {
                    'sender': sender,
                    'sender_tag': sender_tag,
                    'filename': inferred_filename,  # 推斷的檔名，非 'multiple_attachments'
                    'subject': subject,
                    'message_id': email.get('id', 'unknown'),
                    # 注意：沒有 filepath，因為下載失敗
                    # 注意：原始附件檔名未知，標註為推斷的檔名
                }
                self._track_file(failed_file_info, 'download_fail', str(e))
    
    # ... 現有程式碼 ...
```

#### 3.2.4 修改 `extract_texts()` 方法
在 `extract_texts()` 中，更新檔案狀態：

```python
def extract_texts(self) -> bool:
    # ... 現有程式碼 ...
    
    def process_file(file_info):
        try:
            # ... 現有程式碼 ...
            
            if text:
                # 更新狀態為成功
                self._track_file(file_info, 'success')
                return {
                    'text': text,
                    'file_info': file_info
                }
            else:
                # 更新狀態為提取失敗
                self._track_file(file_info, 'extract_fail', 'No text extracted')
                return {'warning': f"No text extracted from {file_info['filepath']}"}
        except Exception as e:
            # 更新狀態為提取失敗
            self._track_file(file_info, 'extract_fail', str(e))
            return {'error': f"Failed to extract text from {file_info['filepath']}: {e}"}
    
    # ... 現有程式碼 ...
```

#### 3.2.5 修改 `parse_receipts()` 方法
在 `parse_receipts()` 中，更新檔案狀態：

```python
def parse_receipts(self) -> bool:
    # ... 現有程式碼 ...
    
    for item in self.extracted_texts:
        text = item['text']
        file_info = item['file_info']
        
        try:
            receipts = parse_receipt_text(text)
            
            if receipts:
                # 更新狀態為成功（如果之前是 pending）
                self._track_file(file_info, 'success')
                # ... 現有程式碼 ...
            else:
                # 更新狀態為解析失敗
                self._track_file(file_info, 'parse_fail', 'No receipts parsed')
                # ... 現有程式碼 ...
                
        except ReceiptParsingError as e:
            # 更新狀態為解析失敗
            self._track_file(file_info, 'parse_fail', str(e))
            # ... 現有程式碼 ...
        except Exception as e:
            # 更新狀態為解析失敗
            self._track_file(file_info, 'parse_fail', str(e))
            # ... 現有程式碼 ...
```

#### 3.2.6 新增 `print_summary()` 方法
```python
def print_summary(self):
    """Print per-sender summary report at the end of execution."""
    if not self.sender_summary:
        self.log('info', "沒有需要報告的 PDF 檔案。")
        return
    
    lines = []
    lines.append("=" * 60)
    lines.append("📊 PDF 解析摘要報告")
    lines.append("=" * 60)
    lines.append("")
    
    total_success = 0
    total_fail = 0
    
    # 按 sender_tag 字母排序
    for sender_tag, info in sorted(self.sender_summary.items()):
        domain = info['domain']
        # sender_tag 大小寫處理規則：
        # - 內部 key：保持 lowercase（由 extract_sender_tag() 產生）
        # - 顯示時：轉為大寫，視覺上更清晰
        display_tag = sender_tag.upper()
        lines.append(f"🏦 {display_tag} ({domain})")
        lines.append("   檔名:")
        
        success_count = 0
        fail_count = 0
        
        for f in info['files']:
            original_name = f['original_filename']
            status = f['status']
            
            if status == 'success':
                lines.append(f"   - {original_name} ✅")
                success_count += 1
            else:
                # 狀態對應的中文標籤
                error_label = {
                    'extract_fail': '文字提取失敗',
                    'parse_fail': '解析失敗',
                    'download_fail': '下載失敗',
                    'pending': '未處理',
                }.get(status, status)
                
                # 優先使用具體錯誤訊息
                error_detail = f['error'] or error_label
                lines.append(f"   - {original_name} ❌ ({error_detail})")
                fail_count += 1
        
        lines.append(f"   成功: {success_count} 筆 | 失敗: {fail_count} 筆")
        lines.append("")
        
        total_success += success_count
        total_fail += fail_count
    
    lines.append("=" * 60)
    lines.append(f"總計: 成功 {total_success} 筆 | 失敗 {total_fail} 筆")
    lines.append("=" * 60)
    
    report = "\n".join(lines)
    self.log('info', f"\n{report}")
    # 同時輸出到 console 以確保可見性
    print(report)
```

#### 3.2.7 在 `run()` 中呼叫 `print_summary()`
在 `run()` 方法的 `finally` 區塊中，現有統計摘要之後加入：

```python
def run(self, max_results: int = 10) -> Dict[str, Any]:
    # ... 現有程式碼 ...
    
    finally:
        end_time = datetime.now()
        duration = end_time - self.start_time
        
        self.log('info', "=" * 60)
        self.log('info', f"Run completed in {duration.total_seconds():.2f} seconds")
        self.log('info', f"Status: {'SUCCESS' if success else 'FAILED'}")
        self.log('info', f"Summary: {self.stats['emails_found']} emails, "
                         f"{self.stats['pdfs_downloaded']} PDFs, "
                         f"{self.stats['receipts_parsed']} receipts")
        self.log('info', f"Errors: {self.stats['errors']}, Warnings: {self.stats['warnings']}")
        self.log('info', "=" * 60)
        
        # 新增：打印按 sender 分類的摘要報告
        self.print_summary()
        
    return self.stats
```

## 4. 資料結構設計

### 4.1 狀態追蹤流程與狀態轉換圖

#### 狀態轉換圖（文字表示）
```
下載階段 (download_attachments)
  ├── 成功下載 → status: 'pending'
  └── 下載失敗 → status: 'download_fail'

提取階段 (extract_texts)
  ├── 成功提取 → status: 'success' (從 pending 轉換)
  └── 提取失敗 → status: 'extract_fail' (從 pending 轉換)

解析階段 (parse_receipts)
  ├── 成功解析 → status: 'success' (保持)
  └── 解析失敗 → status: 'parse_fail' (從 success 覆蓋)
```

#### 詳細狀態轉換規則
1. **download 成功** → 登記為 `pending`（等待後續處理）
2. **download 失敗** → 直接設為 `download_fail`（不進入後續階段）
3. **pending → success**：文字提取成功且 parse 成功
4. **pending → extract_fail**：文字提取失敗，不進入 parse 階段
5. **success → parse_fail**：文字提取成功但 parse 失敗，覆蓋狀態
6. **狀態不可逆轉**：一旦進入失敗狀態（download_fail, extract_fail, parse_fail），不再改變

### 4.2 狀態定義
| 狀態值 | 說明 | 觸發時機 | 可從何狀態轉換 |
|--------|------|---------|---------------|
| `pending` | 已下載，待處理 | 下載成功後 | 無（初始狀態） |
| `success` | 處理成功 | 提取成功且解析成功 | `pending` |
| `extract_fail` | 文字提取失敗 | `extract_texts()` 失敗 | `pending` |
| `parse_fail` | 收據解析失敗 | `parse_receipts()` 失敗 | `success` |
| `download_fail` | 下載失敗 | `download_attachments()` 失敗 | 無（直接設定） |

#### 狀態轉換注意事項
1. **`pending` 是中間狀態**：所有成功下載的檔案都從 `pending` 開始
2. **`download_fail` 是終端狀態**：下載失敗的檔案不進入後續處理流程
3. **`extract_fail` 與 `parse_fail` 的區別**：
   - `extract_fail`：文字提取階段失敗，未進入 parse 階段
   - `parse_fail`：文字提取成功，但 parse 階段失敗
4. **狀態覆蓋規則**：`parse_fail` 可以覆蓋 `success` 狀態，表示「提取成功但解析失敗」

## 5. 邊界情況處理

### 5.1 沒有下載任何 PDF
- 情況：`self.sender_summary` 為空
- 處理：`print_summary()` 打印 "沒有需要報告的 PDF 檔案。"

### 5.2 同一 sender_tag 有多封 email
- 情況：同一銀行發送多封郵件
- 處理：合併在同一分類下，檔名各自列出

### 5.3 download 失敗的檔案追蹤
- 情況：`batch_download_pdfs` 拋出例外，無法取得原始附件檔名
- 處理：從 email metadata 構造最小的 `file_info` 用於追蹤
- 具體實作：

```python
def _infer_filename_from_subject(self, subject: str) -> str:
    """
    從 email subject 推斷可能的 PDF 檔名。
    用於 download 失敗時，原始附件檔名無法取得的情況。
    """
    # 1. 移除特殊字元，保留字母、數字、空格、底線、連字號
    import re
    cleaned = re.sub(r'[^\w\s\-_]', '', subject)
    
    # 2. 移除多餘空格，用底線連接
    words = cleaned.strip().split()
    if len(words) > 5:
        # 取前幾個關鍵字
        inferred = '_'.join(words[:3])
    else:
        inferred = '_'.join(words) if words else 'unknown'
    
    # 3. 確保有內容，加上 .pdf 副檔名
    if not inferred or inferred == 'unknown':
        inferred = 'unknown_attachment'
    
    return f"{inferred}.pdf"
```

#### download 失敗時的 file_info 構造規則：
1. **sender**：從 email metadata 取得 `email.get('sender', 'Unknown')`
2. **sender_tag**：使用 `extract_sender_tag(sender)` 生成
3. **filename**：
   - 優先使用原始附件檔名（如果下載前可知）
   - 如果無法取得，使用 `_infer_filename_from_subject(subject)` 推斷
   - 避免使用通用名稱如 `'multiple_attachments'`，應提供有辨識度的名稱
4. **subject**：保留原始 subject 供參考
5. **message_id**：保留 email ID 供除錯
6. **filepath**：設為 `None`（因為下載失敗）
7. **status**：設為 `'download_fail'`
8. **error**：記錄例外訊息 `str(e)`

### 5.4 sender_tag 為 unknown
- 情況：`extract_sender_tag()` 返回 'unknown'
- 處理：歸類在 `unknown` 分類下，顯示原始 sender

### 5.5 檔案重複追蹤
- 情況：同一檔案在不同階段被多次追蹤
- 處理：`_track_file()` 檢查 `original_filename` 是否已存在，避免重複

### 5.7 sender_tag 大小寫一致性規則
- **內部 key 規則**：所有 `sender_tag` 在 `self.sender_summary` 字典中保持 **lowercase**
  - 來源：`extract_sender_tag()` 函數應返回 lowercase 字串
  - 目的：確保字典查找時的大小寫一致性
- **顯示規則**：在 `print_summary()` 報告中顯示時轉為 **大寫**
  - 方法：使用 `display_tag = sender_tag.upper()`
  - 目的：視覺上更清晰，類似銀行代碼的顯示方式
- **優點**：
  1. 內部查找不會因大小寫問題失敗
  2. 顯示時美觀且易讀
  3. 避免 `'HSBC_TW'` 和 `'hsbc_tw'` 被視為不同鍵值的問題

### 5.6 狀態覆蓋邏輯
- 規則：特定狀態可覆蓋先前狀態，但並非所有狀態都可互相覆蓋
- 允許的覆蓋路徑：
  1. `pending` → `success`（提取成功）
  2. `pending` → `extract_fail`（提取失敗）
  3. `success` → `parse_fail`（解析失敗）
- 禁止的覆蓋：
  - `download_fail` 不可被覆蓋（終端狀態）
  - `extract_fail` 不可被覆蓋（終端狀態）
  - `parse_fail` 不可被覆蓋（終端狀態）
- 範例：`pending` → `success` (提取成功) → `parse_fail` (解析失敗)

## 6. 測試要點

### 6.1 功能測試
1. **基本流程測試**
   - 正常執行，確認報告正確顯示
   - 按 sender_tag 字母排序
   - 成功/失敗計數正確

2. **邊界情況測試**
   - 沒有 PDF 下載的情況
   - 所有檔案都失敗的情況
   - 混合成功/失敗的情況

3. **狀態追蹤測試**
   - 確認狀態轉換正確
   - 確認錯誤訊息正確顯示
   - 確認檔案不重複追蹤

### 6.2 輸出驗證
1. **格式驗證**
   - 報告分隔線正確
   - 表情符號顯示正常
   - 縮排一致

2. **內容驗證**
   - 原始檔名正確顯示（非重新命名後的檔名）
   - 失敗原因有正確標注
   - 域名顯示正確

### 6.3 整合測試
1. **與現有功能整合**
   - 不影響現有統計數字
   - 不影響現有日誌輸出
   - 不影響現有匯出功能

2. **效能影響**
   - 追蹤邏輯不應顯著影響執行速度
   - 記憶體使用量合理

## 7. 驗收標準 (Acceptance Criteria)

### 7.1 必須完成 (Must Have)
- [ ] 在執行結尾打印按 sender 分類的摘要報告
- [ ] 報告包含以下資訊：
  - 按 sender_tag 分類的銀行/發送者
  - 每個分類下的檔案清單
  - 檔案處理狀態（✅/❌）
  - 成功與失敗計數
  - 失敗原因標註
- [ ] 報告格式符合預期（分隔線、表情符號、縮排）
- [ ] 支援所有處理狀態：success, extract_fail, parse_fail, download_fail
- [ ] 處理邊界情況（沒有 PDF、全部失敗、unknown sender）

### 7.2 應該完成 (Should Have)
- [ ] 報告按 sender_tag 字母排序
- [ ] 避免檔案重複追蹤
- [ ] 狀態轉換邏輯正確（詳見狀態轉換圖）
- [ ] 不影響現有統計數字和功能

### 7.3 可以完成 (Could Have)
- [ ] 提供報告匯出選項（如：同時輸出到檔案）
- [ ] 支援更多狀態細節（如：提取成功但解析失敗的具體原因）
- [ ] 添加顏色輸出（如：終端機顏色）

### 7.4 不會完成 (Won't Have)
- [ ] 圖形化介面報告
- [ ] 歷史報告比較
- [ ] 自動郵件通知

## 8. 實施時間估計

| 任務 | 估計時間 | 說明 |
|------|---------|------|
| 資料結構設計與初始化 | 0.5 小時 | 新增 `self.sender_summary` |
| 追蹤方法實作 | 1 小時 | `_track_file()` 方法 |
| 修改 `download_attachments()` | 1 小時 | 成功/失敗追蹤 |
| 修改 `extract_texts()` | 0.5 小時 | 狀態更新 |
| 修改 `parse_receipts()` | 0.5 小時 | 狀態更新 |
| 報告方法實作 | 1.5 小時 | `print_summary()` 方法 |
| 測試與除錯 | 2 小時 | 各種情境測試 |
| **總計** | **7 小時** | |

## 9. 風險與依賴

### 9.1 技術風險
1. **狀態追蹤複雜性**
   - 風險：多階段狀態更新可能導致邏輯錯誤
   - 緩解：設計清晰的狀態轉換圖，充分測試

2. **效能影響**
   - 風險：追蹤大量檔案可能影響效能
   - 緩解：使用字典查找，避免線性搜尋

3. **與現有程式碼衝突**
   - 風險：修改現有方法可能引入錯誤
   - 緩解：保持修改最小化，充分測試現有功能

### 9.2 依賴項目
1. **`extract_sender_tag()` 函數**
   - 來源：`src/fetch/download_pdfs.py`
   - 用途：生成 sender_tag 用於分類

2. **現有日誌系統**
   - 依賴：`self.log()` 方法
   - 用途：報告輸出

## 10. 給 Developer 的實施建議

### 10.1 實施順序建議
1. **先建立基礎架構**
   ```python
   # 1. 在 __init__ 中新增 self.sender_summary
   # 2. 實作 _track_file() 方法
   # 3. 實作 print_summary() 方法（先輸出簡單測試）
   ```

2. **逐步整合到各階段**
   ```python
   # 1. 先在 download_attachments() 中加入追蹤
   # 2. 測試下載階段的追蹤
   # 3. 逐步加入 extract_texts() 和 parse_receipts() 的追蹤
   ```

3. **最後完善報告格式**
   ```python
   # 1. 確保所有狀態都正確追蹤
   # 2. 完善 print_summary() 的輸出格式
   # 3. 測試各種邊界情況
   ```

### 10.2 測試策略
1. **單元測試優先**
   - 先測試 `_track_file()` 的各種情境
   - 測試 `print_summary()` 的輸出格式

2. **整合測試**
   - 使用少量測試郵件
   - 驗證完整流程的追蹤

3. **邊界測試**
   - 測試沒有 PDF 的情況
   - 測試全部失敗的情況
   - 測試 unknown sender 的情況

### 10.3 除錯技巧
1. **添加臨時日誌**
   ```python
   def _track_file(self, file_info: Dict, status: str, error: str = None):
       self.log('debug', f"Tracking file: {file_info.get('filename')} -> {status}")
       # ... 實作 ...
   ```

2. **檢查資料結構**
   ```python
   # 在 print_summary() 開始時檢查
   self.log('debug', f"sender_summary keys: {list(self.sender_summary.keys())}")
   ```

3. **逐步驗證**
   - 每完成一個階段，手動執行驗證
   - 使用 `print()` 輸出中間結果

### 10.4 程式碼品質注意事項
1. **保持一致性**
   - 使用與現有程式碼相同的命名慣例
   - 保持相同的日誌級別使用方式

2. **錯誤處理**
   - 確保所有例外都被適當處理
   - 避免因追蹤邏輯導致主流程失敗

3. **效能考量**
   - 避免在迴圈中進行複雜操作
   - 使用適當的資料結構（字典查找 O(1)）

### 10.5 交付檢查清單
- [ ] 所有必須完成的驗收標準都滿足
- [ ] 程式碼通過基本測試
- [ ] 不影響現有功能
- [ ] 日誌輸出清晰
- [ ] 邊界情況都有處理
- [ ] 程式碼有適當註解

---

## 附錄 A: 參考程式碼片段

### A.1 完整的 `_track_file()` 方法
```python
def _track_file(self, file_info: Dict, status: str, error: str = None):
    """Track file processing status for summary report."""
    sender_tag = file_info.get('sender_tag', 'unknown')
    sender = file_info.get('sender', 'Unknown')
    original_filename = file_info.get('filename', 'unknown.pdf')
    filepath = file_info.get('filepath')
    
    # 初始化 sender 分類
    if sender_tag not in self.sender_summary:
        domain = sender.split('@')[1] if '@' in sender else 'unknown'
        self.sender_summary[sender_tag] = {
            'sender_display': sender,
            'sender_tag': sender_tag,
            'domain': domain,
            'files': []
        }
    
    # 檢查是否已追蹤此檔案
    existing_files = self.sender_summary[sender_tag]['files']
    for f in existing_files:
        if f['original_filename'] == original_filename:
            # 更新現有檔案的狀態（允許狀態覆蓋）
            f['status'] = status
            f['error'] = error
            if filepath:
                f['filepath'] = filepath
            return
    
    # 新增檔案追蹤
    self.sender_summary[sender_tag]['files'].append({
        'original_filename': original_filename,
        'status': status,
        'error': error,
        'filepath': filepath
    })
```

### A.2 完整的 `print_summary()` 方法
```python
def print_summary(self):
    """Print per-sender summary report at the end of execution."""
    if not self.sender_summary:
        self.log('info', "沒有需要報告的 PDF 檔案。")
        return
    
    lines = []
    lines.append("=" * 60)
    lines.append("📊 PDF 解析摘要報告")
    lines.append("=" * 60)
    lines.append("")
    
    total_success = 0
    total_fail = 0
    
    # 按 sender_tag 字母排序
    for sender_tag, info in sorted(self.sender_summary.items()):
        domain = info['domain']
        # sender_tag 大小寫處理規則：
        # - 內部 key：保持 lowercase（由 extract_sender_tag() 產生）
        # - 顯示時：轉為大寫，視覺上更清晰
        display_tag = sender_tag.upper()
        lines.append(f"🏦 {display_tag} ({domain})")
        lines.append("   檔名:")
        
        success_count = 0
        fail_count = 0
        
        for f in info['files']:
            original_name = f['original_filename']
            status = f['status']
            
            if status == 'success':
                lines.append(f"   - {original_name} ✅")
                success_count += 1
            else:
                # 狀態對應的中文標籤
                error_label = {
                    'extract_fail': '文字提取失敗',
                    'parse_fail': '解析失敗',
                    'download_fail': '下載失敗',
                    'pending': '未處理',
                }.get(status, status)
                
                # 優先使用具體錯誤訊息
                error_detail = f['error'] or error_label
                lines.append(f"   - {original_name} ❌ ({error_detail})")
                fail_count += 1
        
        lines.append(f"   成功: {success_count} 筆 | 失敗: {fail_count} 筆")
        lines.append("")
        
        total_success += success_count
        total_fail += fail_count
    
    lines.append("=" * 60)
    lines.append(f"總計: 成功 {total_success} 筆 | 失敗 {total_fail} 筆")
    lines.append("=" * 60)
    
    report = "\n".join(lines)
    self.log('info', f"\n{report}")
    # 同時輸出到 console 以確保可見性
    print(report)
```

---

**文件結束**