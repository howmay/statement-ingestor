# Repo Cleanup And Consolidation Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reorganize the repository so active docs and runtime paths are obvious, historical artifacts are archived, and cleanup work lands through an isolated branch and PR back to `refactor/python-architecture-tdd`.

**Architecture:** Treat this as a staged consolidation, not a rewrite. First isolate the work on a new branch that includes the current dirty state, then establish the target documentation structure, move or delete stale artifacts, document the supported runtime path, and finally run focused regression checks so the cleanup does not silently break developer workflows.

**Tech Stack:** Git, Python, pytest, Markdown documentation

---

## Chunk 1: Isolate Work And Define The New Documentation Topology

### Task 1: Create the cleanup branch from the current dirty state

**Files:**
- Modify: `.gitignore`
- Create: `docs/archive/README.md`
- Create: `docs/README.md`
- Test: N/A

- [ ] **Step 1: Verify the current branch and dirty state**

Run: `git status --short --branch`
Expected: output shows branch `refactor/python-architecture-tdd` with existing modified/untracked files.

- [ ] **Step 2: Create and switch to the cleanup branch without discarding current changes**

Run: `git switch -c chore/repo-cleanup-consolidation`
Expected: branch switches successfully and all current modifications remain in the working tree.

- [ ] **Step 3: Add ignore rules for obvious generated and temporary artifacts if they are not already covered**

Update `.gitignore` so it clearly ignores:

```gitignore
.worktrees/
htmlcov/
.pytest_cache/
__pycache__/
tmp*
downloads/
logs/
output/
```

- [ ] **Step 4: Add a `docs/README.md` that defines active vs archived documentation**

```md
# Documentation Map

- `PRD.md`, `TRD_v1.md`, `DEVELOPER_GUIDE.md`: active project docs
- `archive/`: historical reports, issue writeups, and superseded plans
- `superpowers/`: agent-authored specs and implementation plans
```

- [ ] **Step 5: Add a `docs/archive/README.md` describing what belongs in the archive**

```md
# Archive

This directory stores historical reports, implementation notes, and issue-specific writeups that are kept for traceability but are not the current source of truth.
```

- [ ] **Step 6: Run a quick sanity check on the new branch state**

Run: `git status --short`
Expected: only intended docs and ignore-rule changes are present, plus the pre-existing carried-over work.

- [ ] **Step 7: Commit the topology/bootstrap changes**

```bash
git add .gitignore docs/README.md docs/archive/README.md
git commit -m "chore: define documentation layout for repo cleanup"
```

## Chunk 2: Archive Root-Level Reports And Remove Disposable Artifacts

### Task 2: Move historical markdown reports out of the repository root

**Files:**
- Create: `docs/archive/reports/README.md`
- Modify: `docs/README.md`
- Move: `ARCHITECTURE_ANALYSIS_REPORT.md`
- Move: `PERFORMANCE_ANALYSIS_REPORT.md`
- Move: `FINAL_IMPLEMENTATION_PLAN.md`
- Move: `ISSUE_22_FIX_REPORT.md`
- Move: `ISSUE_23_ENHANCEMENT_REPORT.md`
- Move: `ISSUE_23_FINAL_SUMMARY.md`
- Move: `ISSUE_23_IMPLEMENTATION_COMPLETE.md`
- Move: `ISSUE_24_FINAL_REPORT.md`
- Move: `ISSUE_24_IMPLEMENTATION.md`
- Move: `ISSUE_24_SOLUTION_REPORT.md`
- Move: `ISSUE_27_ARCHITECTURE_REPORT.md`
- Move: `ISSUE_27_COMPLETE_ANALYSIS_REPORT.md`
- Move: `ISSUE_27_COMPREHENSIVE_ANALYSIS.md`
- Move: `ISSUE_27_CRON_COMPLETE_REPORT.md`
- Move: `ISSUE_27_CRON_PROGRESS_REPORT.md`
- Move: `ISSUE_27_FINAL_SUMMARY.md`
- Move: `ISSUE_27_IMMEDIATE_ACTIONS.md`
- Move: `ISSUE_27_IMPLEMENTATION_PLAN.md`
- Move: `ISSUE_27_NEXT_STEPS_ETHAN.md`
- Move: `ISSUE_27_PROGRESS_REPORT.md`
- Move: `ISSUE_27_STATUS_20260313.md`
- Test: `rg -n "ISSUE_27_|FINAL_IMPLEMENTATION_PLAN|ARCHITECTURE_ANALYSIS_REPORT|PERFORMANCE_ANALYSIS_REPORT" docs src test`

- [ ] **Step 1: Create a report archive index**

Add `docs/archive/reports/README.md`:

```md
# Archived Reports

Root-level issue reports and ad hoc implementation notes were moved here during repository cleanup to keep the repository root operational and readable.
```

- [ ] **Step 2: Move root-level reports into archive folders grouped by topic**

Suggested structure:

```text
docs/archive/reports/general/
docs/archive/reports/issue-22/
docs/archive/reports/issue-23/
docs/archive/reports/issue-24/
docs/archive/reports/issue-27/
```

Example commands:

```bash
mkdir -p docs/archive/reports/general docs/archive/reports/issue-22 docs/archive/reports/issue-23 docs/archive/reports/issue-24 docs/archive/reports/issue-27
git mv ARCHITECTURE_ANALYSIS_REPORT.md docs/archive/reports/general/
git mv PERFORMANCE_ANALYSIS_REPORT.md docs/archive/reports/general/
git mv FINAL_IMPLEMENTATION_PLAN.md docs/archive/reports/general/
git mv ISSUE_22_FIX_REPORT.md docs/archive/reports/issue-22/
git mv ISSUE_23_ENHANCEMENT_REPORT.md docs/archive/reports/issue-23/
git mv ISSUE_23_FINAL_SUMMARY.md docs/archive/reports/issue-23/
git mv ISSUE_23_IMPLEMENTATION_COMPLETE.md docs/archive/reports/issue-23/
git mv ISSUE_24_FINAL_REPORT.md docs/archive/reports/issue-24/
git mv ISSUE_24_IMPLEMENTATION.md docs/archive/reports/issue-24/
git mv ISSUE_24_SOLUTION_REPORT.md docs/archive/reports/issue-24/
git mv ISSUE_27_ARCHITECTURE_REPORT.md docs/archive/reports/issue-27/
git mv ISSUE_27_COMPLETE_ANALYSIS_REPORT.md docs/archive/reports/issue-27/
git mv ISSUE_27_COMPREHENSIVE_ANALYSIS.md docs/archive/reports/issue-27/
git mv ISSUE_27_CRON_COMPLETE_REPORT.md docs/archive/reports/issue-27/
git mv ISSUE_27_CRON_PROGRESS_REPORT.md docs/archive/reports/issue-27/
git mv ISSUE_27_FINAL_SUMMARY.md docs/archive/reports/issue-27/
git mv ISSUE_27_IMMEDIATE_ACTIONS.md docs/archive/reports/issue-27/
git mv ISSUE_27_IMPLEMENTATION_PLAN.md docs/archive/reports/issue-27/
git mv ISSUE_27_NEXT_STEPS_ETHAN.md docs/archive/reports/issue-27/
git mv ISSUE_27_PROGRESS_REPORT.md docs/archive/reports/issue-27/
git mv ISSUE_27_STATUS_20260313.md docs/archive/reports/issue-27/
```

- [ ] **Step 3: Remove disposable scratch artifacts from the root**

Delete files that are clearly temporary and not part of the supported workflow:

```bash
rm -f tmp0lv75i3i tmpv7u6mtj4
```

- [ ] **Step 4: Update any docs index references that still imply these files live at the root**

Update `docs/README.md` with an archive pointer:

```md
- `archive/reports/`: historical implementation reports and issue writeups formerly stored at repository root
```

- [ ] **Step 5: Verify the root is now operational rather than report-heavy**

Run: `find . -maxdepth 1 -type f | sort`
Expected: root mostly contains config, manifests, entry points, and a much smaller set of markdown files.

- [ ] **Step 6: Commit the archive migration**

```bash
git add docs/archive docs/README.md
git commit -m "chore: archive historical reports under docs"
```

## Chunk 3: Mark The Supported Runtime Path And Demote Legacy Code

### Task 3: Document active entry points and archive the legacy path

**Files:**
- Modify: `docs/DEVELOPER_GUIDE.md`
- Modify: `docs/TRD_v1.md`
- Create: `legacy/README.md`
- Modify: `main.py`
- Modify: `src/app.py`
- Test: `pytest test/test_app.py test/test_app_comprehensive.py test/test_csv_writer.py -q`

- [ ] **Step 1: Add an explicit runtime-path section to `docs/DEVELOPER_GUIDE.md`**

Document:

```md
## Supported Runtime Path

The supported execution path is:

`main.py` -> `src/app.py` -> active modules under `src/`

`legacy/` is reference-only and should not receive feature work.
```

- [ ] **Step 2: Update `docs/TRD_v1.md` so it no longer leaves legacy paths ambiguous**

Add a maintenance note:

```md
## Maintenance Note

Current implementation work targets `main.py` and `src/`. Files under `legacy/` are retained for reference and migration history only.
```

- [ ] **Step 3: Add `legacy/README.md` to make the archive status explicit**

```md
# Legacy Code

This directory contains historical or superseded implementations retained for reference.

- Do not add new feature work here.
- Prefer `main.py` and modules under `src/` for active maintenance.
- Remove legacy references from active docs and tests when practical.
```

- [ ] **Step 4: Add brief comments in the active entry points if their role is still unclear**

Example for `main.py`:

```python
# Canonical CLI entry point for the maintained application path.
```

Example for `src/app.py`:

```python
# Orchestrates the supported end-to-end pipeline used by main.py.
```

- [ ] **Step 5: Run focused runtime tests**

Run: `pytest test/test_app.py test/test_app_comprehensive.py test/test_csv_writer.py -q`
Expected: PASS

- [ ] **Step 6: Commit the active-path documentation changes**

```bash
git add docs/DEVELOPER_GUIDE.md docs/TRD_v1.md legacy/README.md main.py src/app.py
git commit -m "docs: mark supported runtime path and archive legacy code"
```

## Chunk 4: Remove Stale References And Prepare The PR

### Task 4: Clean stale references, verify the repository, and open the PR

**Files:**
- Modify: `test/test_csv_writer.py`
- Modify: `test/test_csv_writer_comprehensive.py`
- Modify: `test/test_e2e_workflow.py`
- Modify: `docs/README.md`
- Test: `pytest -q`

- [ ] **Step 1: Search for stale references to moved root reports, temporary files, or ambiguous legacy guidance**

Run: `rg -n "ISSUE_27_|ARCHITECTURE_ANALYSIS_REPORT|PERFORMANCE_ANALYSIS_REPORT|FINAL_IMPLEMENTATION_PLAN|tmp0lv75i3i|tmpv7u6mtj4|legacy/" docs src test`
Expected: results are either archive references or clearly intentional mentions.

- [ ] **Step 2: Update any failing references in docs or tests**

Examples:

```python
# Replace outdated path expectations with archive paths when assertions depend on exact filenames.
expected_report_path = "docs/archive/reports/issue-27/ISSUE_27_IMPLEMENTATION_PLAN.md"
```

```md
- Historical issue reports now live under `docs/archive/reports/`.
```

- [ ] **Step 3: Run the full test suite**

Run: `pytest -q`
Expected: PASS, or only pre-existing failures that are documented in the branch notes.

- [ ] **Step 4: Inspect the final tree and git status**

Run: `git status --short`
Expected: only intended cleanup changes remain.

Run: `find docs -maxdepth 3 -type f | sort`
Expected: active docs, archive docs, and superpowers planning docs are organized and discoverable.

- [ ] **Step 5: Commit the final cleanup pass**

```bash
git add docs legacy test
git commit -m "chore: finalize repo cleanup consolidation"
```

- [ ] **Step 6: Push the cleanup branch and open the PR back to the current branch**

```bash
git push -u origin chore/repo-cleanup-consolidation
gh pr create --base refactor/python-architecture-tdd --head chore/repo-cleanup-consolidation --title "chore: consolidate repo structure and docs" --body "## Summary
- archive historical root-level reports under docs
- mark the supported runtime path and legacy status
- clean repository structure for maintainability"
```

- [ ] **Step 7: Capture verification notes in the PR description or branch notes**

Include:

```text
Verification:
- pytest test/test_app.py test/test_app_comprehensive.py test/test_csv_writer.py -q
- pytest -q
```
