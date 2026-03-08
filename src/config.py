import os
from dotenv import load_dotenv

load_dotenv()

# OAuth2 Configuration
OAUTH_CLIENT_SECRETS_PATH = os.getenv("OAUTH_CLIENT_SECRETS_PATH", "config/client_secrets.json")
OAUTH_TOKEN_PATH = os.getenv("OAUTH_TOKEN_PATH", "config/token.json")

# Search Criteria
TARGET_SENDERS = [
    "billing@apple.com",
    "receipts@uber.com",
    "no-reply@amazon.com"
]

# Keywords that must appear in subject or body
TARGET_KEYWORDS = [
    "receipt",
    "invoice",
    "billing",
    "收據",
    "發票"
]

DOWNLOAD_DIR = os.path.join(os.path.dirname(__file__), "..", "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
