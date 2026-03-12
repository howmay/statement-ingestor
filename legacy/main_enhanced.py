import os
import sys
import traceback
from datetime import datetime
from typing import List, Dict, Any

# Import enhanced utilities
from src.utils.logger import setup_logging, get_logger
from src.utils.config_validator import validate_configuration, ConfigValidator
from src.utils.progress import ProgressIndicator, ProgressStyle, track_progress
from src.utils.retry import retry_gmail, retry_openai

# Import project modules
from src.config import TARGET_SENDERS, TARGET_KEYWORDS, DOWNLOAD_DIR, get_bank_password
from src.auth.gmail_auth import get_gmail_service
from src.fetch.fetch_emails import search_emails, list_attachments
from src.fetch.download_pdfs import batch_download_pdfs
from src.pdf.pdf_to_text import extract_text_from_pdf
from src.llm.parse_receipt import parse_receipt_text, parse_multiple_receipts, ReceiptParsingError
from src.output.csv_writer import export_receipts_to_csv, export_extracted_texts_to_csv


class GmailExpenseParser:
    """Enhanced main application with comprehensive error handling and logging."""
    
    def __init__(self):
        """Initialize the application."""
        # Setup structured logging
        setup_logging(
            log_level='INFO',
            log_format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            date_format='%Y-%m-%d %H:%M:%S',
            log_dir='logs',
            log_to_file=True,
            log_to_console=True
        )
        
        self.logger = get_logger(__name__)
        self.start_time = datetime.now()
        
        # Application state
        self.service = None
        self.user_email = None
        self.emails = []
        self.downloaded_files = []
        self.extracted_texts = []
        self.parsed_receipts = []
        
        # Statistics
        self.stats = {
            'emails_found': 0,
            'pdfs_downloaded': 0,
            'texts_extracted': 0,
            'receipts_parsed': 0,
            'errors': 0,
            'warnings': 0
        }
    
    def validate_configuration(self) -> bool:
        """Validate configuration before starting."""
        self.logger.info("Validating configuration...")
        
        try:
            validator = ConfigValidator()
            is_valid = validator.validate_all()
            
            if is_valid:
                self.logger.info("Configuration validation passed")
                return True
            else:
                self.logger.error("Configuration validation failed")
                return False
                
        except Exception as e:
            self.logger.error(f"Configuration validation error: {e}", exc_info=True)
            return False
    
    @retry_gmail
    def authenticate(self) -> bool:
        """Authenticate with Gmail API."""
        self.logger.info("Starting Gmail authentication...")
        
        try:
            self.service = get_gmail_service()
            profile = self.service.users().getProfile(userId='me').execute()
            self.user_email = profile.get('emailAddress')
            
            self.logger.info(f"Authenticated as: {self.user_email}")
            return True
            
        except Exception as e:
            self.logger.error(f"Authentication failed: {e}", exc_info=True)
            self.stats['errors'] += 1
            return False
    
    def search_emails(self, max_results: int = 50) -> bool:
        """Search for emails with PDF attachments."""
        self.logger.info("Searching for emails...", 
                        senders=TARGET_SENDERS, 
                        keywords=TARGET_KEYWORDS,
                        max_results=max_results)
        
        try:
            self.emails = search_emails(self.service, max_results=max_results)
            self.stats['emails_found'] = len(self.emails)
            
            if not self.emails:
                self.logger.warning("No matching emails found", 
                                   senders=TARGET_SENDERS,
                                   keywords=TARGET_KEYWORDS)
                return False
            
            self.logger.info(f"Found {len(self.emails)} matching email(s)")
            
            # Log email summary
            for i, email in enumerate(self.emails[:3]):  # Log first 3
                self.logger.debug(f"Email {i+1}: {email['sender'][:50]}... - {email['subject'][:50]}...")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Email search failed: {e}", exc_info=True)
            self.stats['errors'] += 1
            return False
    
    def download_pdfs(self) -> bool:
        """Download PDF attachments from emails with progress tracking."""
        self.logger.info("Downloading PDF attachments...")
        
        if not self.emails:
            self.logger.warning("No emails to download from")
            return False
            
        from src.fetch.download_pdfs import download_pdf_attachments
        
        self.downloaded_files = []
        
        # Use progress indicator for downloading
        with ProgressIndicator(
            total=len(self.emails),
            description="Downloading PDFs",
            style=ProgressStyle.BAR,
            show_eta=True
        ) as progress:
            for email in self.emails:
                subject_preview = email.get('subject', 'No Subject')[:30]
                progress.update(1, description=f"Downloading: {subject_preview}...")
                
                try:
                    downloaded = download_pdf_attachments(self.service, email['id'], email)
                    self.downloaded_files.extend(downloaded)
                except Exception as e:
                    self.logger.error(f"Failed to process email {email['id']}: {e}")
                    self.stats['errors'] += 1
        
        self.stats['pdfs_downloaded'] = len(self.downloaded_files)
        
        if not self.downloaded_files:
            self.logger.warning("No PDF attachments found in matching emails")
            return False
            
        self.logger.info(f"Downloaded {len(self.downloaded_files)} PDF file(s)")
        
        # Log download summary
        for i, file_info in enumerate(self.downloaded_files[:3]):  # Log first 3
            self.logger.debug(f"PDF {i+1}: {file_info['filename'][:40]}...")
            
        return True
    
    def extract_text_from_pdfs(self) -> bool:
        """Extract text from downloaded PDFs."""
        self.logger.info("Extracting text from PDFs...")
        
        if not self.downloaded_files:
            self.logger.warning("No PDFs to process")
            return False
        
        self.extracted_texts = []
        success_count = 0
        fail_count = 0
        
        # Use progress indicator for extraction
        with ProgressIndicator(
            total=len(self.downloaded_files),
            description="Extracting text",
            style=ProgressStyle.BAR,
            show_eta=True
        ) as progress:
            
            for file_info in self.downloaded_files:
                filepath = file_info['filepath']
                filename = file_info['filename']
                sender = file_info.get('sender', '')
                sender_tag = file_info.get('sender_tag', 'unknown')
                
                progress.update(1, description=f"Extracting: {filename[:30]}...")
                
                try:
                    # Get passwords to try
                    passwords = get_bank_password(sender)
                    
                    text = None
                    password_used = None
                    
                    if passwords:
                        self.logger.debug(f"Trying {len(passwords)} password(s) for {filename}")
                        for i, password in enumerate(passwords):
                            try:
                                text = extract_text_from_pdf(filepath, password)
                                if text:
                                    password_used = password
                                    break
                            except ValueError as e:
                                if "Incorrect password" in str(e) or "password" in str(e).lower():
                                    continue
                                raise
                    else:
                        # No passwords configured
                        text = extract_text_from_pdf(filepath)
                    
                    if text:
                        self.extracted_texts.append({
                            'filepath': filepath,
                            'filename': filename,
                            'sender': sender,
                            'sender_tag': sender_tag,
                            'text': text,
                            'subject': file_info.get('subject', ''),
                            'password_used': bool(password_used),
                            'password_tried': len(passwords) if passwords else 0
                        })
                        success_count += 1
                        self.logger.debug(f"Successfully extracted text from {filename} ({len(text)} chars)")
                    else:
                        fail_count += 1
                        self.logger.warning(f"No text extracted from {filename}")
                        
                except Exception as e:
                    fail_count += 1
                    self.logger.error(f"Failed to extract text from {filename}: {e}", 
                                     exc_info=False)
                    self.stats['errors'] += 1
        
        self.stats['texts_extracted'] = success_count
        self.logger.info(f"Text extraction: {success_count} succeeded, {fail_count} failed")
        
        return success_count > 0
    
    @retry_openai
    def parse_receipts_with_llm(self) -> bool:
        """Parse extracted text using LLM."""
        self.logger.info("Parsing receipts with LLM...")
        
        if not self.extracted_texts:
            self.logger.warning("No extracted text to parse")
            return False
        
        self.parsed_receipts = []
        success_count = 0
        fail_count = 0
        
        # Use progress indicator for parsing
        with ProgressIndicator(
            total=len(self.extracted_texts),
            description="Parsing receipts",
            style=ProgressStyle.BAR,
            show_eta=True
        ) as progress:
            
            for item in self.extracted_texts:
                filename = item['filename']
                sender_tag = item['sender_tag']
                
                progress.update(1, description=f"Parsing: {filename[:30]}...")
                
                try:
                    # Prepare source info for LLM
                    source_info = {
                        'sender': item['sender'],
                        'sender_tag': sender_tag,
                        'filename': filename,
                        'subject': item.get('subject', '')
                    }
                    
                    # Parse receipt text
                    transactions = parse_receipt_text(item['text'], source_info)
                    
                    if not transactions:
                        self.logger.warning(f"No transactions extracted from {filename}")
                        fail_count += 1
                        continue
                    
                    # Add metadata to each transaction
                    for tx in transactions:
                        tx['original_file'] = filename
                        tx['sender_tag'] = sender_tag
                        self.parsed_receipts.append(tx)
                    
                    success_count += 1
                    self.logger.debug(f"Parsed {len(transactions)} transaction(s) from {filename}")
                    
                except ReceiptParsingError as e:
                    fail_count += 1
                    self.logger.warning(f"Receipt parsing failed for {filename}: {e}")
                    self.stats['warnings'] += 1
                    
                except Exception as e:
                    fail_count += 1
                    self.logger.error(f"Unexpected error parsing {filename}: {e}", 
                                     exc_info=False)
                    self.stats['errors'] += 1
        
        self.stats['receipts_parsed'] = len(self.parsed_receipts)
        self.logger.info(f"Receipt parsing: {success_count} succeeded, {fail_count} failed, "
                        f"{len(self.parsed_receipts)} total transactions")
        
        return success_count > 0
    
    def export_results(self) -> bool:
        """Export results to CSV files."""
        self.logger.info("Exporting results...")
        
        try:
            output_dir = os.path.join(os.path.dirname(__file__), "output")
            os.makedirs(output_dir, exist_ok=True)
            
            # Export parsed receipts
            if self.parsed_receipts:
                csv_path = export_receipts_to_csv(self.parsed_receipts, output_dir)
                if csv_path and os.path.exists(csv_path):
                    self.logger.info(f"Exported {len(self.parsed_receipts)} receipts to: {csv_path}")
                    self.logger.info(f"File size: {os.path.getsize(csv_path):,} bytes")
                else:
                    self.logger.warning("Failed to export receipts CSV")
                    return False
            
            # Export extracted text for debugging
            if self.extracted_texts:
                text_csv_path = export_extracted_texts_to_csv(self.extracted_texts, output_dir)
                if text_csv_path:
                    self.logger.debug(f"Extracted text exported to: {text_csv_path}")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Export failed: {e}", exc_info=True)
            self.stats['errors'] += 1
            return False
    
    def generate_report(self):
        """Generate and display execution report."""
        elapsed = datetime.now() - self.start_time
        
        report = [
            "=" * 60,
            "Execution Report",
            "=" * 60,
            f"Start time: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}",
            f"Elapsed time: {elapsed.total_seconds():.1f} seconds",
            f"Authenticated user: {self.user_email or 'N/A'}",
            "",
            "📊 Statistics:",
            f"  • Emails found: {self.stats['emails_found']}",
            f"  • PDFs downloaded: {self.stats['pdfs_downloaded']}",
            f"  • Texts extracted: {self.stats['texts_extracted']}",
            f"  • Receipts parsed: {self.stats['receipts_parsed']}",
            f"  • Transactions: {len(self.parsed_receipts)}",
            f"  • Errors: {self.stats['errors']}",
            f"  • Warnings: {self.stats['warnings']}",
            "",
            "📁 Output:",
        ]
        
        if self.parsed_receipts:
            output_dir = os.path.join(os.path.dirname(__file__), "output")
            csv_files = [f for f in os.listdir(output_dir) if f.endswith('.csv')]
            for csv_file in csv_files:
                csv_path = os.path.join(output_dir, csv_file)
                report.append(f"  • {csv_file}: {os.path.getsize(csv_path):,} bytes")
        
        report.append("")
        
        # Show sample of parsed receipts
        if self.parsed_receipts:
            report.append("📋 Sample transactions:")
            for i, receipt in enumerate(self.parsed_receipts[:3]):
                report.append(f"  {i+1}. {receipt.get('expense_name', 'Unknown')[:40]}")
                if receipt.get('date'):
                    report.append(f"     Date: {receipt['date']}")
                if receipt.get('amount') and receipt.get('currency'):
                    report.append(f"     Amount: {receipt['amount']} {receipt['currency']}")
                report.append("")
        
        report.append("=" * 60)
        
        print('\n'.join(report))
        self.logger.info("Execution completed", 
                        elapsed_seconds=elapsed.total_seconds(),
                        **self.stats)
    
    def run(self, max_emails: int = 50):
        """Main execution flow."""
        self.logger.info("Starting Gmail Expense Parser")
        
        # Step 1: Validate configuration
        if not self.validate_configuration():
            self.logger.error("Configuration validation failed. Exiting.")
            return False
        
        # Step 2: Authenticate
        if not self.authenticate():
            self.logger.error("Authentication failed. Exiting.")
            return False
        
        # Step 3: Search emails
        if not self.search_emails(max_emails):
            self.logger.warning("No emails found. Exiting.")
            return True  # Not an error, just no data
        
        # Step 4: Download PDFs
        if not self.download_pdfs():
            self.logger.warning("No PDFs downloaded. Exiting.")
            return True  # Not an error, just no PDFs
        
        # Step 5: Extract text
        if not self.extract_text_from_pdfs():
            self.logger.warning("No text extracted. Exiting.")
            return True  # Not an error, just no text
        
        # Step 6: Parse receipts
        if not self.parse_receipts_with_llm():
            self.logger.warning("No receipts parsed. Exiting.")
            # Continue to export any extracted text
        
        # Step 7: Export results
        self.export_results()
        
        # Step 8: Generate report
        self.generate_report()
        
        return True


def main():
    """Entry point for the enhanced application."""
    try:
        # Create and run the application
        app = GmailExpenseParser()
        success = app.run(max_emails=50)
        
        if success:
            print("\n✅ Application completed successfully!")
            return 0
        else:
            print("\n❌ Application failed!")
            return 1
            
    except KeyboardInterrupt:
        print("\n\n⚠️  Operation cancelled by user")
        return 130
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())