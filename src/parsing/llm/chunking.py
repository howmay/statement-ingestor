"""Chunking and merge helpers for large transaction extraction."""

from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Tuple


def safe_env_int(name: str, default: int, minimum: int = 1, maximum: int = 100000) -> int:
    """Read int env var with bounds and fallback default."""
    raw = os.getenv(name, str(default)).strip()
    try:
        val = int(raw)
    except Exception:
        return default
    return max(minimum, min(maximum, val))


def get_chunking_config() -> Dict[str, Any]:
    """Read adaptive chunking controls from environment variables."""
    enabled = os.getenv('ENABLE_ADAPTIVE_CHUNKING', 'true').strip().lower() in {'1', 'true', 'yes', 'on'}
    max_chunk_size = safe_env_int('MAX_CHUNK_SIZE', 3500, minimum=500, maximum=20000)
    min_tx_per_chunk = safe_env_int('MIN_TRANSACTIONS_PER_CHUNK', 5, minimum=1, maximum=100)
    force_threshold = safe_env_int('FORCE_CHUNKING_TEXT_LENGTH', 8000, minimum=1000, maximum=50000)

    return {
        'enabled': enabled,
        'max_chunk_size': max_chunk_size,
        'min_transactions_per_chunk': min_tx_per_chunk,
        'force_threshold': force_threshold,
    }


def should_enable_chunking(text: str, source_info: Dict[str, Any], force: bool = False) -> bool:
    """Determine whether to enable chunking."""
    cfg = get_chunking_config()
    if not cfg['enabled'] and not force:
        return False

    if force:
        return True

    if len(text) > cfg['force_threshold']:
        return True

    sender_tag = source_info.get('sender_tag', '').lower()
    if 'hsbc' in sender_tag and len(text) > 5000:
        return True

    date_count = len(re.findall(r'\d{4}[-/]\d{1,2}[-/]\d{1,2}', text))
    if date_count > 25:
        return True

    return False


def calculate_max_tokens(text_length: int) -> int:
    """Calculate max_tokens based on input size."""
    return min(4000, 1000 + (text_length // 2))


def chunk_text_by_transactions(
    text: str,
    max_chunk_size: int = 3500,
    min_transactions_per_chunk: int = 5,
) -> List[Tuple[str, List[int]]]:
    """Split text into chunks based on transaction boundaries."""
    if len(text) <= max_chunk_size:
        return [(text, [0])]

    lines = text.split('\n')
    transaction_starts = []

    date_patterns = [
        r'\d{4}[-/]\d{1,2}[-/]\d{1,2}',
        r'\d{1,2}[-/]\d{1,2}[-/]\d{4}',
        r'\d{3}[-/]\d{1,2}[-/]\d{1,2}',
        r'\d{4}年\d{1,2}月\d{1,2}日',
    ]

    for i, line in enumerate(lines):
        for pattern in date_patterns:
            if re.search(pattern, line):
                transaction_starts.append(i)
                break

    if len(transaction_starts) < 2:
        return [(text[i : i + max_chunk_size], [i]) for i in range(0, len(text), max_chunk_size)]

    chunks = []
    current_chunk_lines = []
    current_chunk_indices = []
    current_size = 0

    for i, line in enumerate(lines):
        line_size = len(line) + 1
        is_transaction_start = i in transaction_starts

        if (
            current_size + line_size > max_chunk_size
            and len(current_chunk_indices) >= min_transactions_per_chunk
            and is_transaction_start
        ):
            if current_chunk_lines:
                chunks.append(('\n'.join(current_chunk_lines), current_chunk_indices.copy()))

            current_chunk_lines = [line]
            current_chunk_indices = [i] if is_transaction_start else []
            current_size = line_size
        else:
            current_chunk_lines.append(line)
            if is_transaction_start:
                current_chunk_indices.append(i)
            current_size += line_size

    if current_chunk_lines:
        chunks.append(('\n'.join(current_chunk_lines), current_chunk_indices))

    return chunks


def merge_transaction_results(all_transactions: List[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """Merge and deduplicate chunked results."""
    if not all_transactions:
        return []

    flat_transactions: List[Dict[str, Any]] = []
    for chunk_transactions in all_transactions:
        flat_transactions.extend(chunk_transactions)

    seen = set()
    unique_transactions: List[Dict[str, Any]] = []

    for tx in flat_transactions:
        key = (
            tx.get('date'),
            f"{float(tx.get('amount', 0)):.2f}" if tx.get('amount') is not None else '0.00',
            tx.get('expense_name', '')[:50],
        )
        if key in seen:
            continue
        seen.add(key)
        unique_transactions.append(tx)

    return unique_transactions
