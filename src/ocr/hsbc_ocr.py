import logging
import os
import re
import shutil
import subprocess
import tempfile
from typing import Dict, List, Optional, Tuple, Set

logger = logging.getLogger(__name__)

MISSING_DESC_LINE_PATTERN = re.compile(
    r'^(?P<tx_md>\d{1,2}/\d{1,2})\s+'
    r'(?P<post_md>\d{1,2}/\d{1,2})\s+'
    r'(?P<amount>-?[0-9,]+(?:\.[0-9]+)?)$'
)

OCR_ROW_PATTERN = re.compile(
    r'(?P<tx_md>\d{1,2}[/-]\d{1,2})\s+'
    r'(?P<post_md>\d{1,2}[/-]\d{1,2})\s+'
    r'(?P<desc>.+?)\s+'
    r'(?P<amount>-?[0-9,]+(?:\.[0-9]+)?)(?:\s*(?P<suffix>CR|DR))?$',
    re.IGNORECASE,
)


def _get_tesseract_langs() -> Set[str]:
    """Return installed tesseract language codes."""
    try:
        proc = subprocess.run(
            ['tesseract', '--list-langs'],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if proc.returncode != 0:
            return set()

        langs = []
        for line in (proc.stdout or '').splitlines():
            line = line.strip()
            if not line or line.startswith('List of available languages'):
                continue
            langs.append(line)

        return set(langs)
    except Exception:
        return set()


def enrich_hsbc_transactions_with_ocr(
    transactions: List[Dict],
    source_info: Optional[Dict] = None,
) -> int:
    """
    Try to fill missing HSBC description fields via OCR on statement pages.

    This is a best-effort fallback for PDFs where text layer loses merchant column.

    Returns:
        Number of transactions successfully enriched.
    """
    source_info = source_info or {}

    pdf_path = source_info.get('filepath')
    if not pdf_path or not os.path.exists(pdf_path):
        logger.debug('HSBC OCR skipped: missing source_info.filepath')
        return 0

    if shutil.which('tesseract') is None:
        logger.warning('HSBC OCR skipped: `tesseract` not found in PATH')
        return 0

    # Default: require chi_tra for HSBC TW statements to avoid severe OCR garbling.
    require_chi_tra = os.getenv('HSBC_OCR_REQUIRE_CHI_TRA', 'true').strip().lower() in {'1', 'true', 'yes', 'on'}
    if require_chi_tra:
        langs = _get_tesseract_langs()
        if 'chi_tra' not in langs:
            logger.warning(
                'HSBC OCR skipped: chi_tra language data not installed in tesseract '
                f'(available={sorted(langs)})'
            )
            return 0

    candidates = []
    for idx, tx in enumerate(transactions):
        raw_line = str(tx.get('raw_text_snippet', '')).strip()
        expense_name = str(tx.get('expense_name', '')).strip()

        # Candidate if we only have date/date/amount with no merchant text
        is_missing = bool(MISSING_DESC_LINE_PATTERN.match(expense_name)) or expense_name == raw_line
        if not is_missing:
            continue

        line_match = MISSING_DESC_LINE_PATTERN.match(raw_line) or MISSING_DESC_LINE_PATTERN.match(expense_name)
        if not line_match:
            continue

        amount = _safe_float(tx.get('amount'))
        if amount is None:
            continue

        candidates.append({
            'index': idx,
            'tx_md': _normalize_md(line_match.group('tx_md')),
            'post_md': _normalize_md(line_match.group('post_md')),
            'amount': amount,
        })

    if not candidates:
        return 0

    try:
        ocr_rows = _ocr_statement_rows(pdf_path, source_info)
    except Exception as e:
        logger.warning(f'HSBC OCR failed: {e}')
        return 0

    if not ocr_rows:
        logger.info('HSBC OCR found no row candidates')
        return 0

    # Build match maps
    exact_map: Dict[Tuple[str, str, float], str] = {}
    abs_map: Dict[Tuple[str, str, float], str] = {}

    for row in ocr_rows:
        key_exact = (row['tx_md'], row['post_md'], round(row['amount'], 2))
        key_abs = (row['tx_md'], row['post_md'], round(abs(row['amount']), 2))

        desc = row['desc']
        if key_exact not in exact_map or len(desc) > len(exact_map[key_exact]):
            exact_map[key_exact] = desc
        if key_abs not in abs_map or len(desc) > len(abs_map[key_abs]):
            abs_map[key_abs] = desc

    enriched = 0
    for c in candidates:
        key_exact = (c['tx_md'], c['post_md'], round(c['amount'], 2))
        key_abs = (c['tx_md'], c['post_md'], round(abs(c['amount']), 2))

        desc = exact_map.get(key_exact) or abs_map.get(key_abs)
        if not desc:
            continue

        tx = transactions[c['index']]
        tx['expense_name'] = desc[:120]
        tx['confidence'] = max(float(tx.get('confidence', 0.0) or 0.0), 0.93)
        tx['description_source'] = 'ocr'
        enriched += 1

    if enriched:
        logger.info(f'HSBC OCR enriched descriptions: {enriched}/{len(candidates)}')

    return enriched


def _ocr_statement_rows(pdf_path: str, source_info: Optional[Dict] = None) -> List[Dict]:
    rows: List[Dict] = []

    try:
        import pypdfium2 as pdfium
    except ImportError as e:
        raise RuntimeError('pypdfium2 is required for OCR fallback') from e

    source_info = source_info or {}

    with tempfile.TemporaryDirectory(prefix='hsbc_ocr_') as tmpdir:
        pdf = _open_pdf_with_password_candidates(pdfium, pdf_path, source_info)

        try:
            for i in range(len(pdf)):
                page = None
                bitmap = None
                pil_image = None
                try:
                    page = pdf[i]
                    bitmap = page.render(scale=2.4)
                    image_path = os.path.join(tmpdir, f'page_{i+1}.png')

                    pil_image = bitmap.to_pil()
                    pil_image.save(image_path, format='PNG')

                    text = _run_tesseract_text(image_path)
                    if not text:
                        continue

                    rows.extend(_extract_rows_from_ocr_text(text))
                finally:
                    if pil_image is not None:
                        try:
                            pil_image.close()
                        except Exception:
                            pass
                    if bitmap is not None:
                        try:
                            bitmap.close()
                        except Exception:
                            pass
                    if page is not None:
                        try:
                            page.close()
                        except Exception:
                            pass
        finally:
            try:
                pdf.close()
            except Exception:
                pass

    return rows


def _open_pdf_with_password_candidates(pdfium, pdf_path: str, source_info: Dict):
    """Open encrypted PDF using known password candidates."""
    sender = source_info.get('sender', '')
    preferred_password = source_info.get('pdf_password')

    candidates: List[Optional[str]] = []
    if preferred_password:
        candidates.append(preferred_password)

    # Fallback to configured password list for this sender
    try:
        from src.config import get_bank_password
        for pw in get_bank_password(sender) or []:
            if pw and pw not in candidates:
                candidates.append(pw)
    except Exception:
        pass

    # Finally, try opening without password
    candidates.append(None)

    last_error = None
    for pw in candidates:
        try:
            if pw:
                return pdfium.PdfDocument(pdf_path, password=pw)
            return pdfium.PdfDocument(pdf_path)
        except Exception as e:
            last_error = e
            continue

    raise RuntimeError(f"Failed to load document (PDFium: {last_error})")


def _run_tesseract_text(image_path: str) -> str:
    # Try traditional Chinese + English first, then fallback to English.
    for lang in ('chi_tra+eng', 'eng'):
        cmd = ['tesseract', image_path, 'stdout', '--psm', '6', '-l', lang]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if proc.returncode == 0 and proc.stdout.strip():
                return proc.stdout
        except Exception:
            continue

    return ''


def _extract_rows_from_ocr_text(text: str) -> List[Dict]:
    rows: List[Dict] = []

    for raw_line in text.splitlines():
        line = ' '.join(raw_line.strip().split())
        if not line:
            continue

        m = OCR_ROW_PATTERN.search(line)
        if not m:
            continue

        desc = m.group('desc').strip()
        if not desc or len(desc) < 2:
            continue

        # Skip non-merchant obvious headers
        low = desc.lower()
        if any(k in low for k in ['statement', 'payment', 'minimum', 'credit limit', '總額', '應繳']):
            continue

        amount = _safe_float(m.group('amount'))
        if amount is None:
            continue

        suffix = (m.group('suffix') or '').upper()
        if suffix == 'CR':
            amount = -abs(amount)
        elif suffix == 'DR':
            amount = abs(amount)

        rows.append({
            'tx_md': _normalize_md(m.group('tx_md')),
            'post_md': _normalize_md(m.group('post_md')),
            'amount': amount,
            'desc': desc,
        })

    return rows


def _normalize_md(md: str) -> str:
    m = re.match(r'^(\d{1,2})[/-](\d{1,2})$', md.strip())
    if not m:
        return md.strip()
    return f'{int(m.group(1)):02d}/{int(m.group(2)):02d}'


def _safe_float(value) -> Optional[float]:
    if value is None:
        return None

    try:
        return float(str(value).replace(',', '').strip())
    except Exception:
        return None
