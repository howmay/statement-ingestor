import os
import sys
import logging
from src.config import TARGET_SENDERS, TARGET_KEYWORDS, DOWNLOAD_DIR, get_bank_password
from src.auth.gmail_auth import get_gmail_service
from src.fetch.fetch_emails import search_emails, list_attachments
from src.fetch.download_pdfs import batch_download_pdfs
from src.pdf.pdf_to_text import extract_text_from_pdf
from src.llm.parse_receipt import parse_receipt_text, parse_multiple_receipts, ReceiptParsingError
# Temporarily keep imports for future steps (will be replaced in later steps)
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
    print("Gmail Receipt & Invoice Extractor (MVP) - Step 5 Demo")
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
    
    # Step 4: Extract text from PDFs
    print("\n3. Extracting text from PDFs (Step 4)...")
    extracted_texts = []
    
    if downloaded_files:
        for i, file_info in enumerate(downloaded_files):
            filepath = file_info['filepath']
            filename = file_info['filename']
            sender_tag = file_info.get('sender_tag', 'unknown')
            sender = file_info.get('sender', '')
            
            try:
                print(f"   Processing: {filename}...")
                
                # Get passwords to try (now returns list)
                passwords = get_bank_password(sender)
                
                text = None
                password_used = None
                
                if passwords:
                    print(f"   Trying {len(passwords)} password(s)...")
                    for i, password in enumerate(passwords):
                        try:
                            masked_pw = password[:3] + "..." + password[-3:] if len(password) > 6 else "***"
                            print(f"     Password {i+1}/{len(passwords)}: {masked_pw}")
                            
                            text = extract_text_from_pdf(filepath, password)
                            if text:
                                password_used = password
                                break
                        except ValueError as e:
                            if "Incorrect password" in str(e) or "password" in str(e).lower():
                                # Try next password
                                continue
                            else:
                                # Other ValueError, re-raise
                                raise
                else:
                    # No passwords configured
                    text = extract_text_from_pdf(filepath)
                
                if text:
                    print(f"   ✓ Extracted {len(text)} characters")
                    extracted_texts.append({
                        'filepath': filepath,
                        'filename': filename,
                        'sender': sender,
                        'sender_tag': sender_tag,
                        'text': text,
                        'subject': file_info.get('subject', ''),
                        'password_used': bool(password_used),
                        'password_tried': len(passwords) if passwords else 0
                    })
                else:
                    if passwords:
                        print(f"   ✗ All {len(passwords)} passwords failed")
                    else:
                        print(f"   ⚠ No text extracted (may be scanned/image PDF or no password)")
            except ValueError as e:
                if "Incorrect password" in str(e) or "password" in str(e).lower():
                    print(f"   ✗ Extraction failed: {e}")
                    print(f"   Please check BANK_PASSWORDS configuration for {sender_tag}")
                else:
                    print(f"   ✗ Extraction failed: {e}")
            except Exception as e:
                print(f"   ✗ Extraction failed: {e}")
                continue
        
        print(f"\n   Successfully extracted text from {len(extracted_texts)}/{len(downloaded_files)} PDF(s)")
    else:
        print("   No PDFs to process")
    
    # Step 5: LLM parsing
    print("\n4. Parsing receipts with LLM (Step 5)...")
    parsed_receipts = []
    
    if extracted_texts:
        for i, item in enumerate(extracted_texts):
            try:
                print(f"   Parsing: {item['filename'][:40]}...")
                
                # Prepare source info for LLM
                source_info = {
                    'sender': item['sender'],
                    'sender_tag': item['sender_tag'],
                    'filename': item['filename'],
                    'subject': item.get('subject', '')
                }
                
                # Parse receipt text
                parsed = parse_receipt_text(item['text'], source_info)
                parsed['original_file'] = item['filename']
                parsed['sender_tag'] = item['sender_tag']
                parsed_receipts.append(parsed)
                
                # Show brief result
                if parsed.get('amount') and parsed.get('currency'):
                    print(f"   ✓ {parsed.get('expense_name')[:30]:<30} {parsed.get('amount')} {parsed.get('currency')}")
                else:
                    print(f"   ⚠ Limited info extracted")
                    
            except ReceiptParsingError as e:
                print(f"   ✗ Parsing failed: {e}")
                continue
            except Exception as e:
                print(f"   ✗ Unexpected error: {e}")
                continue
        
        print(f"\n   Successfully parsed {len(parsed_receipts)}/{len(extracted_texts)} receipts")
    else:
        print("   No extracted text to parse")
    
    # Summary
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    print(f"• Authenticated user: {user_email}")
    print(f"• Emails found: {len(emails)}")
    print(f"• PDFs downloaded: {len(downloaded_files)}")
    print(f"• Texts extracted: {len(extracted_texts)}")
    print(f"• Receipts parsed: {len(parsed_receipts)}")
    if downloaded_files:
        print(f"• Download location: {DOWNLOAD_DIR}")
    
    # Show preview of parsed receipts if available
    if parsed_receipts:
        print("\n" + "-" * 60)
        print("Parsed Receipts Preview:")
        print("-" * 60)
        for i, receipt in enumerate(parsed_receipts[:3]):  # Show first 3
            print(f"\n[{i+1}] {receipt.get('expense_name', 'Unknown')}")
            if receipt.get('date'):
                print(f"    Date: {receipt['date']}")
            if receipt.get('amount') and receipt.get('currency'):
                print(f"    Amount: {receipt['amount']} {receipt['currency']}")
            if receipt.get('expense_type'):
                print(f"    Type: {receipt['expense_type']}")
            if receipt.get('source'):
                print(f"    Source: {receipt['source']}")
            if receipt.get('confidence'):
                print(f"    Confidence: {receipt['confidence']:.2f}")
    elif extracted_texts:
        print("\n" + "-" * 60)
        print("Extracted Text Preview (first 2 PDFs):")
        print("-" * 60)
        for i, item in enumerate(extracted_texts[:2]):
            print(f"\n[{i+1}] {item['filename']} (from: {item['sender_tag']})")
            preview = item['text'][:200]
            print(f"    {preview}...")
            if len(item['text']) > 200:
                print(f"    ({len(item['text']) - 200} more characters)")
    
    print("\n" + "=" * 60)
    print("Next steps:")
    print("1. Step 6: CSV export (src/output/csv_writer.py)")
    if not parsed_receipts:
        print("2. Configure OPENAI_API_KEY in .env for better LLM parsing")
    print("=" * 60)

if __name__ == "__main__":
    main()
