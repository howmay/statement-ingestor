# Src Refactor Design

**Date:** 2026-03-13
**Status:** Approved in chat
**Scope:** First sub-project for structural refactoring of the active `src/` tree

## Goal

Restructure the active `src/` tree around clear responsibilities, remove stale or generated artifacts from active code, and complete a full import-path cutover so future `test/` and `legacy/` cleanup can build on a cleaner foundation.

## Why This Is The First Sub-Project

The current repository still mixes active packages, stale backup artifacts, tracked generated files, and historical naming patterns inside `src/`. Refactoring `test/` or `legacy/` first would preserve ambiguity about what the active application layout actually is. Cleaning `src/` first creates the stable target that later projects can follow.

## Current Problems

- Active source is spread across packages with inconsistent naming and mixed abstraction levels:
  - orchestration in `src/app.py`
  - external integration code in `src/auth/` and `src/fetch/`
  - parsing code in `src/bank_parsers/`, `src/llm/`, `src/ocr/`, and `src/pdf/`
  - output code in `src/output/`
  - catch-all helpers in `src/utils/`
- Active `src/` still contains tracked generated artifacts such as `__pycache__/`.
- Active `src/` still contains stale backup files such as `src/llm/parse_receipt.py.backup`.
- Existing names reflect previous structure rather than a clear long-term architecture.

## Approved Direction

This refactor is allowed to move active modules between packages. It is not limited to removing junk files or doing small in-place renames.

The target structure is responsibility-based:

- `src/cli/`: command-line coordination if more CLI-specific logic is extracted later
- `src/runtime/`: application orchestration currently centered in `src/app.py`
- `src/integrations/`: Gmail auth/fetch and external service integrations
- `src/parsing/`: bank parsers, LLM parsing, OCR, and PDF text extraction
- `src/export/`: CSV and future output writers
- `src/core/`: config and shared internal contracts
- `src/support/`: logging, retry, progress, cache, and validation helpers

### Expected Migrations

- Move `src/app.py` into `src/runtime/`
- Collapse `src/auth/` and `src/fetch/` into `src/integrations/`
- Consolidate `src/bank_parsers/`, `src/llm/`, `src/ocr/`, and `src/pdf/` into `src/parsing/`
- Rename `src/output/` to `src/export/`
- Move `src/config.py` and any shared internal contracts into `src/core/`
- Replace `src/utils/` with a more intentional `src/support/` package or split those helpers more cleanly within that area

## Migration Strategy

This refactor should be a full cutover on the branch, not a long-lived dual structure.

- Move active modules into their destination packages.
- Update imports in active code, tests, and active docs to point to final paths.
- Use compatibility shims only if they reduce migration risk within the same branch.
- Remove temporary shims before considering the refactor complete.

### Explicit Exclusion

`legacy/` remains reference-only during this project. Historical names such as `csv_exporter`, `parser_factory`, and `pdf_extractor` should not be restored under active `src/` as part of this refactor.

## Execution Order

To limit circular-dependency and import-breakage risk, implementation should proceed in layers:

1. Create destination packages and shared contracts
2. Move low-risk `core` and `support` modules
3. Move integration and export modules
4. Move parsing modules
5. Move runtime orchestration last
6. Update tests and active docs to final paths
7. Remove temporary shims and stale artifacts

## Verification Strategy

Verification must be staged, not deferred until the end.

- Run focused tests after each layer move
- Search for stale imports referencing old package paths
- Re-run application-focused tests after the runtime move
- Finish with the full suite, while distinguishing true refactor regressions from the known pre-existing retry-test import failures

## Success Criteria

- No tracked generated artifacts or backup files remain in active `src/`
- Active modules live in the new package structure
- Active code and tests import only the new package paths
- Active docs describe only the new package structure
- `legacy/` is not pulled back into the active import graph

## Non-Goals

- Refactoring the `test/` tree as a standalone project
- Reorganizing `legacy/` beyond what is necessary to preserve its reference-only status
- Introducing new product features or parser behavior changes unrelated to the structural migration
