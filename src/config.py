import os
from dotenv import load_dotenv

load_dotenv()

# For MVP, we can support a single account via env, 
# or multiple if we parse a JSON string. We'll start with one for simplicity.
GMAIL_USER = os.getenv("GMAIL_USER", "example@gmail.com")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "")

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
