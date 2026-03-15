import os
import logging
import re
import hashlib
import base64
import json
import tempfile
from email.utils import parseaddr
from typing import List, Dict, Any, Optional
from src.core.config import DOWNLOAD_DIR, get_bank_password
from src.parsing.pdf.pdf_to_text import extract_text_from_pdf
from src.support.retry import retry_gmail
from src.integrations.gmail.fetch import list_attachments

logger = logging.getLogger(__name__)


def extract_sender_tag(sender: str) -> str:
    """
    Extract a meaningful tag from sender email address for filename prefix.
    Prioritizes bank/business identification over generic domain parts.
    
    Args:
        sender: Email address string.
    
    Returns:
        Clean tag string (lowercase, alphanumeric and underscores only).
    """
    # Extract domain part after @
    if '@' not in sender:
        # Clean the whole string if no @ found
        tag = re.sub(r'[^a-zA-Z0-9]', '_', sender).lower()
        return tag[:30] if tag else 'unknown'
    
    domain = sender.split('@')[1]
    
    # Bank/company domain mapping for better identification
    # Key patterns in domain -> preferred tag
    domain_patterns = {
        # HSBC Singapore patterns (more precise)
        r'mail\.hsbc\.com\.sg$': 'hsbc_sg_mail',
        r'hsbc\.com\.sg$': 'hsbc_sg',
        
        # HSBC Taiwan patterns (more precise)
        r'cards\.estatements\.hsbc\.com\.tw$': 'hsbc_tw_cards',
        r'estatements\.hsbc\.com\.tw$': 'hsbc_tw_estatements',
        r'hsbc\.com\.tw$': 'hsbc_tw',
        
        # Generic HSBC patterns (fallback)
        r'hsbc\.': 'hsbc',
        
        # Fubon patterns
        r'bhu\.taipeifubon\.com\.tw$': 'fubon_tw_bhu',
        r'taipeifubon\.com\.tw$': 'fubon_tw',
        r'fubon\.': 'fubon',
        
        # Esun Bank patterns
        r'esunbank\.com$': 'esunbank',
        
        # Common financial patterns
        r'bank\.': '_bank',
        r'financial\.': '_financial',
        r'credit\.': '_credit',
        r'estatements\.': 'estatements_',
        
        # Generic company patterns
        r'apple\.com$': 'apple',
        r'uber\.com$': 'uber',
        r'amazon\.com$': 'amazon',
    }
    
    # Try to match known patterns first
    for pattern, preferred_tag in domain_patterns.items():
        if re.search(pattern, domain, re.IGNORECASE):
            # Clean the preferred tag
            clean_tag = re.sub(r'[^a-zA-Z0-9_]', '_', preferred_tag).lower()
            return clean_tag[:30] if clean_tag else 'unknown'
    
    # Fallback: extract meaningful parts from domain
    domain_parts = domain.split('.')
    
    # Remove common email prefixes (mail., service., no-reply., etc.)
    filtered_parts = []
    for part in domain_parts:
        if part.lower() not in ['mail', 'service', 'no-reply', 'noreply', 'billing', 
                               'receipts', 'support', 'info', 'contact', 'admin',
                               'cards', 'estatement', 'estatements']:
            filtered_parts.append(part)
    
    # If we filtered everything out, use original parts
    if not filtered_parts:
        filtered_parts = domain_parts
    
    # Build tag from remaining parts (max 3 parts)
    if len(filtered_parts) >= 2:
        # For domains like "mail.hsbc.com.sg", take "hsbc" and "sg"
        if len(filtered_parts) >= 3:
            # Take second-to-last and last parts (e.g., "hsbc" and "sg")
            tag_parts = [filtered_parts[-2], filtered_parts[-1]]
        else:
            tag_parts = filtered_parts
    else:
        tag_parts = filtered_parts
    
    # Join with underscores and clean
    tag = '_'.join(tag_parts)
    tag = re.sub(r'[^a-zA-Z0-9_]', '_', tag).lower()
    
    # Remove leading/trailing underscores and consecutive underscores
    tag = re.sub(r'_+', '_', tag).strip('_')
    
    if not tag:
        tag = 'unknown'
    
    return tag[:30]  # Limit length but allow more for complex domains


def extract_sender_display_name(sender: str) -> str:
    """
    Extract sender display name for filename use.

    Examples:
    - '"台北富邦銀行" <service@bhu.taipeifubon.com.tw>' -> '台北富邦銀行'
    - 'cards@estatements.hsbc.com.tw' -> 'cards'
    """
    display_name, email_addr = parseaddr(sender or "")
    name = (display_name or "").strip().strip('"')

    if not name:
        if '@' in email_addr:
            name = email_addr.split('@', 1)[0]
        else:
            name = (sender or 'unknown').strip()

    # Keep CJK, latin, number, underscore, dash. Replace others with underscore.
    safe = re.sub(r'[^\w\-\u4e00-\u9fff]', '_', name)
    safe = re.sub(r'_+', '_', safe).strip('_')
    return (safe or 'unknown')[:40]


def build_sender_base64_suffix(sender_name: str) -> str:
    """
    Create base64 suffix using sender name and return last 8 chars.

    Note: Keep '=' padding as requested.
    """
    encoded = base64.urlsafe_b64encode((sender_name or 'unknown').encode('utf-8')).decode('ascii')
    if not encoded:
        encoded = 'unknown'
    return encoded[-8:]


def build_file_base64_suffix(file_data: bytes) -> str:
    """
    Create stable suffix from file content hash and return last 8 chars.

    Why not use raw file base64 tail directly?
    - Many PDFs end with very similar bytes (e.g., %%EOF), so tail8 can collide.

    We hash first (SHA-256), then base64-encode hash bytes to get a high-entropy suffix.
    """
    if not file_data:
        return 'unknown='

    digest = hashlib.sha256(file_data).digest()
    encoded = base64.urlsafe_b64encode(digest).decode('ascii')
    if not encoded:
        encoded = 'unknown='
    return encoded[-8:]


def build_hash10_suffix(file_data: bytes) -> str:
    if not file_data:
        return "0000000000"
    digest = hashlib.sha256(file_data).digest()
    value = int.from_bytes(digest[:8], "big") % 10_000_000_000
    return f"{value:010d}"


def _sanitize_filename_component(value: str, fallback: str = "unknown") -> str:
    text = re.sub(r'[^\w\-\u4e00-\u9fff（）()]', '_', value or "")
    text = re.sub(r'_+', '_', text).strip('_')
    return (text or fallback)[:80]


def _extract_year_month(text: str) -> Optional[str]:
    if not text:
        return None

    # Try explicit Year/Month patterns first (e.g., 2023年10月, 2023-10)
    patterns = [
        re.search(r'(?P<year>\d{4})年\s*(?P<month>\d{1,2})月', text),
        re.search(r'(?P<year>\d{4})[/-](?P<month>\d{1,2})', text),
        re.search(r'(?P<roc>\d{3})年\s*(?P<month>\d{1,2})月', text),
    ]
    for match in patterns:
        if not match:
            continue
        if "roc" in match.groupdict() and match.group("roc"):
            year = int(match.group("roc")) + 1911
        else:
            year = int(match.group("year"))
        month = int(match.group("month"))
        if 1 <= month <= 12:
            return f"{year:04d}-{month:02d}"

    # Try DD-MM-YYYY or YYYY-MM-DD in filename/subject
    date_match = re.search(r'(?P<p1>\d{2,4})[-_](?P<p2>\d{2})[-_](?P<p3>\d{2,4})', text)
    if date_match:
        p1, p2, p3 = date_match.group("p1"), date_match.group("p2"), date_match.group("p3")
        # Case 1: YYYY-MM-DD
        if len(p1) == 4 and 1 <= int(p2) <= 12:
            return f"{p1}-{p2}"
        # Case 2: DD-MM-YYYY
        if len(p3) == 4 and 1 <= int(p2) <= 12:
            return f"{p3}-{p2}"

    return None


def _infer_bank_label(text: str) -> Optional[str]:
    checks = [
        ("滙豐(台灣)", ["匯豐(台灣)", "滙豐(台灣)", "hsbc taiwan"]),
        ("HSBC_SG", ["hsbc bank (singapore)", "hsbc singapore", "visa revolution"]),
        ("DBS_SG", ["dbs bank", "dbs account", "consolidated statement", "account summary"]),
        ("台新銀行", ["台新銀行"]),
        ("台北富邦銀行", ["台北富邦銀行", "taipei fubon"]),
        ("玉山銀行", ["玉山銀行", "esun"]),
        ("永豐銀行", ["永豐銀行", "sinopac"]),
        ("第一銀行", ["第一銀行", "first bank"]),
        ("Revolut", ["revolut"]),
    ]
    lowered = text.lower()
    for label, keywords in checks:
        if any(keyword.lower() in lowered for keyword in keywords):
            return label
    return None


def _infer_statement_type(text: str) -> Optional[str]:
    lowered = text.lower()
    if any(keyword in lowered for keyword in ['綜合對帳單', '銀行對帳單', '運籌理財對帳單', '銀行帳戶', 'account statement']):
        return '銀行帳戶對帳單'
    if any(keyword in lowered for keyword in ['信用卡', 'credit card', 'visa revolution', 'card statement']):
        return '信用卡帳單'
    return None


def _extract_pdf_text_hint(file_data: bytes, sender: str, ext: str) -> str:
    if ext != '.pdf' or not file_data:
        return ""

    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp.write(file_data)
        tmp_path = tmp.name

    try:
        # 1) Try specific passwords for this sender
        passwords = get_bank_password(sender) or [None]
        for password in passwords:
            text = extract_text_from_pdf(tmp_path, password)
            if text and text.strip():
                return text
        
        # 2) Fallback: If sender is generic (e.g., self), try ALL known bank passwords
        from src.core.config import get_all_bank_passwords
        all_passwords = get_all_bank_passwords()
        if all_passwords:
            logger.debug(f"Trying all known bank passwords for identification: {len(all_passwords)} variants")
            for password in all_passwords:
                if password in passwords: continue # Skip if already tried
                try:
                    text = extract_text_from_pdf(tmp_path, password)
                    if text and text.strip():
                        return text
                except Exception:
                    continue
    except Exception:
        return ""
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    return ""


def build_pdf_filename_by_sender(
    sender: str,
    original_filename: str,
    file_data: bytes = b'',
    subject: str = '',
) -> str:
    """
    Build filename as: <sender_label>_<statement_label>_<hash10><ext>
    """
    ext = os.path.splitext(os.path.basename(original_filename or ''))[1].lower()
    if not ext:
        ext = '.pdf'
    original_stem = os.path.splitext(os.path.basename(original_filename or 'statement'))[0]

    hint_text = " ".join(part for part in [subject, original_filename] if part)
    extracted_hint = _extract_pdf_text_hint(file_data, sender, ext)
    sender_label = _infer_bank_label(hint_text) or _infer_bank_label(extracted_hint) or extract_sender_display_name(sender)
    statement_type = _infer_statement_type(hint_text) or _infer_statement_type(extracted_hint)
    year_month = _extract_year_month(hint_text) or _extract_year_month(extracted_hint)

    if statement_type and year_month:
        statement_label = f"{statement_type}_{year_month}"
    elif statement_type:
        statement_label = statement_type
    elif year_month:
        statement_label = f"{original_stem}_{year_month}"
    else:
        statement_label = original_stem

    hash10 = build_hash10_suffix(file_data)

    return (
        f"{_sanitize_filename_component(sender_label)}_"
        f"{_sanitize_filename_component(statement_label, 'statement')}_"
        f"{hash10}{ext}"
    )


def compute_md5_hash(data: bytes) -> str:
    """Compute MD5 hash of binary data."""
    return hashlib.md5(data).hexdigest()


def get_existing_file_by_md5(target_md5: str, directory: str = DOWNLOAD_DIR) -> Optional[str]:
    """
    Check if a file with the same MD5 hash already exists in directory.
    Uses an efficient local cache to avoid re-scanning all files.
    
    Args:
        target_md5: MD5 hash to search for.
        directory: Directory to search in.
    
    Returns:
        Path to existing file with matching MD5, or None if not found.
    """
    if not os.path.exists(directory):
        return None
    
    cache_path = os.path.join(directory, ".md5_cache.json")
    md5_cache = {}
    
    if os.path.exists(cache_path):
        try:
            with open(cache_path, 'r') as f:
                md5_cache = json.load(f)
        except Exception:
            pass
            
    # Check if target_md5 is in cache
    for filename, cached_md5 in md5_cache.items():
        if cached_md5 == target_md5:
            filepath = os.path.join(directory, filename)
            if os.path.isfile(filepath):
                return filepath

    # If not in cache, scan directory but only for files not in cache
    # or whose mtime has changed. For simplicity, we'll just scan missing files.
    updated = False
    for filename in os.listdir(directory):
        if filename.startswith('.') or filename == ".md5_cache.json":
            continue
            
        filepath = os.path.join(directory, filename)
        if os.path.isfile(filepath) and filename not in md5_cache:
            try:
                with open(filepath, 'rb') as f:
                    file_md5 = hashlib.md5(f.read()).hexdigest()
                    md5_cache[filename] = file_md5
                    updated = True
                    if file_md5 == target_md5:
                        # Continue scanning to build cache but we found it
                        pass 
            except Exception:
                continue
    
    if updated:
        try:
            with open(cache_path, 'w') as f:
                json.dump(md5_cache, f)
        except Exception:
            pass
            
    # Re-check after update
    for filename, cached_md5 in md5_cache.items():
        if cached_md5 == target_md5:
            filepath = os.path.join(directory, filename)
            if os.path.isfile(filepath):
                return filepath
                
    return None


@retry_gmail
def download_attachment(
    service,
    message_id: str,
    attachment_info: Dict[str, Any],
    sender: str = None,
    subject: str = '',
) -> str:
    """
    Download a single attachment from Gmail with retry mechanism.
    
    Args:
        service: Authenticated Gmail API service object.
        message_id: Gmail message ID.
        attachment_info: Attachment metadata from list_attachments().
        sender: Sender header string; used to generate filename.
    
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
        file_data = base64.urlsafe_b64decode(attachment['data'].encode('UTF-8'))
        
        # Compute MD5 hash of file content
        file_md5 = compute_md5_hash(file_data)
        logger.debug(f"Attachment MD5: {file_md5}")
        
        # Check if file with same content already exists
        existing_file = get_existing_file_by_md5(file_md5)
        if existing_file:
            logger.info(f"Skipping download: identical file already exists at {existing_file}")
            return existing_file
        
        # Ensure download directory exists
        os.makedirs(DOWNLOAD_DIR, exist_ok=True)
        
        # Generate filename by user rule: sender_name + base64_tail8(file content)
        original_filename = attachment_info['filename']
        safe_filename = build_pdf_filename_by_sender(
            sender or 'unknown',
            original_filename,
            file_data,
            subject=subject,
        )
        
        filepath = os.path.join(DOWNLOAD_DIR, safe_filename)
        
        # Handle duplicate filenames (by name, not content)
        base, ext = os.path.splitext(filepath)
        counter = 1
        while os.path.exists(filepath):
            filepath = f"{base}_{counter}{ext}"
            counter += 1
        
        # Write file
        with open(filepath, 'wb') as f:
            f.write(file_data)
        
        logger.info(f"Downloaded: {filepath} ({len(file_data)} bytes, MD5: {file_md5})")
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
    if email_metadata is None:
        email_metadata = {}
    
    sender = email_metadata.get('sender', 'Unknown')
    subject = email_metadata.get('subject', 'No Subject')
    
    # Extract sender tag for filename prefixing
    sender_tag = extract_sender_tag(sender)
    logger.info(f"Processing attachments from: {sender} ({sender_tag}) - {subject}")
    
    downloaded_files = []
    attachments = list_attachments(service, message_id)
    
    for att in attachments:
        try:
            filepath = download_attachment(service, message_id, att, sender, subject)
            downloaded_files.append({
                'filepath': filepath,
                'filename': att['filename'],
                'sender': sender,
                'sender_tag': sender_tag,
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
            # Propagate to caller so run summary can reflect errors accurately
            raise
    
    logger.info(f"Total downloaded PDFs: {len(all_downloaded)}")
    return all_downloaded


if __name__ == '__main__':
    # Simple test when run directly
    import sys
    from src.integrations.gmail.auth import get_gmail_service
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
