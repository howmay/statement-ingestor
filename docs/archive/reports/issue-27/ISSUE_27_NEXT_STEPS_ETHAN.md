# Issue #27: Immediate Next Steps for Ethan

## 📌 Checklist: Start Here (Next 24 Hours)

### ✅ Already Completed (by Vesper)
- [x] Fixed pdfium test failure
- [x] Fixed 4 gmail_auth test failures
- [x] All 154 tests passing
- [x] Created comprehensive analysis reports
- [x] Designed implementation plan

### 🚀 Tasks to Start Immediately

#### Task 1: Create Comprehensive Test Files (Priority 1)
**Goal**: Raise coverage from 70% to 80%+

**File 1: `test/test_gmail_auth_comprehensive.py`**
- [ ] Test `get_gmail_service()` with `manual_token` parameter
- [ ] Test OOB flow (`oob_callback=True`)
- [ ] Test missing client_secrets file → FileNotFoundError
- [ ] Test invalid/corrupted token file handling
- [ ] Test token file with JSON format (already exists but needs full coverage)
- [ ] Test `_load_credentials_from_token_file` edge cases
- [ ] Test `_save_credentials_to_token_file` both JSON and pickle paths
- [ ] Test `_test_token_usable` with various API error scenarios
- [ ] Test custom paths and port parameters
- [ ] Test refresh token rotation

**File 2: `test/test_retry_enhanced_comprehensive.py`**
- [ ] Test `calculate_backoff()` for various attempt numbers
- [ ] Test `should_retry_on_exception()` with different exception types
- [ ] Test `JSONTruncationError` detection and fixing
- [ ] Test `fix_truncated_json()` with various truncation patterns
- [ ] Test `enhanced_retry_openai` decorator behavior
- [ ] Test rate limit handling (429 responses)
- [ ] Test concurrent safety (if applicable)

**File 3: `test/test_parse_receipt_comprehensive.py`**
- [ ] Test `_get_llm_runtime_config()` for all providers (local, ollama, openai)
- [ ] Test environment variable parsing edge cases
- [ ] Test configuration validation (missing API keys, etc.)
- [ ] Test cache get/set/clear operations
- [ ] Test `parse_receipt_text()` with empty/malformed responses
- [ ] Test `parse_multiple_receipts()` batch processing
- [ ] Test bank parser factory integration
- [ ] Test JSON repair fallback chains
- [ ] Test chunking integration for long texts

**File 4: `test/test_pdf_to_text_comprehensive.py` (remaining)**
- [ ] Test encrypted PDF handling (with wrong password)
- [ ] Test `_extract_with_pdftotext` edge cases (missing tool, errors)
- [ ] Test fallback chain complete scenarios
- [ ] Test non-PDF file handling warnings
- [ ] Test very large PDF handling
- [ ] Test empty PDF pages

**File 5: `test/test_hsbc_ocr_comprehensive.py` (if needed)**
- [ ] Test OCR text cleaning
- [ ] Test regex patterns for different card types
- [ ] Test error recovery in `process_hsbc_ocr_text`

#### Task 2: Quick Performance Benchmark (2-3 hours)
**Goal**: Establish baseline metrics

1. Create `scripts/benchmark.py`:
```python
import time
from pathlib import Path

def benchmark_pdf_extraction(pdf_dir: Path, samples=10):
    """Time PDF extraction for sample files."""
    from src.pdf.pdf_to_text import extract_text_from_pdf
    times = []
    for pdf in list(pdf_dir.glob("*.pdf"))[:samples]:
        start = time.time()
        extract_text_from_pdf(str(pdf))
        times.append(time.time() - start)
    return {
        "avg": sum(times)/len(times),
        "min": min(times),
        "max": max(times),
        "samples": len(times)
    }

def benchmark_llm_parsing(text_samples, samples=5):
    """Time LLM parsing for text samples."""
    from src.llm.parse_receipt import parse_receipt_text
    times = []
    for text in text_samples[:samples]:
        start = time.time()
        parse_receipt_text(text)
        times.append(time.time() - start)
    return {...}

if __name__ == "__main__":
    # Run benchmarks
    pdf_results = benchmark_pdf_extraction(Path("test/data/pdfs"))
    print(f"PDF extraction: {pdf_results}")
```

2. Run baseline and save results to `benchmarks/baseline_20260312.json`

#### Task 3: Design Dependency Injection Prototype (3-4 hours)
**Goal**: Create design document and simple prototype

1. Create `docs/dependency-injection-design.md`:
   - Current coupling analysis
   - Proposed interfaces (protocols)
   - Refactoring steps
   - Migration path (backward compatibility)

2. Create `src/di_prototype.py` (proof of concept):
```python
from typing import Protocol
from dataclasses import dataclass

class GmailService(Protocol):
    def get_emails(self, query: str) -> List[Dict]:
        ...

class LLMClient(Protocol):
    def parse_receipt(self, text: str) -> Dict:
        ...

class PDFExtractor(Protocol):
    def extract_text(self, pdf_path: str) -> str:
        ...

@dataclass
class InMemoryCache:
    data: Dict = field(default_factory=dict)

    def get(self, key: str):
        return self.data.get(key)

    def set(self, key: str, value):
        self.data[key] = value

# Refactored app
class GmailExpenseParserApp:
    def __init__(
        self,
        gmail_service: GmailService,
        pdf_extractor: PDFExtractor,
        llm_client: LLMClient,
        cache: Optional[ResultCache] = None,
        logger: Optional[Logger] = None
    ):
        self.gmail_service = gmail_service
        self.pdf_extractor = pdf_extractor
        self.llm_client = llm_client
        self.cache = cache or InMemoryCache()
        self.logger = logger or logging.getLogger(__name__)
```

3. Write one test using the new pattern.

#### Task 4: Progress Tracking Setup (1 hour)
1. Update `ISSUE_27_PROGRESS_TRACKER.md` with:
   - Daily checkboxes for tasks
   - Coverage metrics after each test file completion
   - Performance benchmark results

2. Set up daily reporting:
   - 18:00 UTC+8 update to Telegram
   - Format: "Day X: Completed Y tasks, coverage: Z%, next: ..."

## 📝 Deliverables Checklist

### By End of Day 1 (tomorrow 18:00)
- [ ] Comprehensive test files for gmail_auth, retry_enhanced, parse_receipt
- [ ] Coverage increased by at least 5% (75% total)
- [ ] Performance benchmarks run and results saved
- [ ] Dependency injection design document draft
- [ ] Progress tracker updated

### By End of Week 1
- [ ] Test coverage ≥80%
- [ ] All new tests passing
- [ ] Performance optimization tasks started
- [ ] Documentation improvements

## 🆘 When to Ask for Help

- **Any test can't be fixed after 2 hours** → Report to Vesper
- **Coverage not improving after 2 days** → Request architecture review
- **Performance benchmarks show worse results** → Stop and analyze
- **Dependencies conflict** → Immediate assistance

## 📞 Communication Cadence

- **Daily**: 18:00 UTC+8 brief update to Telegram
- **Weekly**: Friday comprehensive report in markdown
- **Issues**: Immediate Telegram message with context

## 🔄 Related Files Created

1. `ISSUE_27_COMPREHENSIVE_ANALYSIS.md` - Initial analysis
2. `ISSUE_27_IMPLEMENTATION_PLAN.md` - 4-week detailed plan
3. `ISSUE_27_IMMEDIATE_ACTIONS.md` - Quick start guide (Vesper version)
4. `ISSUE_27_COMPLETE_ANALYSIS_REPORT.md` - Full technical report
5. `ISSUE_27_FINAL_SUMMARY.md` - Executive summary
6. **THIS FILE**: `ISSUE_27_NEXT_STEPS_ETHAN.md` - Your action checklist

## 🎯 First Step Right Now

Start with **Task 1, File 1**:

```bash
# 1. Create test/test_gmail_auth_comprehensive.py
# 2. Add test for manual_token flow
# 3. Run: pytest test/test_gmail_auth_comprehensive.py -v --cov=src.auth.gmail_auth
# 4. Check coverage: pytest --cov=src.auth.gmail_auth --cov-report=term
# 5. Iterate until coverage for auth/gmail_auth.py ≥ 75%
```

---

**Ready to start?** Begin with Task 1, File 1 and report back at 18:00 with your progress.

**Good luck!** 🚀
