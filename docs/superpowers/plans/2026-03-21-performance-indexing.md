# Performance Indexing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace repeated file hashing, full CSV rewrites, and JSON-based download dedupe with a `.cache` SQLite index while preserving current public APIs.

**Architecture:** Add a shared SQLite-backed performance index under `.cache/performance_index.sqlite3`, then route file fingerprinting, CSV dedupe, and download dedupe through focused helpers. Keep `file_info["file_md5"]` as the in-memory pipeline memoization layer and preserve the existing app entry points.

**Tech Stack:** Python, sqlite3, pytest, existing runtime/cache/export/download modules

---

## Chunk 1: Shared Index Foundation

### Task 1: Add focused tests for persistent file fingerprint caching

**Files:**
- Modify: `test/test_utils_cache.py`

- [x] Step 1: Write a failing test proving `get_file_md5()` returns a cached md5 when `size` and `mtime` are unchanged
- [x] Step 2: Write a failing test proving `get_file_md5()` recomputes after the file content changes
- [x] Step 3: Run `pytest -q test/test_utils_cache.py` and verify the new coverage fails before implementation

### Task 2: Implement the SQLite performance index helper

**Files:**
- Modify: `src/support/cache.py`

- [x] Step 1: Add SQLite initialization under `.cache/performance_index.sqlite3`
- [x] Step 2: Add a file fingerprint table keyed by path with `size`, `mtime`, and `md5`
- [x] Step 3: Update `get_file_md5()` to reuse md5 values when file metadata is unchanged
- [x] Step 4: Keep graceful fallback behavior if SQLite access fails
- [x] Step 5: Run `pytest -q test/test_utils_cache.py` and confirm green

## Chunk 2: Runtime MD5 Reuse

### Task 3: Lock app pipeline code to the per-file md5 memoization path

**Files:**
- Modify: `src/runtime/app.py`
- Verify: `test/test_app.py`

- [x] Step 1: Confirm extract and parse stages already reuse `file_info["file_md5"]`
- [x] Step 2: Keep md5 lookups in the runtime flowing through `_get_or_compute_file_md5()`
- [x] Step 3: Run `pytest -q test/test_app.py` and confirm green

## Chunk 3: Incremental CSV Export

### Task 4: Add failing tests for append-only CSV export with persistent dedupe

**Files:**
- Modify: `test/test_csv_writer_comprehensive.py`

- [x] Step 1: Add a failing test showing reruns append only unseen rows without rewriting existing rows
- [x] Step 2: Add a failing test showing an existing CSV file can be backfilled into the new SQLite dedupe index
- [x] Step 3: Run `pytest -q test/test_csv_writer_comprehensive.py` and verify failure before implementation

### Task 5: Implement SQLite-backed CSV dedupe and append-only writes

**Files:**
- Modify: `src/export/csv_writer.py`

- [x] Step 1: Add a SQLite table for month/path/key tracking
- [x] Step 2: Backfill index entries from an existing CSV file when the month file exists but no index rows do
- [x] Step 3: Append only new rows and write headers only for newly created files
- [x] Step 4: Preserve current return values and lock behavior
- [x] Step 5: Run `pytest -q test/test_csv_writer.py test/test_csv_writer_comprehensive.py` and confirm green

## Chunk 4: Download Dedupe Index

### Task 6: Add failing tests for metadata-aware download dedupe

**Files:**
- Modify: `test/test_download_pdfs_enhanced.py`

- [x] Step 1: Add a failing test proving unchanged files no longer rely on `.md5_cache.json`
- [x] Step 2: Add a failing test proving changed file metadata triggers md5 refresh
- [x] Step 3: Run `pytest -q test/test_download_pdfs_enhanced.py -k "existing_file_by_md5"` and verify failure before implementation

### Task 7: Replace `.md5_cache.json` with SQLite-backed download indexing

**Files:**
- Modify: `src/integrations/gmail/downloads.py`
- Modify: `src/support/cache.py`

- [x] Step 1: Remove `.md5_cache.json` read/write logic
- [x] Step 2: Query and refresh file md5 values through the shared performance index
- [x] Step 3: Persist new downloads into the SQLite index after successful writes
- [x] Step 4: Run `pytest -q test/test_download_pdfs.py test/test_download_pdfs_enhanced.py -k "md5 or existing_file"` and confirm green

## Chunk 5: Final Verification

### Task 8: Run focused regression coverage

**Files:**
- Verify: `test/test_utils_cache.py`
- Verify: `test/test_app.py`
- Verify: `test/test_csv_writer.py`
- Verify: `test/test_csv_writer_comprehensive.py`
- Verify: `test/test_download_pdfs.py`
- Verify: `test/test_download_pdfs_enhanced.py`

- [x] Step 1: Run `pytest -q test/test_utils_cache.py test/test_app.py test/test_csv_writer.py test/test_csv_writer_comprehensive.py test/test_download_pdfs.py test/test_download_pdfs_enhanced.py`
- [x] Step 2: Review any failures for nearby regressions in cache, export, or download flows
- [x] Step 3: Summarize the verified behavior changes and remaining tradeoffs
