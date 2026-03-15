# Documentation Map

- `PRD.md`, `TRD_v1.md`, `DEVELOPER_GUIDE.md`: active project and technical documentation.
- `../README.md`: setup, run, and usage guide.
- Active CSV exports use separate `收入` and `支出` columns instead of a single signed amount column.
- Active Gmail ingestion is statement-only: monthly bank statements and credit-card statements are targeted instead of merchant receipt emails.
- Default Gmail search now uses a generic statement query plus required attachment file types (`pdf/xls/xlsx/csv`) and exclusion terms; `from`-based narrowing remains available as future optional refinement rather than the default path.
