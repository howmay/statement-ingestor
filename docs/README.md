# Documentation Map

- `PRD.md`, `TRD_v1.md`, `DEVELOPER_GUIDE.md`: active project and technical documentation.
- Active CSV exports use separate `收入` and `支出` columns instead of a single signed amount column.
- Active Gmail ingestion is statement-only: monthly bank statements and credit-card statements are targeted instead of merchant receipt emails.
- Preferred Gmail search configuration is `STATEMENT_SEARCH_PROFILES`; legacy `TARGET_SENDERS` and `TARGET_KEYWORDS` remain as fallback compatibility settings.
- `archive/`: historical reports, issue writeups, and superseded implementation notes.
- `archive/reports/`: historical implementation reports and issue writeups formerly stored at repository root.
- `superpowers/`: agent-authored design specs and implementation plans.
