import csv
import os
import json
import re
import sqlite3
import time
from contextlib import closing
from datetime import datetime
from typing import List, Dict, Any, Tuple
import logging

logger = logging.getLogger(__name__)

class FileLock:
    """A simple cross-platform file locking mechanism to prevent concurrent write issues."""
    def __init__(self, lock_file: str, timeout: int = 10):
        self.lock_file = lock_file
        self.timeout = timeout
        self.fd = None

    def __enter__(self):
        start_time = time.time()
        while True:
            try:
                # O_EXCL ensures that the call fails if the file already exists
                self.fd = os.open(self.lock_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                break
            except FileExistsError:
                if time.time() - start_time > self.timeout:
                    logger.warning(f"Timeout waiting for lock: {self.lock_file}. Proceeding anyway...")
                    break
                time.sleep(0.1)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.fd is not None:
            os.close(self.fd)
            try:
                os.remove(self.lock_file)
            except OSError:
                pass


CSV_COLUMNS = [
    ('date', '日期'),
    ('income', '收入'),
    ('expense', '支出'),
    ('currency', '幣別'),
    ('expense_name', '消費名目'),
    ('expense_type', '類型'),
    ('source', '來源'),
    ('source_file', '來源檔案'),
]

PERFORMANCE_CACHE_DIR = ".cache"
PERFORMANCE_DB_FILENAME = "performance_index.sqlite3"


def _transaction_month(receipt: Dict[str, Any]) -> str:
    """Return YYYY-MM bucket for a receipt. Unknown dates go to `unknown`."""
    date_value = str(receipt.get('date') or '').strip()
    if re.match(r'^\d{4}-\d{2}-\d{2}$', date_value):
        return date_value[:7]
    if re.match(r'^\d{4}/\d{2}/\d{2}$', date_value):
        return date_value[:7].replace('/', '-')
    return 'unknown'


def _receipt_key(receipt: Dict[str, Any]) -> Tuple[str, str, str, str, str, str]:
    """Stable key for de-duplication across reruns."""
    income_str, expense_str = _split_income_and_expense(receipt)

    return (
        str(receipt.get('date') or '').strip(),
        income_str,
        expense_str,
        str(receipt.get('currency') or '').strip(),
        str(receipt.get('expense_name') or '').strip(),
        str(receipt.get('source_file') or receipt.get('original_file') or '').strip(),
    )


def _detect_statement_kind(receipt: Dict[str, Any]) -> str:
    source = str(receipt.get('source') or '').lower()
    sender_tag = str(receipt.get('sender_tag') or '').lower()
    source_file = str(receipt.get('source_file') or receipt.get('original_file') or '').lower()
    hint = ' '.join([source, sender_tag, source_file])

    if any(token in hint for token in ['credit card', '信用卡', 'hsbc', 'sinopac credit', 'first bank credit']):
        return 'credit_card'
    if any(token in hint for token in [' bank', '銀行', '對帳單', 'fubon bank']):
        return 'bank'
    return 'unknown'


def _split_income_and_expense(receipt: Dict[str, Any]) -> Tuple[str, str]:
    amount = receipt.get('amount')
    if amount is None:
        return '', ''

    try:
        value = float(amount)
    except Exception:
        return '', ''

    if value == 0:
        return '', ''

    cashflow_side = str(receipt.get('cashflow_side') or '').strip().lower()
    if cashflow_side == 'income':
        return f"{abs(value):.2f}", ''
    if cashflow_side == 'expense':
        return '', f"{abs(value):.2f}"

    statement_kind = _detect_statement_kind(receipt)

    if statement_kind == 'credit_card':
        if value < 0:
            return f"{abs(value):.2f}", ''
        return '', f"{abs(value):.2f}"

    if statement_kind == 'bank':
        if value > 0:
            return f"{abs(value):.2f}", ''
        return '', f"{abs(value):.2f}"

    return '', ''


def _format_export_row(receipt: Dict[str, Any]) -> Dict[str, str]:
    row: Dict[str, str] = {}
    source_file = receipt.get('source_file') or receipt.get('original_file') or ''
    income_str, expense_str = _split_income_and_expense(receipt)

    for key, _display in CSV_COLUMNS:
        value = source_file if key == 'source_file' else receipt.get(key)
        if key == 'income':
            row[key] = income_str
        elif key == 'expense':
            row[key] = expense_str
        elif value is None:
            row[key] = ''
        else:
            row[key] = str(value)

    return row


def _load_existing_rows(filepath: str) -> List[Dict[str, str]]:
    if not os.path.exists(filepath):
        return []

    try:
        with open(filepath, 'r', newline='', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            return list(reader)
    except Exception:
        return []


def _sort_row_key(row: Dict[str, str]) -> Tuple[str, str, str, str, str, str]:
    return (
        str(row.get("date") or "").strip(),
        str(row.get("income") or "").strip(),
        str(row.get("expense") or "").strip(),
        str(row.get("currency") or "").strip(),
        str(row.get("expense_name") or "").strip(),
        str(row.get("source_file") or "").strip(),
    )


def _performance_db_path() -> str:
    cache_dir = os.path.join(os.getcwd(), PERFORMANCE_CACHE_DIR)
    os.makedirs(cache_dir, exist_ok=True)
    return os.path.join(cache_dir, PERFORMANCE_DB_FILENAME)


def _connect_performance_db() -> sqlite3.Connection:
    conn = sqlite3.connect(_performance_db_path(), timeout=5)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _init_csv_export_index(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS csv_export_index (
            csv_path TEXT NOT NULL,
            month TEXT NOT NULL,
            dedupe_key TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (csv_path, dedupe_key)
        )
        """
    )
    conn.commit()


def _serialize_csv_row_key(row: Dict[str, str]) -> str:
    return json.dumps(
        [
            str(row.get("date") or "").strip(),
            str(row.get("income") or "").strip(),
            str(row.get("expense") or "").strip(),
            str(row.get("currency") or "").strip(),
            str(row.get("expense_name") or "").strip(),
            str(row.get("source_file") or "").strip(),
        ],
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _backfill_csv_index(conn: sqlite3.Connection, filepath: str, month: str) -> None:
    existing_index_count = conn.execute(
        "SELECT COUNT(*) FROM csv_export_index WHERE csv_path = ?",
        (filepath,),
    ).fetchone()[0]
    if existing_index_count or not os.path.exists(filepath):
        return

    existing_rows = _load_existing_rows(filepath)
    if not existing_rows:
        return

    conn.executemany(
        """
        INSERT OR IGNORE INTO csv_export_index(csv_path, month, dedupe_key)
        VALUES (?, ?, ?)
        """,
        [(filepath, month, _serialize_csv_row_key(row)) for row in existing_rows],
    )
    conn.commit()


def export_receipts_to_csv(receipts: List[Dict[str, Any]], output_dir: str = "output") -> str:
    """
    Export parsed receipts into month-partitioned CSV files (append-only + de-duplicated + sorted).

    Output naming: `expenses_YYYY-MM.csv`.
    """
    if not receipts:
        logger.warning("No receipts to export")
        return ""

    os.makedirs(output_dir, exist_ok=True)

    # Group by month bucket
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for receipt in receipts:
        month = _transaction_month(receipt)
        grouped.setdefault(month, []).append(receipt)

    written_paths: List[str] = []

    for month, month_receipts in grouped.items():
        filename = f"expenses_{month}.csv"
        filepath = os.path.join(output_dir, filename)
        lock_filepath = f"{filepath}.lock"

        with FileLock(lock_filepath):
            try:
                with closing(_connect_performance_db()) as conn:
                    _init_csv_export_index(conn)
                    _backfill_csv_index(conn, filepath, month)

                    new_rows: List[Dict[str, str]] = []
                    index_entries: List[Tuple[str, str, str]] = []

                    for receipt in month_receipts:
                        row = _format_export_row(receipt)
                        dedupe_key = _serialize_csv_row_key(row)
                        existing = conn.execute(
                            """
                            SELECT 1 FROM csv_export_index
                            WHERE csv_path = ? AND dedupe_key = ?
                            """,
                            (filepath, dedupe_key),
                        ).fetchone()
                        if existing:
                            continue
                        new_rows.append(row)
                        index_entries.append((filepath, month, dedupe_key))

                    if not new_rows:
                        continue

                    file_exists = os.path.exists(filepath) and os.path.getsize(filepath) > 0
                    mode = 'a' if file_exists else 'w'

                    with open(filepath, mode, newline='', encoding='utf-8-sig') as csvfile:
                        writer = csv.DictWriter(csvfile, fieldnames=[k for k, _ in CSV_COLUMNS])
                        if not file_exists:
                            writer.writeheader()
                        writer.writerows(new_rows)

                    conn.executemany(
                        """
                        INSERT OR IGNORE INTO csv_export_index(csv_path, month, dedupe_key)
                        VALUES (?, ?, ?)
                        """,
                        index_entries,
                    )
                    conn.commit()

                    total_rows = conn.execute(
                        "SELECT COUNT(*) FROM csv_export_index WHERE csv_path = ?",
                        (filepath,),
                    ).fetchone()[0]

                logger.info(
                    f"Exported month={month}: new_rows={len(new_rows)} total_rows={total_rows} file={filepath}"
                )
                written_paths.append(filepath)
            except Exception as e:
                logger.error(f"Failed to write CSV {filepath}: {e}")
                raise

    return ",".join(sorted(written_paths))


def sort_exported_receipt_csvs(csv_paths: List[str]) -> None:
    """Sort exported monthly receipt CSV files after append-only writes complete."""
    for filepath in csv_paths:
        if not filepath or not os.path.exists(filepath):
            continue

        rows = _load_existing_rows(filepath)
        if not rows:
            continue

        rows.sort(key=_sort_row_key)
        temp_filepath = f"{filepath}.tmp"

        with open(temp_filepath, 'w', newline='', encoding='utf-8-sig') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=[k for k, _ in CSV_COLUMNS])
            writer.writeheader()
            writer.writerows(rows)

        os.replace(temp_filepath, filepath)


def export_extracted_texts_to_csv(extracted_texts: List[Dict[str, Any]], output_dir: str = "output") -> str:
    """
    Export extracted PDF text into a line-level CSV for debugging.

    Args:
        extracted_texts: List of extracted text items from Step 4.
        output_dir: Directory to save CSV file.

    Returns:
        Path to the created CSV file, or empty string if no data.
    """
    if not extracted_texts:
        logger.warning("No extracted texts to export")
        return ""

    os.makedirs(output_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_filename = f"pdf_text_lines_{timestamp}.csv"
    filepath = os.path.join(output_dir, output_filename)

    rows: List[Dict[str, Any]] = []

    for item in extracted_texts:
        source_filename = item.get('filename', 'unknown.pdf')
        sender_tag = item.get('sender_tag', 'unknown')
        subject = item.get('subject', '')
        text = item.get('text', '') or ''
        file_char_count = len(text)

        current_page = 1
        line_no = 0

        for raw_line in text.splitlines():
            page_match = re.match(r'^---\s*Page\s+(\d+)\s*---$', raw_line.strip(), re.IGNORECASE)
            if page_match:
                current_page = int(page_match.group(1))
                line_no = 0
                continue

            clean_line = raw_line.strip()
            if not clean_line:
                continue

            line_no += 1
            rows.append({
                'filename': source_filename,
                'sender_tag': sender_tag,
                'subject': subject,
                'page': current_page,
                'line_no': line_no,
                'line_text': clean_line,
                'line_char_count': len(clean_line),
                'file_char_count': file_char_count,
                'has_date_pattern': bool(re.search(r'\d{2,4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}/\d{1,2}', clean_line)),
                'has_currency_pattern': bool(re.search(r'NT\$|TWD|USD|US\$|SGD|S\$|HKD|HK\$|元', clean_line, re.IGNORECASE)),
            })

    if not rows:
        logger.warning("Extracted texts are empty after line split")
        return ""

    fieldnames = [
        'filename', 'sender_tag', 'subject', 'page', 'line_no',
        'line_text', 'line_char_count', 'file_char_count',
        'has_date_pattern', 'has_currency_pattern'
    ]

    try:
        with open(filepath, 'w', newline='', encoding='utf-8-sig') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

        logger.info(f"Exported {len(rows)} text lines to CSV: {filepath}")
        return filepath
    except Exception as e:
        logger.error(f"Failed to export extracted text CSV: {e}")
        raise


def format_receipt_for_csv(receipt: Dict[str, Any]) -> Dict[str, Any]:
    """
    Format a receipt dictionary for CSV export.
    
    Args:
        receipt: Parsed receipt dictionary.
    
    Returns:
        Formatted receipt with cleaned values.
    """
    formatted = receipt.copy()
    
    # Format float amounts to 2 decimal places
    if 'amount' in formatted and isinstance(formatted['amount'], (int, float)):
        formatted['amount'] = f"{formatted['amount']:.2f}"
    
    # Format confidence as percentage
    if 'confidence' in formatted and isinstance(formatted['confidence'], (int, float)):
        formatted['confidence'] = f"{formatted['confidence']:.1%}"
    
    # Ensure all values are strings for CSV
    for key, value in formatted.items():
        if value is None:
            formatted[key] = ''
        elif not isinstance(value, str):
            formatted[key] = str(value)
    
    return formatted


if __name__ == "__main__":
    # Test the CSV writer with sample data
    sample_receipts = [
        {
            'date': '2024-12-25',
            'amount': 350.0,
            'currency': 'TWD',
            'expense_name': 'Uber ride',
            'expense_type': 'Transportation',
            'source': 'Uber',
            'confidence': 0.95,
            'original_file': 'uber_receipt.pdf',
            'sender_tag': 'uber',
            'parsed_at': '2024-12-25T12:30:00',
            'parsing_method': 'openai'
        },
        {
            'date': '2024-12-24',
            'amount': 1299.0,
            'currency': 'TWD',
            'expense_name': 'Amazon purchase',
            'expense_type': 'Shopping',
            'source': 'Amazon',
            'confidence': 0.85,
            'original_file': 'amazon_invoice.pdf',
            'sender_tag': 'amazon',
            'parsed_at': '2024-12-24T15:45:00',
            'parsing_method': 'heuristic'
        }
    ]
    
    print("Testing CSV export...")
    try:
        output_path = export_receipts_to_csv(sample_receipts, "test_output")
        print(f"✓ CSV exported to: {output_path}")
        
        # Display first few lines
        with open(output_path, 'r', encoding='utf-8-sig') as f:
            lines = f.readlines()
            print("\nFirst 3 lines of CSV:")
            for i, line in enumerate(lines[:3]):
                print(f"  {i+1}: {line.strip()}")
                
    except Exception as e:
        print(f"✗ Error: {e}")
