import os
import json
import logging
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


DEFAULT_STATEMENT_SEARCH_PROFILES = [
    {
        "name": "hsbc-card",
        "senders": ["cards@estatements.hsbc.com.tw"],
        "subject_keywords": ["信用卡帳單", "電子帳單", "eStatement"],
        "exclude_keywords": ["OTP", "驗證", "活動", "廣告"],
        "has_pdf_attachment": True,
    },
    {
        "name": "fubon-bank",
        "senders": ["service@bhu.taipeifubon.com.tw"],
        "subject_keywords": ["銀行對帳單", "對帳單", "電子對帳單"],
        "exclude_keywords": ["OTP", "驗證", "活動", "廣告"],
        "has_pdf_attachment": True,
    },
    {
        "name": "fubon-card",
        "senders": ["creditcard@taipeifubon.com.tw"],
        "subject_keywords": ["信用卡", "信用卡帳單", "電子帳單"],
        "exclude_keywords": ["OTP", "驗證", "活動", "廣告"],
        "has_pdf_attachment": True,
    },
    {
        "name": "esun-card",
        "senders": ["estatement@esunbank.com"],
        "subject_keywords": ["信用卡", "電子帳單", "帳單"],
        "exclude_keywords": ["OTP", "驗證", "活動", "廣告"],
        "has_pdf_attachment": True,
    },
    {
        "name": "sinopac-card",
        "senders": ["ebillservice@newebill.banksinopac.com.tw"],
        "subject_keywords": ["信用卡", "電子帳單", "帳單"],
        "exclude_keywords": ["OTP", "驗證", "活動", "廣告"],
        "has_pdf_attachment": True,
    },
    {
        "name": "hsbc-sg",
        "senders": ["hsbc.com.sg", "hsbc_sg"],
        "subject_keywords": ["Statement", "Composite", "Credit Card"],
        "exclude_keywords": ["OTP", "驗證", "活動", "廣告"],
        "has_pdf_attachment": True,
    },
    {
        "name": "dbs-sg",
        "senders": ["dbs.com.sg", "dbs bank"],
        "subject_keywords": ["Statement", "Account", "Credit Card"],
        "exclude_keywords": ["OTP", "驗證", "活動", "廣告"],
        "has_pdf_attachment": True,
    },
    {
        "name": "generic-statement",
        "senders": [],
        "subject_keywords": ["statement", "對帳單", "信用卡帳單", "銀行對帳單", "transaction detail"],
        "exclude_keywords": ["保單", "人壽", "活動通知", "核卡通知", "應付憑據"],
        "has_pdf_attachment": True,
    },
]


def _normalize_statement_profile(profile: dict, index: int) -> dict:
    senders = [str(v).strip() for v in profile.get("senders", []) if str(v).strip()]
    subject_keywords = [
        str(v).strip() for v in profile.get("subject_keywords", []) if str(v).strip()
    ]
    exclude_keywords = [
        str(v).strip() for v in profile.get("exclude_keywords", []) if str(v).strip()
    ]

    return {
        "name": str(profile.get("name") or f"profile-{index}").strip(),
        "senders": senders,
        "subject_keywords": subject_keywords,
        "exclude_keywords": exclude_keywords,
        "has_pdf_attachment": bool(profile.get("has_pdf_attachment", True)),
    }


def _load_statement_search_profiles() -> list[dict]:
    raw = os.getenv("STATEMENT_SEARCH_PROFILES", "").strip()
    if not raw:
        return [_normalize_statement_profile(profile, idx) for idx, profile in enumerate(DEFAULT_STATEMENT_SEARCH_PROFILES, start=1)]

    try:
        parsed = json.loads(raw)
        if not isinstance(parsed, list):
            raise ValueError("STATEMENT_SEARCH_PROFILES must be a JSON array")
        profiles = []
        for idx, item in enumerate(parsed, start=1):
            if isinstance(item, dict):
                profiles.append(_normalize_statement_profile(item, idx))
        if profiles:
            return profiles
    except Exception as exc:
        logger.warning("Failed to parse STATEMENT_SEARCH_PROFILES: %s", exc)

    return [_normalize_statement_profile(profile, idx) for idx, profile in enumerate(DEFAULT_STATEMENT_SEARCH_PROFILES, start=1)]

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

STATEMENT_SEARCH_PROFILES = _load_statement_search_profiles()

# Bank passwords for encrypted PDFs: "pass1,pass2" (a legacy "name=pass" form keeps only the part after "=")
BANK_PASSWORDS = [p.split('=', 1)[-1].strip() for p in os.getenv("BANK_PASSWORDS", "").split(",") if p.strip()]

DOWNLOAD_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "downloads")
)
os.makedirs(DOWNLOAD_DIR, exist_ok=True)


def get_bank_password(sender: str) -> list[str]:
    """Return every configured PDF password; sender is ignored."""
    return list(BANK_PASSWORDS)
