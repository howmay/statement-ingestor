import os
import sys
import logging
from src.config import TARGET_SENDERS, TARGET_KEYWORDS, DOWNLOAD_DIR
from src.auth.gmail_auth import get_gmail_service
from src.fetch.fetch_emails import search_emails, list_attachments
from src.fetch.download_pdfs import batch_download_pdfs
# Temporarily keep imports for future steps (will be replaced in later steps)
from src.pdf_extractor import PDFExtractor
from src.parser_factory import get_parser
from src.csv_exporter import CSVExporter

def main():
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger(__name__)
    
    print("=" * 60)
    print("Gmail Receipt & Invoice Extractor (MVP) - Step 3 Demo")
    print("=" * 60)
    
    # Step 1: Authenticate using OAuth2
    try:
        service = get_gmail_service()
        profile = service.users().getProfile(userId='me').execute()
        user_email = profile.get('emailAddress')
        print(f"✓ Authenticated as: {user_email}")
    except Exception as e:
        print(f"✗ Authentication failed: {e}")
        print("\nPlease ensure you have:")
        print("1. Created a Google Cloud project with Gmail API enabled")
        print("2. Configured OAuth2 desktop client credentials")
        print("3. Placed client_secrets.json in config/ directory")
        sys.exit(1)
    
    print("\n" + "=" * 60)
    print("Step 3: Email filtering & PDF download")
    print("=" * 60)
    
    # Step 2: Search for emails
    print("\n1. Searching for emails...")
    try:
        emails = search_emails(service, max_results=10)  # Limit to 10 for demo
        print(f"   ✓ Found {len(emails)} matching email(s)")
        
        if not emails:
            print("\n   No matching emails found with current criteria:")
            print(f"   - Senders: {TARGET_SENDERS}")
            print(f"   - Keywords: {TARGET_KEYWORDS}")
            print("\n   Exiting.")
            sys.exit(0)
            
        # Display summary of found emails
        print("\n   Email summary:")
        for i, email in enumerate(emails[:5]):  # Show first 5
            print(f"   {i+1}. From: {email['sender'][:50]}")
            print(f"      Subject: {email['subject'][:60]}...")
            attachments = list_attachments(service, email['id'])
            print(f"      PDF attachments: {len(attachments)}")
        
        if len(emails) > 5:
            print(f"   ... and {len(emails) - 5} more")
            
    except Exception as e:
        print(f"   ✗ Email search failed: {e}")
        sys.exit(1)
    
    # Step 3: Download PDF attachments
    print("\n2. Downloading PDF attachments...")
    try:
        downloaded_files = batch_download_pdfs(service, emails)
        print(f"   ✓ Downloaded {len(downloaded_files)} PDF file(s)")
        
        if downloaded_files:
            print("\n   Downloaded files:")
            for i, file_info in enumerate(downloaded_files[:5]):  # Show first 5
                print(f"   {i+1}. {file_info['filename'][:40]}")
                print(f"      Saved to: {file_info['filepath']}")
            
            if len(downloaded_files) > 5:
                print(f"   ... and {len(downloaded_files) - 5} more")
        else:
            print("\n   No PDF attachments found in the matching emails.")
            
    except Exception as e:
        print(f"   ✗ PDF download failed: {e}")
        sys.exit(1)
    
    # Summary
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    print(f"• Authenticated user: {user_email}")
    print(f"• Emails found: {len(emails)}")
    print(f"• PDFs downloaded: {len(downloaded_files)}")
    if downloaded_files:
        print(f"• Download location: {DOWNLOAD_DIR}")
    print("\nNext steps:")
    print("1. Step 4: PDF text extraction (src/pdf/pdf_to_text.py)")
    print("2. Step 5: LLM parsing (src/llm/parse_receipt.py)")
    print("3. Step 6: CSV export (src/output/csv_writer.py)")
    print("=" * 60)

if __name__ == "__main__":
    main()
