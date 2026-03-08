import os
import sys
from src.config import TARGET_SENDERS, TARGET_KEYWORDS, DOWNLOAD_DIR
from src.auth.gmail_auth import get_gmail_service
# Temporarily keep imports for future steps (will be replaced in Step 3+)
from src.gmail_client import GmailClient
from src.pdf_extractor import PDFExtractor
from src.parser_factory import get_parser
from src.csv_exporter import CSVExporter

def main():
    print("Starting Gmail Receipt & Invoice Extractor (MVP) with OAuth2...")
    
    # Step 1: Authenticate using OAuth2
    try:
        service = get_gmail_service()
        profile = service.users().getProfile(userId='me').execute()
        print(f"✓ Authenticated as: {profile.get('emailAddress')}")
    except Exception as e:
        print(f"✗ Authentication failed: {e}")
        print("\nPlease ensure you have:")
        print("1. Created a Google Cloud project with Gmail API enabled")
        print("2. Configured OAuth2 desktop client credentials")
        print("3. Placed client_secrets.json in config/ directory")
        sys.exit(1)
    
    print("\n⚠️  Full email processing not yet implemented.")
    print("   This will be completed in Step 3 (Email filtering & PDF download).")
    print("   Exiting demo mode.")
    
    # TODO: Step 3 will implement:
    # 1. Search emails using Gmail API (service.users().messages().list())
    # 2. Download PDF attachments
    # 3. Extract text, parse with LLM, export CSV

if __name__ == "__main__":
    main()
