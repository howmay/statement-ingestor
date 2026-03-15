from __future__ import annotations

import base64
import json
import logging
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from html import unescape
from typing import Any, Dict, List, Optional


logger = logging.getLogger(__name__)

POSITIVE_HINTS = [
    "Composite Statement",
    "statement",
    "對帳單",
    "信用卡帳單",
    "銀行對帳單",
    "transaction detail",
]

NEGATIVE_HINTS = [
    "保單",
    "人壽",
    "活動通知",
    "核卡通知",
    "應付憑據",
    "Investment Statement",
    "Margin Account",
]


def build_attachment_inventory_query(date_from: str, date_to: Optional[str] = None) -> str:
    after = _normalize_gmail_date(date_from)
    if not after:
        raise ValueError(f"invalid date_from: {date_from}")

    include_clause = '("statement" OR "對帳單" OR "信用卡帳單" OR "銀行對帳單" OR "transaction detail")'
    file_clause = "(filename:pdf OR filename:csv)"
    exclude_clause = '-("保單" OR "人壽" OR "活動通知" OR "核卡通知" OR "應付憑據" OR "Investment Statement" OR "Margin Account")'

    query_parts = [include_clause, file_clause, exclude_clause]
    query_parts.append(f"after:{after}")

    if date_to:
        before_dt = datetime.strptime(_normalize_gmail_date(date_to), "%Y/%m/%d") + timedelta(days=1)
        query_parts.append(f"before:{before_dt.strftime('%Y/%m/%d')}")

    return " ".join(query_parts)


def fetch_attachment_email_records(
    service,
    date_from: str,
    date_to: Optional[str] = None,
    max_results: Optional[int] = None,
) -> List[Dict[str, Any]]:
    query = build_attachment_inventory_query(date_from, date_to)
    page_token = None
    records: List[Dict[str, Any]] = []

    while True:
        page_size = 50 if max_results is None else min(50, max_results - len(records))
        if page_size <= 0:
            break

        response = service.users().messages().list(
            userId="me",
            q=query,
            maxResults=page_size,
            pageToken=page_token,
        ).execute()

        for msg in response.get("messages", []):
            detail = service.users().messages().get(
                userId="me",
                id=msg["id"],
                format="full",
            ).execute()
            records.append(_message_to_record(detail))
            if max_results is not None and len(records) >= max_results:
                break

        page_token = response.get("nextPageToken")
        if not page_token or (max_results is not None and len(records) >= max_results):
            break

    return records


def recommend_search_filters(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    positive_records = [record for record in records if _is_statement_like(record)]
    negative_records = [record for record in records if not _is_statement_like(record)]

    include_terms = _top_terms(positive_records, min_count=1)
    exclude_terms = _top_terms(negative_records, min_count=1)
    include_terms = [term for term in include_terms if term not in exclude_terms][:12]
    exclude_terms = [term for term in exclude_terms if term not in include_terms][:12]

    profiles = _build_profiles(positive_records, include_terms, exclude_terms)
    recommended_query = _build_recommended_query(include_terms, exclude_terms)

    return {
        "total_records": len(records),
        "positive_records": len(positive_records),
        "negative_records": len(negative_records),
        "include_terms": include_terms,
        "exclude_terms": exclude_terms,
        "profiles": profiles,
        "recommended_query": recommended_query,
    }


def _message_to_record(message: Dict[str, Any]) -> Dict[str, Any]:
    payload = message.get("payload", {})
    headers = {
        str(header.get("name", "")).lower(): header.get("value", "")
        for header in payload.get("headers", [])
    }
    attachments = _collect_attachment_filenames(payload)
    body_text = _extract_text_from_payload(payload)

    return {
        "id": message.get("id"),
        "sender": headers.get("from", ""),
        "subject": headers.get("subject", ""),
        "snippet": message.get("snippet", ""),
        "attachment_filenames": attachments,
        "body_text": body_text,
        "internal_date": message.get("internalDate"),
    }


def _collect_attachment_filenames(payload: Dict[str, Any]) -> List[str]:
    filenames: List[str] = []
    for part in payload.get("parts", []) or []:
        filename = str(part.get("filename") or "").strip()
        if filename:
            filenames.append(filename)
        filenames.extend(_collect_attachment_filenames(part))
    return filenames


def _extract_text_from_payload(payload: Dict[str, Any]) -> str:
    text_parts: List[str] = []

    mime_type = payload.get("mimeType", "")
    data = payload.get("body", {}).get("data")
    if data and mime_type in {"text/plain", "text/html"}:
        decoded = base64.urlsafe_b64decode(data.encode("utf-8")).decode("utf-8", errors="ignore")
        if mime_type == "text/html":
            decoded = re.sub(r"<[^>]+>", " ", decoded)
        text_parts.append(unescape(decoded))

    for part in payload.get("parts", []) or []:
        extracted = _extract_text_from_payload(part)
        if extracted:
            text_parts.append(extracted)

    return "\n".join(part.strip() for part in text_parts if part.strip())


def _is_statement_like(record: Dict[str, Any]) -> bool:
    haystack = " ".join([
        str(record.get("sender", "")),
        str(record.get("subject", "")),
        str(record.get("body_text", "")),
        " ".join(record.get("attachment_filenames", [])),
    ]).lower()

    positive = any(term.lower() in haystack for term in POSITIVE_HINTS)
    negative = any(term.lower() in haystack for term in NEGATIVE_HINTS)
    return positive and not negative


def _top_terms(records: List[Dict[str, Any]], min_count: int = 2) -> List[str]:
    counter: Counter[str] = Counter()
    for record in records:
        for term in _extract_terms(record):
            counter[term] += 1
    return [term for term, count in counter.most_common() if count >= min_count]


def _extract_terms(record: Dict[str, Any]) -> List[str]:
    terms: List[str] = []
    terms.extend(_interesting_lines(str(record.get("subject", ""))))
    body_lines = [line.strip() for line in str(record.get("body_text", "")).splitlines() if line.strip()]
    terms.extend(_interesting_lines("\n".join(body_lines[:30])))
    terms.extend(_interesting_lines("\n".join(body_lines[-20:])))
    return list(dict.fromkeys(terms))


def _interesting_lines(text: str) -> List[str]:
    out: List[str] = []
    for raw_line in text.splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip()
        if not line:
            continue
        if len(line) > 40:
            continue
        matched_hints = [hint for hint in POSITIVE_HINTS + NEGATIVE_HINTS if hint in line]
        if matched_hints:
            out.append(line)
            out.extend(matched_hints)
            continue
        if re.search(r"(20\d{2}年\d{1,2}月|\d{4}[/-]\d{1,2})", line):
            out.append(line)
    return out


def _build_profiles(
    records: List[Dict[str, Any]],
    include_terms: List[str],
    exclude_terms: List[str],
) -> List[Dict[str, Any]]:
    grouped: dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for record in records:
        sender = str(record.get("sender", "")).strip()
        if sender:
            grouped[sender].append(record)

    profiles = []
    for sender, sender_records in sorted(grouped.items()):
        sender_terms = _top_terms(sender_records, min_count=1)
        subject_keywords = [term for term in sender_terms if term in include_terms][:4]
        if not subject_keywords:
            subject_keywords = [term for term in include_terms[:2]]

        profiles.append({
            "name": _profile_name(sender),
            "senders": [sender],
            "subject_keywords": subject_keywords,
            "exclude_keywords": exclude_terms[:4],
            "has_pdf_attachment": True,
        })

    return profiles


def _build_recommended_query(include_terms: List[str], exclude_terms: List[str]) -> str:
    include_clause = " OR ".join(f'"{term}"' for term in include_terms[:6]) or '"對帳單"'
    query = f'({include_clause}) (filename:pdf OR filename:csv)'
    if exclude_terms:
        query += f" -({' OR '.join(exclude_terms[:6])})"
    return query


def _profile_name(sender: str) -> str:
    local, _, domain = sender.partition("@")
    base = domain or local or "profile"
    base = re.sub(r"[^a-zA-Z0-9]+", "-", base).strip("-").lower()
    return base[:40] or "profile"


def _normalize_gmail_date(date_text: Optional[str]) -> Optional[str]:
    if not date_text:
        return None

    raw = str(date_text).strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y/%m/%d")
        except ValueError:
            continue
    return None


def analysis_to_json(data: Dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)
