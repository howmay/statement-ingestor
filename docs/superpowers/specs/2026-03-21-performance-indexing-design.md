# Performance Indexing Design

## Context

The current pipeline still pays unnecessary I/O and rewrite costs in three places:

1. File MD5 values may be recomputed by reading the same PDF multiple times across pipeline stages.
2. Monthly CSV export de-duplicates by loading, sorting, and rewriting the full file on every run.
3. Download de-duplication relies on `.md5_cache.json`, which becomes stale easily and still forces cold-start directory scans.

The user wants all three optimizations implemented, with persistent indexes stored under `.cache/`.

## Goals

- Reuse file MD5 values across the pipeline and across runs whenever the file has not changed.
- Make receipt CSV export append-only for new rows instead of rewriting the whole month file.
- Replace the download MD5 JSON cache with a persistent metadata-aware index.
- Preserve current public entry points so the rest of the app can keep calling the same functions.

## Non-Goals

- Changing the user-facing CSV schema.
- Introducing external services or non-standard-library dependencies.
- Adding background compaction in this iteration.

## Chosen Approach

Use a single SQLite database at `.cache/performance_index.sqlite3` with focused tables for:

- file fingerprints: `path`, `size`, `mtime`, `md5`
- download dedupe lookups via shared file fingerprint metadata
- CSV dedupe rows: month bucket + stable receipt key + target csv path

This keeps persistence simple, avoids a new dependency, and lets both download and export logic share one indexing backend.

## Design Details

### 1. Persistent file fingerprint cache

`src/support/cache.py` gains a SQLite-backed index helper. `get_file_md5(filepath)` now:

- stats the file
- checks whether a cached row exists with the same `size` and `mtime`
- returns cached md5 when unchanged
- recomputes and upserts only when metadata changed or no row exists

`src/runtime/app.py` continues to treat `file_info["file_md5"]` as the per-run memoized value, so each file is hashed at most once in a single pipeline execution even if multiple stages ask for it.

### 2. Incremental CSV export index

`src/export/csv_writer.py` keeps the existing CSV output contract but changes its write path:

- compute the stable dedupe key for each receipt row
- check a SQLite index table instead of loading existing CSV rows every run
- append only the rows whose keys are not yet indexed
- write the header only when creating a new CSV file

Row ordering is no longer enforced by full-file sorting. The file reflects append order across runs. This trades globally sorted output for significantly lower rewrite cost on large datasets.

For compatibility with existing CSV files, the first time a month file is seen without index rows, the exporter backfills the index from the current CSV contents once, then continues in append-only mode.

### 3. Download dedupe index

`src/integrations/gmail/downloads.py` stops reading and writing `.md5_cache.json`.

Instead, download dedupe:

- walks the download directory
- asks the shared file fingerprint cache for each file's md5
- reuses cached md5 values when `size` and `mtime` are unchanged
- refreshes md5 automatically when metadata changed
- persists md5 for newly written downloads immediately after save

This keeps cold starts cheaper because unchanged files can be matched from metadata without rehashing file contents again.

## Error Handling

- If SQLite initialization fails, log the issue and fall back to direct md5 computation rather than crashing the application.
- If an index row points to a missing file, ignore it and continue.
- If CSV index backfill fails, surface the error rather than silently risking duplicate output.

## Testing Strategy

- Add unit tests for metadata-based md5 reuse and invalidation when file contents change.
- Add CSV writer tests proving reruns append only new rows and backfill existing files into the dedupe index.
- Add download tests proving unchanged files no longer rely on `.md5_cache.json` and changed files refresh the stored md5.
- Run focused app/runtime tests to verify the pipeline still uses the same public interfaces.

## Risks and Tradeoffs

- CSV files are no longer globally sorted after each run. This is intentional for performance.
- SQLite introduces a small local state file, but it is acceptable because the user explicitly approved `.cache/`.
- Concurrent writes need careful locking. Existing file lock behavior in CSV export remains in place, and SQLite transactions are used for index updates.
