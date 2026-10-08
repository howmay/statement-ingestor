import csv
import os
import re
from datetime import datetime
from typing import List, Dict, Any, Tuple
import logging

logger = logging.getLogger(__name__)

CSV_COLUMNS = ['date', 'income', 'expense', 'currency', 'expense_name', 'expense_type', 'source', 'source_file']


def _transaction_month(receipt: Dict[str, Any]) -> str:
    """Return YYYY-MM bucket for a receipt. Unknown dates go to `unknown`."""
    date_value = str(receipt.get('date') or '').strip()
    if re.match(r'^\d{4}-\d{2}-\d{2}$', date_value):
        return date_value[:7]
    if re.match(r'^\d{4}/\d{2}/\d{2}$', date_value):
        return date_value[:7].replace('/', '-')
    return 'unknown'


def _receipt_key(row: Dict[str, str]) -> Tuple[str, str, str, str, str, str]:
    """Stable de-dup/sort key of an export row (from _format_export_row or read back from the CSV)."""
    return tuple(str(row.get(k) or '').strip() for k in ('date', 'income', 'expense', 'currency', 'expense_name', 'source_file'))


def _detect_statement_kind(receipt: Dict[str, Any]) -> str:
    # Bank parsers always set parser_name (…CardParser / …BankParser); trust it over labels.
    parser_name = str(receipt.get('parser_name') or '')
    if 'Card' in parser_name:
        return 'credit_card'
    if 'Bank' in parser_name:
        return 'bank'

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

    for key in CSV_COLUMNS:
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


def export_receipts_to_csv(receipts: List[Dict[str, Any]], output_dir: str = "output") -> str:
    """
    Export parsed receipts into month-partitioned CSV files (append-only + de-duplicated + sorted).

    Output naming: `expenses_YYYY-MM.csv`.
    """
    if not receipts:
        logger.warning("No receipts to export")
        return ""

    os.makedirs(output_dir, exist_ok=True)

    # Group by month bucket; a row that moves no money (e.g. "INTEREST USD $0") is noise.
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for receipt in receipts:
        try:
            if float(receipt.get('amount') or 0) == 0:
                continue
        except (TypeError, ValueError):
            pass
        month = _transaction_month(receipt)
        grouped.setdefault(month, []).append(receipt)

    written_paths: List[str] = []

    for month, month_receipts in grouped.items():
        filepath = os.path.join(output_dir, f"expenses_{month}.csv")

        # Dedup against rows already in the file and within this batch.
        seen = {_receipt_key(row) for row in _load_existing_rows(filepath)}
        new_rows: List[Dict[str, str]] = []
        for receipt in month_receipts:
            row = _format_export_row(receipt)
            key = _receipt_key(row)
            if key not in seen:
                seen.add(key)
                new_rows.append(row)

        if not new_rows:
            continue

        file_exists = os.path.exists(filepath) and os.path.getsize(filepath) > 0
        with open(filepath, 'a' if file_exists else 'w', newline='', encoding='utf-8-sig') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=CSV_COLUMNS)
            if not file_exists:
                writer.writeheader()
            writer.writerows(new_rows)

        logger.info(f"Exported month={month}: new_rows={len(new_rows)} total_rows={len(seen)} file={filepath}")
        written_paths.append(filepath)

    return ",".join(sorted(written_paths))


def sort_exported_receipt_csvs(csv_paths: List[str]) -> None:
    """Sort exported monthly receipt CSV files after append-only writes complete."""
    for filepath in csv_paths:
        if not filepath or not os.path.exists(filepath):
            continue

        rows = _load_existing_rows(filepath)
        if not rows:
            continue

        rows.sort(key=_receipt_key)
        temp_filepath = f"{filepath}.tmp"

        with open(temp_filepath, 'w', newline='', encoding='utf-8-sig') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=CSV_COLUMNS)
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
        info = item.get('file_info') or item  # app passes metadata under file_info
        source_filename = info.get('filename') or os.path.basename(info.get('filepath', '')) or 'unknown.pdf'
        sender_tag = info.get('sender_tag', 'unknown')
        subject = info.get('subject', '')
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
