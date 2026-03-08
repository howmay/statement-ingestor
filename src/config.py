import os
from dotenv import load_dotenv

load_dotenv()

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

DOWNLOAD_DIR = os.path.join(os.path.dirname(__file__), "..", "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
