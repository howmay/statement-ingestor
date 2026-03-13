import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from src.config import TARGET_SENDERS, TARGET_KEYWORDS
from src.utils.retry import retry_gmail

logger = logging.getLogger(__name__)


def _normalize_gmail_date(date_text: Optional[str]) -> Optional[str]:
    """Normalize date string into Gmail query format YYYY/MM/DD."""
    if not date_text:
        return None

    raw = str(date_text).strip()
    if not raw:
        return None

    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y/%m/%d")
        except ValueError:
            continue

    return None


def build_gmail_query(
    senders: List[str],
    keywords: List[str],
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> str:
    """
    Build a Gmail API search query from senders/keywords and optional date range.

    Args:
        senders: List of sender email addresses.
        keywords: List of keywords to search in subject/body.
        date_from: Inclusive start date (YYYY-MM-DD, YYYY/MM/DD, or YYYYMMDD).
        date_to: Inclusive end date (same formats). Implemented as Gmail `before` of next day.

    Returns:
        A Gmail search query string.
    """
    # Build sender part: (from:sender1 OR from:sender2 ...)
    sender_query = " OR ".join([f'from:"{sender}"' for sender in senders])
    if len(senders) > 1:
        sender_query = f"({sender_query})"
    
    # Build keyword part: (keyword1 OR keyword2 ...)
    keyword_query = " OR ".join([f'"{keyword}"' for keyword in keywords])
    if len(keywords) > 1:
        keyword_query = f"({keyword_query})"
    
    # Combine with PDF attachment requirement
    query_parts = []
    if sender_query:
        query_parts.append(sender_query)
    if keyword_query:
        query_parts.append(keyword_query)
    query_parts.append("has:attachment filename:pdf")

    # Date range (Gmail query: after inclusive-ish, before exclusive)
    from_norm = _normalize_gmail_date(date_from)
    to_norm = _normalize_gmail_date(date_to)

    if from_norm:
        query_parts.append(f"after:{from_norm}")

    if to_norm:
        to_dt = datetime.strptime(to_norm, "%Y/%m/%d") + timedelta(days=1)
        query_parts.append(f"before:{to_dt.strftime('%Y/%m/%d')}")

    final_query = " ".join(query_parts)
    logger.debug(f"Built Gmail query: {final_query}")
    logger.debug(f"  - Senders: {senders}")
    logger.debug(f"  - Keywords: {keywords}")
    logger.debug(f"  - Date from: {from_norm}")
    logger.debug(f"  - Date to: {to_norm}")
    return final_query


@retry_gmail
def search_emails(
    service,
    senders=None,
    keywords=None,
    max_results: Optional[int] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Search emails using Gmail API with retry mechanism.
    
    Args:
        service: Authenticated Gmail API service object.
        senders: List of sender email addresses (defaults to TARGET_SENDERS).
        keywords: List of keywords (defaults to TARGET_KEYWORDS).
        max_results: Maximum number of emails to return. None = fetch all pages.
        date_from: Inclusive start date (YYYY-MM-DD, YYYY/MM/DD, or YYYYMMDD).
        date_to: Inclusive end date (same formats).
    
    Returns:
        List of email metadata dictionaries with keys:
        - 'id': Gmail message ID
        - 'threadId': Thread ID
        - 'sender': From header (extracted)
        - 'subject': Subject header
        - 'internalDate': Internal date timestamp
    """
    if senders is None:
        senders = TARGET_SENDERS
    if keywords is None:
        keywords = TARGET_KEYWORDS
    
    logger.info(f"Starting email search with:")
    logger.info(f"  - Senders: {senders}")
    logger.info(f"  - Keywords: {keywords}")
    logger.info(f"  - Max results: {max_results if max_results is not None else 'ALL'}")
    logger.info(f"  - Date range: {date_from or '-'} ~ {date_to or '-'}")

    query = build_gmail_query(senders, keywords, date_from=date_from, date_to=date_to)
    logger.info(f"Searching emails with query: {query}")
    
    emails = []
    seen_ids = set()
    page_token = None
    page_count = 0

    try:
        while True:
            page_count += 1

            if max_results is None:
                page_max_results = 50
            else:
                remaining = max_results - len(emails)
                if remaining <= 0:
                    logger.info(f"Reached maximum results limit: {max_results}")
                    break
                page_max_results = min(50, remaining)

            logger.debug(f"Fetching page {page_count} (page_size={page_max_results})")

            response = service.users().messages().list(
                userId='me',
                q=query,
                maxResults=page_max_results,
                pageToken=page_token
            ).execute()

            messages = response.get('messages', [])
            logger.info(f"Page {page_count}: Found {len(messages)} message(s)")

            for i, msg in enumerate(messages):
                msg_id = msg['id']
                if msg_id in seen_ids:
                    continue
                seen_ids.add(msg_id)

                logger.debug(f"Processing message {i+1}/{len(messages)}: {msg_id}")
                msg_detail = service.users().messages().get(
                    userId='me',
                    id=msg_id,
                    format='metadata',
                    metadataHeaders=['From', 'Subject']
                ).execute()

                headers = {h['name'].lower(): h['value'] for h in msg_detail.get('payload', {}).get('headers', [])}
                sender = headers.get('from', 'Unknown')
                subject = headers.get('subject', 'No Subject')

                emails.append({
                    'id': msg_id,
                    'threadId': msg.get('threadId'),
                    'sender': sender,
                    'subject': subject,
                    'internalDate': msg_detail.get('internalDate')
                })
                logger.debug(f"  Added: {sender[:50]}... - {subject[:50]}...")

            if max_results is not None and len(emails) >= max_results:
                logger.info(f"Reached maximum results limit: {max_results}")
                break

            page_token = response.get('nextPageToken')
            if not page_token:
                logger.debug("No more pages available")
                break

    except Exception as e:
        logger.error(f"Error searching emails: {e}")
        raise

    logger.info(f"Email search completed. Total unique emails found: {len(emails)}")
    return emails if max_results is None else emails[:max_results]


@retry_gmail
def list_attachments(service, message_id: str) -> List[Dict[str, Any]]:
    """
    List PDF attachments in a message.
    
    Args:
        service: Authenticated Gmail API service object.
        message_id: Gmail message ID.
    
    Returns:
        List of attachment metadata dictionaries with keys:
        - 'attachmentId': Gmail attachment ID
        - 'filename': Attachment filename
        - 'mimeType': MIME type
        - 'size': Size in bytes
    """
    try:
        message = service.users().messages().get(
            userId='me',
            id=message_id,
            format='full'
        ).execute()
    except Exception as e:
        logger.error(f"Error retrieving message {message_id}: {e}")
        raise
    
    attachments = []
    
    def traverse_parts(parts):
        for part in parts:
            if part.get('parts'):
                traverse_parts(part['parts'])
            
            if part.get('filename') and part.get('body', {}).get('attachmentId'):
                filename = part['filename'].lower()
                mime_type = part.get('mimeType', '')
                
                # Check if it's a PDF
                if filename.endswith('.pdf') or mime_type == 'application/pdf':
                    attachments.append({
                        'attachmentId': part['body']['attachmentId'],
                        'filename': part['filename'],
                        'mimeType': mime_type,
                        'size': part.get('body', {}).get('size', 0)
                    })
    
    payload = message.get('payload', {})
    if payload.get('parts'):
        traverse_parts(payload['parts'])
    elif payload.get('filename') and payload.get('body', {}).get('attachmentId'):
        filename = payload['filename'].lower()
        mime_type = payload.get('mimeType', '')
        if filename.endswith('.pdf') or mime_type == 'application/pdf':
            attachments.append({
                'attachmentId': payload['body']['attachmentId'],
                'filename': payload['filename'],
                'mimeType': mime_type,
                'size': payload.get('body', {}).get('size', 0)
            })
    
    logger.info(f"Found {len(attachments)} PDF attachments in message {message_id}")
    return attachments


if __name__ == '__main__':
    # Simple test when run directly
    import sys
    from src.auth.gmail_auth import get_gmail_service
    
    logging.basicConfig(level=logging.INFO)
    
    try:
        service = get_gmail_service()
        emails = search_emails(service, max_results=5)
        print(f"Found {len(emails)} emails")
        for i, email in enumerate(emails):
            print(f"{i+1}. {email['sender']} - {email['subject']}")
            attachments = list_attachments(service, email['id'])
            print(f"   PDF attachments: {len(attachments)}")
    except Exception as e:
        print(f"Test failed: {e}")
        sys.exit(1)