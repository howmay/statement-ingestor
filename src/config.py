import os
import json
import logging
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# OAuth2 Configuration
OAUTH_CLIENT_SECRETS_PATH = os.getenv("OAUTH_CLIENT_SECRETS_PATH", "config/client_secrets.json")
OAUTH_TOKEN_PATH = os.getenv("OAUTH_TOKEN_PATH", "config/token.json")
OAUTH_PORT = int(os.getenv("OAUTH_PORT", "8080"))

# Search Criteria (configurable via environment variables)
# Format: comma-separated email addresses
TARGET_SENDERS_STR = os.getenv("TARGET_SENDERS", "billing@apple.com,receipts@uber.com,no-reply@amazon.com")
TARGET_SENDERS = [s.strip() for s in TARGET_SENDERS_STR.split(",") if s.strip()]

# Keywords that must appear in subject or body
# Format: comma-separated keywords
TARGET_KEYWORDS_STR = os.getenv("TARGET_KEYWORDS", "receipt,invoice,billing,收據,發票")
TARGET_KEYWORDS = [k.strip() for k in TARGET_KEYWORDS_STR.split(",") if k.strip()]

# Bank passwords for encrypted PDFs
# Format: JSON string or key=value pairs
# Example JSON: {"hsbc": "A123456789", "fubon": "B987654321", "esunbank": "C111111111"}
BANK_PASSWORDS_JSON = os.getenv("BANK_PASSWORDS", "{}")
BANK_PASSWORDS = {}

try:
    BANK_PASSWORDS = json.loads(BANK_PASSWORDS_JSON)
    if not isinstance(BANK_PASSWORDS, dict):
        logger.warning("BANK_PASSWORDS should be a JSON dictionary, got %s", type(BANK_PASSWORDS))
        BANK_PASSWORDS = {}
except json.JSONDecodeError:
    # Fallback: try parsing as key=value pairs separated by commas
    logger.warning("BANK_PASSWORDS is not valid JSON, trying key=value format")
    try:
        pairs = BANK_PASSWORDS_JSON.split(",")
        for pair in pairs:
            if "=" in pair:
                key, value = pair.split("=", 1)
                BANK_PASSWORDS[key.strip()] = value.strip()
    except Exception:
        logger.warning("Failed to parse BANK_PASSWORDS, using empty dict")
        BANK_PASSWORDS = {}

DOWNLOAD_DIR = os.path.join(os.path.dirname(__file__), "..", "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)


def get_bank_password(sender: str) -> str:
    """
    Get password for a bank PDF based on sender email address.
    
    Args:
        sender: Email address string.
    
    Returns:
        Password string or empty string if no password configured.
    """
    if not sender or '@' not in sender:
        return ""
    
    domain = sender.split('@')[1].lower()
    
    # Map domain patterns to bank keys (more precise for HSBC)
    domain_to_bank = {
        # HSBC Singapore patterns
        "mail.hsbc.com.sg": "hsbc_sg",
        "hsbc.com.sg": "hsbc_sg",
        
        # HSBC Taiwan patterns
        "estatements.hsbc.com.tw": "hsbc_tw",
        "cards.estatements.hsbc.com.tw": "hsbc_tw",
        "hsbc.com.tw": "hsbc_tw",
        
        # Fubon patterns
        "bhu.taipeifubon.com.tw": "fubon",
        "taipeifubon.com.tw": "fubon",
        
        # Esun Bank patterns
        "esunbank.com": "esunbank",
        
        # Generic mapping by domain part (fallback)
        "hsbc": "hsbc",
        "fubon": "fubon",
        "esunbank": "esunbank",
    }
    
    # Find matching bank key
    bank_key = None
    for pattern, key in domain_to_bank.items():
        if pattern in domain:
            bank_key = key
            break
    
    if not bank_key:
        # Try to extract bank name from domain
        domain_parts = domain.split('.')
        for part in domain_parts:
            if part in BANK_PASSWORDS:
                bank_key = part
                break
    
    # Try to get password with fallback logic
    password_keys_to_try = []
    
    if bank_key:
        # Add the specific bank key first
        password_keys_to_try.append(bank_key)
        
        # Add fallback keys based on bank type
        if bank_key in ['hsbc_sg', 'hsbc_tw']:
            password_keys_to_try.append('hsbc')
        elif bank_key in ['fubon_tw', 'fubon']:
            password_keys_to_try.append('fubon')
        elif bank_key in ['esunbank']:
            password_keys_to_try.append('esunbank')
    
    # Try each key in order
    for key in password_keys_to_try:
        if key in BANK_PASSWORDS:
            password = BANK_PASSWORDS[key]
            logger.debug(f"Found password for bank '{key}' (sender: {sender})")
            return password
    
    logger.debug(f"No password configured for sender: {sender}")
    return ""
