import logging
from typing import List, Dict, Any
from src.config import TARGET_SENDERS, TARGET_KEYWORDS

logger = logging.getLogger(__name__)


def build_gmail_query(senders: List[str], keywords: List[str]) -> str:
    """
    Build a Gmail API search query from senders and keywords.
    
    Args:
        senders: List of sender email addresses.
        keywords: List of keywords to search in subject/body.
    
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
    
    final_query = " ".join(query_parts)
    logger.debug(f"Built Gmail query: {final_query}")
    logger.debug(f"  - Senders: {senders}")
    logger.debug(f"  - Keywords: {keywords}")
    return final_query


def search_emails(service, senders=None, keywords=None, max_results=100) -> List[Dict[str, Any]]:
    """
    Search emails using Gmail API.
    
    Args:
        service: Authenticated Gmail API service object.
        senders: List of sender email addresses (defaults to TARGET_SENDERS).
        keywords: List of keywords (defaults to TARGET_KEYWORDS).
        max_results: Maximum number of emails to return.
    
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
    logger.info(f"  - Max results: {max_results}")
    
    query = build_gmail_query(senders, keywords)
    logger.info(f"Searching emails with query: {query}")
    
    emails = []
    page_token = None
    page_count = 0
    
    try:
        while True:
            page_count += 1
            page_max_results = min(50, max_results - len(emails))
            logger.debug(f"Fetching page {page_count} (max {page_max_results} results)")
            
            # Call the Gmail API
            response = service.users().messages().list(
                userId='me',
                q=query,
                maxResults=page_max_results,
                pageToken=page_token
            ).execute()
            
            messages = response.get('messages', [])
            logger.info(f"Page {page_count}: Found {len(messages)} messages")
            
            for i, msg in enumerate(messages):
                logger.debug(f"Processing message {i+1}/{len(messages)}: {msg['id']}")
                # Get full message metadata (lightweight, not full content)
                msg_detail = service.users().messages().get(
                    userId='me',
                    id=msg['id'],
                    format='metadata',
                    metadataHeaders=['From', 'Subject']
                ).execute()
                
                # Extract headers
                headers = {h['name'].lower(): h['value'] for h in msg_detail.get('payload', {}).get('headers', [])}
                sender = headers.get('from', 'Unknown')
                subject = headers.get('subject', 'No Subject')
                
                emails.append({
                    'id': msg['id'],
                    'threadId': msg.get('threadId'),
                    'sender': sender,
                    'subject': subject,
                    'internalDate': msg_detail.get('internalDate')
                })
                logger.debug(f"  Added: {sender[:50]}... - {subject[:50]}...")
            
            # Check if we have enough results or reached end
            if len(emails) >= max_results:
                logger.info(f"Reached maximum results limit: {max_results}")
                break
                
            page_token = response.get('nextPageToken')
            if not page_token:
                logger.debug(f"No more pages available")
                break
                
    except Exception as e:
        logger.error(f"Error searching emails: {e}")
        raise
    
    logger.info(f"Email search completed. Total emails found: {len(emails)}")
    return emails[:max_results]


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
        return []
    
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