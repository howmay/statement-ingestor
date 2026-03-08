import os
import sys
from src.config import GMAIL_USER, GMAIL_APP_PASSWORD, TARGET_SENDERS, TARGET_KEYWORDS, DOWNLOAD_DIR
from src.gmail_client import GmailClient
from src.pdf_extractor import PDFExtractor

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
    
    extracted_data = []

    for msg_id in message_ids:
        # Download PDFs
        files = client.fetch_and_extract_pdfs(msg_id, DOWNLOAD_DIR, TARGET_KEYWORDS)
        
        for file in files:
            print(f"Extracting text from: {file}")
            extractor = PDFExtractor(file)
            text = extractor.extract_text()
            extracted_data.append({
                "filepath": file,
                "raw_text": text
            })

    print(f"Extraction complete. Processed {len(extracted_data)} PDF(s) in {DOWNLOAD_DIR}")
    client.close()

if __name__ == "__main__":
    main()
