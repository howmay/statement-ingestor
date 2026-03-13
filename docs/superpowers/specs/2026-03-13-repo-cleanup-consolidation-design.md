# Repo Cleanup And Consolidation Design

**Date:** 2026-03-13
**Status:** Approved in chat
**Scope:** Documentation and repository cleanup plan for the current `gmail-expense-parser` codebase

## Goal

Reduce repository confusion by consolidating active docs under `docs/`, archiving historical reports and legacy code paths, and defining one clear supported runtime path for future work.

## Priorities

1. Reduce confusion by consolidating docs, reports, and duplicate paths.
2. Make the repo easier to maintain day-to-day.
3. Make the codebase easier to extend with new banks and features.

## Constraints

- The effort should be isolated on a new branch created from the current dirty state.
- The final integration path should be a pull request back into the current branch: `refactor/python-architecture-tdd`.
- Cleanup may include moving or deleting files, as long as migration and reference updates are included in the same effort.
- Historical artifacts should be preserved when they still provide traceability; disposable scratch files should be deleted.

## Current Problems

- The repository root contains many issue reports, summaries, and ad hoc planning documents that obscure the actual entry points and project structure.
- `legacy/` sits alongside active source code without a clear support boundary.
- There are temporary artifacts and generated directories in the workspace that are not part of the supported developer workflow.
- The active runtime path exists, but it is not documented strongly enough: `main.py` -> `src/app.py` -> `src/*`.

## Proposed Design

### 1. Documentation Structure

Active documentation remains under `docs/` and is organized by purpose rather than chronology.

- Keep current product and technical references under `docs/`.
- Add an archival subtree under `docs/archive/` for issue reports, summaries, old implementation notes, and one-off analysis documents currently stored at the repository root.
- Add a small navigation layer so contributors can tell which docs are current, historical, or generated.

### 2. Root-Level Hygiene

The repository root should contain only operational files:

- dependency manifests such as `requirements.txt`, `requirements-dev.txt`, `pyproject.toml`
- active entry points such as `main.py`
- setup/config helpers such as `setup-venv.sh`, `.env.example`
- essential repo metadata such as `.gitignore`

Ad hoc reports, progress notes, and temporary files should move out of the root or be removed.

### 3. Runtime Path

The cleanup should document one supported path for execution and maintenance:

- `main.py` is the canonical CLI entry point.
- `src/app.py` is the application orchestration layer.
- Active modules live under `src/auth`, `src/fetch`, `src/pdf`, `src/llm`, `src/output`, `src/utils`, and `src/bank_parsers`.

The cleanup may extract or reorganize internals later, but it should not leave ambiguity about the supported top-level execution path.

### 4. Legacy Code Policy

`legacy/` becomes explicitly archival:

- It is not the default implementation target for changes.
- It should either move under the new archival structure or remain in place with clear documentation that it is reference-only.
- Any tests or docs that still point at legacy modules should be updated to use active code or be marked historical if retained for comparison.

### 5. Branch And PR Workflow

Implementation should begin by creating a new branch from the current uncommitted state so no in-progress work is lost. The cleanup branch then becomes the vehicle for documentation reorganization, source cleanups, and follow-up fixes. The merge path is a PR targeting `refactor/python-architecture-tdd`.

## Non-Goals

- Rewriting the parsing architecture from scratch
- Adding new bank support during the cleanup
- Performing broad behavior changes unrelated to structure, documentation, or maintainability

## Acceptance Criteria

- The repository root is reduced to operational files only.
- Historical reports are preserved in a documented archival location under `docs/`.
- The active runtime path is documented and consistent with the codebase.
- `legacy/` is clearly marked as archival/reference-only.
- The implementation work is scoped to a dedicated cleanup branch with a PR path back to `refactor/python-architecture-tdd`.
