import os
import logging
from typing import List, Dict, Any
from src.config import DOWNLOAD_DIR

logger = logging.getLogger(__name__)


def download_attachment(service, message_id: str, attachment_info: Dict[str, Any]) -> str:
    """
    Download a single attachment from Gmail.
    
    Args:
        service: Authenticated Gmail API service object.
        message_id: Gmail message ID.
        attachment_info: Attachment metadata from list_attachments().
    
    Returns:
        Path to the downloaded file.
    
    Raises:
        Exception: If download fails.
    """
    try:
        # Get the attachment data
        attachment = service.users().messages().attachments().get(
            userId='me',
            messageId=message_id,
            id=attachment_info['attachmentId']
        ).execute()
        
        # Decode from base64
        import base64
        file_data = base64.urlsafe_b64decode(attachment['data'].encode('UTF-8'))
        
        # Ensure download directory exists
        os.makedirs(DOWNLOAD_DIR, exist_ok=True)
        
        # Generate safe filename
        original_filename = attachment_info['filename']
        # Clean filename: remove path components, limit length
        import re
        safe_filename = re.sub(r'[^\w\-_.]', '_', os.path.basename(original_filename))
        safe_filename = safe_filename[:200]  # Limit length
        
        filepath = os.path.join(DOWNLOAD_DIR, safe_filename)
        
        # Handle duplicate filenames
        base, ext = os.path.splitext(filepath)
        counter = 1
        while os.path.exists(filepath):
            filepath = f"{base}_{counter}{ext}"
            counter += 1
        
        # Write file
        with open(filepath, 'wb') as f:
            f.write(file_data)
        
        logger.info(f"Downloaded: {filepath} ({len(file_data)} bytes)")
        return filepath
        
    except Exception as e:
        logger.error(f"Failed to download attachment {attachment_info.get('filename')}: {e}")
        raise


def download_pdf_attachments(service, message_id: str, email_metadata: Dict[str, Any] = None) -> List[Dict[str, Any]]:
    """
    Download all PDF attachments from a message.
    
    Args:
        service: Authenticated Gmail API service object.
        message_id: Gmail message ID.
        email_metadata: Optional email metadata (sender, subject) for logging.
    
    Returns:
        List of dictionaries with downloaded file info:
        - 'filepath': Path to downloaded file
        - 'filename': Original filename
        - 'sender': Sender email (from metadata)
        - 'subject': Email subject (from metadata)
        - 'message_id': Gmail message ID
    """
    from .fetch_emails import list_attachments
    
    if email_metadata is None:
        email_metadata = {}
    
    sender = email_metadata.get('sender', 'Unknown')
    subject = email_metadata.get('subject', 'No Subject')
    
    logger.info(f"Processing attachments from: {sender} - {subject}")
    
    downloaded_files = []
    attachments = list_attachments(service, message_id)
    
    for att in attachments:
        try:
            filepath = download_attachment(service, message_id, att)
            downloaded_files.append({
                'filepath': filepath,
                'filename': att['filename'],
                'sender': sender,
                'subject': subject,
                'message_id': message_id
            })
        except Exception as e:
            logger.error(f"Skipping attachment {att['filename']}: {e}")
            continue
    
    logger.info(f"Downloaded {len(downloaded_files)} PDF(s) from message {message_id}")
    return downloaded_files


def batch_download_pdfs(service, email_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Download PDF attachments from multiple emails.
    
    Args:
        service: Authenticated Gmail API service object.
        email_list: List of email metadata from search_emails().
    
    Returns:
        Combined list of all downloaded file info.
    """
    all_downloaded = []
    
    for email in email_list:
        try:
            downloaded = download_pdf_attachments(service, email['id'], email)
            all_downloaded.extend(downloaded)
        except Exception as e:
            logger.error(f"Failed to process email {email['id']}: {e}")
            continue
    
    logger.info(f"Total downloaded PDFs: {len(all_downloaded)}")
    return all_downloaded


if __name__ == '__main__':
    # Simple test when run directly
    import sys
    from src.auth.gmail_auth import get_gmail_service
    from .fetch_emails import search_emails
    
    logging.basicConfig(level=logging.INFO)
    
    try:
        service = get_gmail_service()
        emails = search_emails(service, max_results=2)
        print(f"Found {len(emails)} emails for testing")
        
        if emails:
            downloaded = batch_download_pdfs(service, emails)
            print(f"Downloaded {len(downloaded)} PDF(s)")
            for i, file_info in enumerate(downloaded):
                print(f"{i+1}. {file_info['filename']} -> {file_info['filepath']}")
        else:
            print("No emails found to test download")
            
    except Exception as e:
        print(f"Test failed: {e}")
        sys.exit(1)