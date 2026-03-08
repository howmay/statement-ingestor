import os
import sys
from src.config import GMAIL_USER, GMAIL_APP_PASSWORD, TARGET_SENDERS, TARGET_KEYWORDS, DOWNLOAD_DIR
from src.gmail_client import GmailClient

def main():
    if not GMAIL_USER or not GMAIL_APP_PASSWORD:
        print("Please configure GMAIL_USER and GMAIL_APP_PASSWORD in .env or environment variables.")
        sys.exit(1)

    print(f"Starting Gmail Receipt & Invoice Extractor (MVP) for {GMAIL_USER}...")
    
    client = GmailClient(username=GMAIL_USER, password=GMAIL_APP_PASSWORD)
    client.connect()

    if not client.mail:
        sys.exit("Failed to connect to Gmail. Exiting.")

    print(f"Searching for emails from: {TARGET_SENDERS}")
    
    message_ids = client.search_emails(TARGET_SENDERS, TARGET_KEYWORDS)
    print(f"Found {len(message_ids)} matching email(s).")
    
    total_downloaded = 0
    for msg_id in message_ids:
        # Download PDFs
        files = client.fetch_and_extract_pdfs(msg_id, DOWNLOAD_DIR, TARGET_KEYWORDS)
        total_downloaded += len(files)

    print(f"Extraction complete. Downloaded {total_downloaded} PDF(s) to {DOWNLOAD_DIR}")
    client.close()

if __name__ == "__main__":
    main()
