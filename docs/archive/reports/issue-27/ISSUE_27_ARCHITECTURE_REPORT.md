# Issue #27: Architecture and Performance Review Report

## 1. Executive Summary
This report details the architectural and performance assessment of the `gmail-expense-parser` project. While the core functionality (fetching, parsing, and exporting) is in place, the current implementation has several issues regarding test stability, modularity, and extensibility.

Current overall test coverage is approximately **55%**, with **25 test failures** out of 101 items.

## 2. Technical Assessment

### 2.1 Test Coverage and Quality
- **Current State**: Low coverage in core orchestration logic (`src/app.py` has 0% coverage due to tight coupling).
- **Broken Tests**: 25 failed tests.
  - **Reason**: Improper mocking of `open()`, `os.path.exists`, and environment variables. Many tests use `unittest.mock.Mock` where they should use `mock_open`.
  - **Fragility**: Tests are too dependent on the local environment and global state.

### 2.2 Performance Analysis
- **PDF Extraction Bottleneck**:
  - The fallback chain (pypdfium2 → pdfplumber → PyPDF2) is robust but `pdfplumber` is significantly slower for large PDFs.
  - Concurrency is used in `src/app.py` for PDF extraction but not for LLM parsing, which is the actual bottleneck for time and cost.
- **LLM Token Management**:
  - Chunking and JSON repair logic is present but could be more efficient.
  - No caching for previously parsed PDFs, leading to redundant LLM calls.

### 2.3 Architecture and Modularization
- **Tight Coupling**: `GmailExpenseParserApp` creates its own dependencies (loggers, services, validators), making unit testing difficult.
- **"Utils" Bloat**: `src/utils/` contains disparate logic like `progress.py`, `retry_enhanced.py`, and `config_validator.py` which are growing in complexity.
- **Deterministic vs. LLM Parsing**: The boundary between deterministic bank parsers and LLM parsers is well-defined, but the factory logic relies on fragile string matching.

### 2.4 Documentation
- Internal design documents (PRD, TRD) exist but lack clear "Developer's Guide" or "API Documentation" for new bank parser additions.

---

## 3. Recommended Improvement Plan

### Phase 1: Stability and Testing (Highest Priority)
1.  **Fix all broken tests**: Refactor mocking strategies and resolve assertion errors.
2.  **Coverage to 80%+**:
    - Decouple `GmailExpenseParserApp` from its dependencies to allow mocking of Gmail service and LLM clients.
    - Add comprehensive unit tests for `app.py` and `config.py`.
3.  **Modernize Testing**: Switch to more robust `pytest` fixtures.

### Phase 2: Architecture Refactoring
1.  **Dependency Injection**: Inject services into the application class.
2.  **Registry Pattern**: Replace the if-else bank factory with a registry-based approach for better extensibility.
3.  **Pipeline Abstraction**: Formalize the pipeline stages (Fetch → Extract → Parse → Export) into a composable workflow.

### Phase 3: Performance Optimization
1.  **Parallel LLM Parsing**: Process multiple PDF texts concurrently through the LLM.
2.  **Result Caching**: Cache successful PDF extractions and LLM parsing results by MD5 hash of the PDF content.
3.  **Optimize PDF Extraction**: Fine-tune `pdfplumber` parameters for speed.

---

## 4. Execution Start: Phase 1
I am starting Phase 1 by fixing the broken tests and increasing coverage.
Estimated Time: 4-6 hours.
Priority: Urgent (Foundational for further development).
