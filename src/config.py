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
# Format: comma-separated list of passwords (simple mode)
# Example: "password1,password2,password3"
# Legacy format (key=value pairs) also supported for backward compatibility
BANK_PASSWORDS_STR = os.getenv("BANK_PASSWORDS", "")
BANK_PASSWORDS = []

if BANK_PASSWORDS_STR:
    # Try to parse as simple comma-separated list first
    if "=" not in BANK_PASSWORDS_STR:
        # Simple list format: "pass1,pass2,pass3"
        passwords = [p.strip() for p in BANK_PASSWORDS_STR.split(",") if p.strip()]
        BANK_PASSWORDS = passwords
        logger.info(f"Loaded {len(BANK_PASSWORDS)} passwords from simple list")
    else:
        # Legacy key=value format for backward compatibility
        # Convert to list of passwords (ignoring keys)
        try:
            passwords = []
            pairs = BANK_PASSWORDS_STR.split(",")
            for pair in pairs:
                if "=" in pair:
                    key, value = pair.split("=", 1)
                    passwords.append(value.strip())
                else:
                    # Handle edge case: password containing "="
                    passwords.append(pair.strip())
            BANK_PASSWORDS = passwords
            logger.info(f"Loaded {len(BANK_PASSWORDS)} passwords from legacy key=value format")
        except Exception:
            logger.warning("Failed to parse BANK_PASSWORDS, using empty list")
            BANK_PASSWORDS = []
else:
    logger.debug("No BANK_PASSWORDS configured")

DOWNLOAD_DIR = os.path.join(os.path.dirname(__file__), "..", "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)


def get_passwords() -> list[str]:
    """
    Get list of passwords to try for encrypted PDFs.
    
    Returns:
        List of password strings to try in order.
    """
    return BANK_PASSWORDS.copy()


def get_bank_password(sender: str) -> list[str]:
    """
    Get passwords for a bank PDF (legacy function for backward compatibility).
    Now returns list of all passwords regardless of sender.
    
    Args:
        sender: Email address string (ignored in new simple mode).
    
    Returns:
        List of password strings to try in order.
    """
    logger.debug(f"Getting passwords for sender: {sender}")
    return get_passwords()
