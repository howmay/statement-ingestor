#!/usr/bin/env python3
"""
Gmail Expense Parser - Enhanced version with comprehensive error handling and logging.
This version integrates all the enhancements from Issue #23 while maintaining backward compatibility.
"""
import os
import sys
import traceback
from datetime import datetime
from typing import List, Dict, Any, Optional

# Import enhanced utilities
try:
    from src.utils.logger import setup_logging, get_logger
    from src.utils.config_validator import validate_configuration, ConfigValidator
    from src.utils.progress import ProgressIndicator, ProgressStyle, track_progress
    from src.utils.retry import retry_gmail, retry_openai
    ENHANCEMENTS_AVAILABLE = True
except ImportError:
    # Fallback to basic logging if enhancements not available
    import logging
    ENHANCEMENTS_AVAILABLE = False
    print("⚠ Enhancement modules not found. Running in compatibility mode.")

# Import project modules
from src.config import TARGET_SENDERS, TARGET_KEYWORDS, DOWNLOAD_DIR, get_bank_password
from src.auth.gmail_auth import get_gmail_service
from src.fetch.fetch_emails import search_emails, list_attachments
from src.fetch.download_pdfs import batch_download_pdfs
from src.pdf.pdf_to_text import extract_text_from_pdf
from src.llm.parse_receipt import parse_receipt_text, parse_multiple_receipts, ReceiptParsingError
from src.output.csv_writer import export_receipts_to_csv, export_extracted_texts_to_csv


class EnhancedGmailExpenseParser:
    """Enhanced main application with comprehensive error handling and logging."""
    
    def __init__(self, use_enhancements: bool = True):
        """Initialize the application."""
        self.use_enhancements = use_enhancements and ENHANCEMENTS_AVAILABLE
        self.start_time = datetime.now()
        
        # Setup logging based on availability
        if self.use_enhancements:
            setup_logging(
                log_level='INFO',
                log_format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                date_format='%Y-%m-%d %H:%M:%S',
                log_dir='logs',
                log_to_file=True,
                log_to_console=True
            )
            self.logger = get_logger(__name__)
        else:
            # Basic logging for compatibility
            logging.basicConfig(
                level=logging.INFO,
                format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            self.logger = logging.getLogger(__name__)
        
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
        
        # Progress indicators
        self.progress = None
        
    def log(self, level: str, message: str, **kwargs):
        """Log message with appropriate level."""
        if level == 'info':
            self.logger.info(message, **kwargs)
        elif level == 'debug':
            self.logger.debug(message, **kwargs)
        elif level == 'warning':
            self.logger.warning(message, **kwargs)
        elif level == 'error':
            self.logger.error(message, **kwargs)
        elif level == 'exception':
            self.logger.exception(message, **kwargs)
    
    def validate_configuration(self) -> bool:
        """Validate configuration before starting."""
        self.log('info', "Validating configuration...")
        
        if self.use_enhancements:
            try:
                validator = ConfigValidator()
                is_valid, report = validator.validate_all()
                
                if is_valid:
                    self.log('info', "Configuration validation passed")
                    return True
                else:
                    self.log('error', f"Configuration validation failed:\n{report}")
                    print(f"\n❌ Configuration errors found:")
                    print(report)
                    return False
            except Exception as e:
                self.log('error', f"Configuration validation error: {e}", exc_info=True)
                print(f"⚠ Configuration validation error: {e}")
                # Continue with basic validation
                return self._basic_config_validation()
        else:
            return self._basic_config_validation()
    
    def _basic_config_validation(self) -> bool:
        """Basic configuration validation for compatibility mode."""
        # Check required environment variables
        required_vars = ['TARGET_SENDERS', 'TARGET_KEYWORDS']
        missing = []
        
        for var in required_vars:
            if not os.getenv(var):
                missing.append(var)
        
        if missing:
            print(f"❌ Missing required environment variables: {', '.join(missing)}")
            print("Please check your .env file")
            return False
        
        # Check config directory
        config_dir = os.path.join(os.path.dirname(__file__), 'config')
        client_secrets = os.path.join(config_dir, 'client_secrets.json')
        
        if not os.path.exists(client_secrets):
            print(f"❌ Missing client_secrets.json in {config_dir}")
            print("Please create a Google Cloud project and download OAuth2 credentials")
            return False
        
        return True
    
    def authenticate(self) -> bool:
        """Authenticate with Gmail API."""
        self.log('info', "Starting Gmail authentication...")
        
        try:
            if self.use_enhancements:
                # Use retry decorator if available
                @retry_gmail
                def _authenticate():
                    return get_gmail_service()
                
                self.service = _authenticate()
            else:
                self.service = get_gmail_service()
            
            # Get user profile
            profile = self.service.users().getProfile(userId='me').execute()
            self.user_email = profile.get('emailAddress')
            
            self.log('info', f"Authenticated as: {self.user_email}")
            print(f"✓ Authenticated as: {self.user_email}")
            return True
            
        except Exception as e:
            self.log('error', f"Authentication failed: {e}", exc_info=True)
            print(f"✗ Authentication failed: {e}")
            print("\nPlease ensure you have:")
            print("1. Created a Google Cloud project with Gmail API enabled")
            print("2. Configured OAuth2 desktop client credentials")
            print("3. Placed client_secrets.json in config/ directory")
            return False
    
    def search_emails(self, max_results: int = 10) -> bool:
        """Search for emails matching criteria."""
        self.log('info', f"Searching for emails (max: {max_results})...")
        
        if self.use_enhancements and self.progress:
            self.progress.update(description="Searching emails")
        
        try:
            if self.use_enhancements:
                # Use retry decorator if available
                @retry_gmail
                def _search_emails():
                    return search_emails(self.service, max_results=max_results)
                
                self.emails = _search_emails()
            else:
                self.emails = search_emails(self.service, max_results=max_results)
            
            self.stats['emails_found'] = len(self.emails)
            self.log('info', f"Found {len(self.emails)} matching email(s)")
            print(f"✓ Found {len(self.emails)} matching email(s)")
            
            if not self.emails:
                self.log('warning', "No matching emails found", 
                        senders=TARGET_SENDERS, keywords=TARGET_KEYWORDS)
                print("\n   No matching emails found with current criteria:")
                print(f"   - Senders: {TARGET_SENDERS}")
                print(f"   - Keywords: {TARGET_KEYWORDS}")
                return False
            
            # Log email summary
            for i, email in enumerate(self.emails[:3]):
                self.log('debug', f"Email {i+1}: {email['sender']} - {email['subject'][:50]}...")
            
            return True
            
        except Exception as e:
            self.log('error', f"Email search failed: {e}", exc_info=True)
            print(f"✗ Email search failed: {e}")
            self.stats['errors'] += 1
            return False
    
    def download_pdfs(self) -> bool:
        """Download PDF attachments from emails."""
        self.log('info', "Downloading PDF attachments...")
        
        if self.use_enhancements and self.progress:
            self.progress.update(description="Downloading PDFs")
        
        try:
            if self.use_enhancements:
                # Use retry decorator if available
                @retry_gmail
                def _download_pdfs():
                    return batch_download_pdfs(self.service, self.emails)
                
                self.downloaded_files = _download_pdfs()
            else:
                self.downloaded_files = batch_download_pdfs(self.service, self.emails)
            
            self.stats['pdfs_downloaded'] = len(self.downloaded_files)
            self.log('info', f"Downloaded {len(self.downloaded_files)} PDF file(s)")
            print(f"✓ Downloaded {len(self.downloaded_files)} PDF file(s)")
            
            if not self.downloaded_files:
                self.log('warning', "No PDF attachments found")
                print("\n   No PDF attachments found in the matching emails.")
                return False
            
            # Log download summary
            for i, file_info in enumerate(self.downloaded_files[:3]):
                self.log('debug', f"Downloaded {i+1}: {file_info['filename']}")
            
            return True
            
        except Exception as e:
            self.log('error', f"PDF download failed: {e}", exc_info=True)
            print(f"✗ PDF download failed: {e}")
            self.stats['errors'] += 1
            return False
    
    def extract_text_from_pdfs(self) -> bool:
        """Extract text from downloaded PDFs."""
        self.log('info', "Extracting text from PDFs...")
        
        if not self.downloaded_files:
            self.log('warning', "No PDFs to extract text from")
            return False
        
        success_count = 0
        
        # Setup progress indicator for extraction
        if self.use_enhancements:
            from src.utils.progress import track_progress
            files_to_process = track_progress(
                self.downloaded_files,
                description="Extracting text",
                style=ProgressStyle.BAR
            )
        else:
            files_to_process = self.downloaded_files
        
        for file_info in files_to_process:
            filepath = file_info['filepath']
            filename = file_info['filename']
            sender = file_info.get('sender', '')
            sender_tag = file_info.get('sender_tag', 'unknown')
            
            try:
                self.log('debug', f"Extracting text from: {filename}")
                
                # Get passwords to try
                passwords = get_bank_password(sender)
                
                text = None
                password_used = None
                
                if passwords:
                    self.log('debug', f"Trying {len(passwords)} password(s) for {filename}")
                    for i, password in enumerate(passwords):
                        try:
                            masked_pw = password[:3] + "..." + password[-3:] if len(password) > 6 else "***"
                            self.log('debug', f"Trying password {i+1}/{len(passwords)}: {masked_pw}")
                            
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
                    self.log('info', f"Extracted {len(text)} characters from {filename}")
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
                else:
                    if passwords:
                        self.log('warning', f"All {len(passwords)} passwords failed for {filename}")
                        print(f"   ✗ All {len(passwords)} passwords failed for {filename}")
                    else:
                        self.log('warning', f"No text extracted from {filename} (may be scanned/image PDF)")
                        print(f"   ⚠ No text extracted from {filename} (may be scanned/image PDF)")
                        
            except ValueError as e:
                if "Incorrect password" in str(e) or "password" in str(e).lower():
                    self.log('error', f"Password error for {filename}: {e}")
                    print(f"   ✗ Extraction failed: {e}")
                    print(f"   Please check BANK_PASSWORDS configuration for {sender_tag}")
                else:
                    self.log('error', f"Extraction error for {filename}: {e}", exc_info=True)
                    print(f"   ✗ Extraction failed: {e}")
                self.stats['errors'] += 1
            except Exception as e:
                self.log('error', f"Unexpected error extracting {filename}: {e}", exc_info=True)
                print(f"   ✗ Extraction failed: {e}")
                self.stats['errors'] += 1
        
        self.stats['texts_extracted'] = success_count
        self.log('info', f"Successfully extracted text from {success_count}/{len(self.downloaded_files)} PDF(s)")
        print(f"\n   Successfully extracted text from {success_count}/{len(self.downloaded_files)} PDF(s)")
        
        return success_count > 0
    
    def parse_receipts_with_llm(self) -> bool:
        """Parse extracted text with LLM."""
        self.log('info', "Parsing receipts with LLM...")
        
        if not self.extracted_texts:
            self.log('warning', "No extracted text to parse")
            return False
        
        success_count = 0
        
        # Setup progress indicator for parsing
        if self.use_enhancements:
            from src.utils.progress import track_progress
            texts_to_parse = track_progress(
                self.extracted_texts,
                description="Parsing receipts",
                style=ProgressStyle.BAR
            )
        else:
            texts_to_parse = self.extracted_texts
        
        for item in texts_to_parse:
            try:
                self.log('debug', f"Parsing: {item['filename']}")
                
                # Prepare source info for LLM
                source_info = {
                    'sender': item['sender'],
                    'sender_tag': item['sender_tag'],
                    'filename': item['filename'],
                    'subject': item.get('subject', '')
                }
                
                # Parse receipt text
                if self.use_enhancements:
                    # Use retry decorator if available
                    @retry_openai
                    def _parse_receipt():
                        return parse_receipt_text(item['text'], source_info)
                    
                    transactions = _parse_receipt()
                else:
                    transactions = parse_receipt_text(item['text'], source_info)
                
                if not transactions:
                    self.log('warning', f"No transactions extracted from {item['filename']}")
                    print(f"   ⚠ No transactions extracted from {item['filename']}")
                    continue
                
                # Add metadata to each transaction
                for tx in transactions:
                    tx['original_file'] = item['filename']
                    tx['sender_tag'] = item['sender_tag']
                    self.parsed_receipts.append(tx)
                
                # Log success
                first_tx = transactions[0]
                tx_count = len(transactions)
                self.log('info', f"Extracted {tx_count} transactions from {item['filename']}")
                
                if first_tx.get('amount') and first_tx.get('currency'):
                    if tx_count > 1:
                        print(f"   ✓ {tx_count} transactions found, first: {first_tx.get('expense_name')[:30]:<30} {first_tx.get('amount')} {first_tx.get('currency')}")
                    else:
                        print(f"   ✓ {first_tx.get('expense_name')[:30]:<30} {first_tx.get('amount')} {first_tx.get('currency')}")
                else:
                    print(f"   ⚠ Limited info extracted from {len(transactions)} transaction(s)")
                
                success_count += len(transactions)
                    
            except ReceiptParsingError as e:
                self.log('error', f"Parsing error for {item['filename']}: {e}")
                print(f"   ✗ Parsing failed: {e}")
                self.stats['errors'] += 1
            except Exception as e:
                self.log('error', f"Unexpected error parsing {item['filename']}: {e}", exc_info=True)
                print(f"   ✗ Unexpected error: {e}")
                self.stats['errors'] += 1
        
        self.stats['receipts_parsed'] = success_count
        self.log('info', f"Successfully parsed {success_count} transactions from {len(self.extracted_texts)} receipts")
        print(f"\n   Successfully parsed {success_count} transactions from {len(self.extracted_texts)} receipts")
        
        return success_count > 0
    
    def export_results(self) -> Optional[str]:
        """Export results to CSV."""
        self.log('info', "Exporting results to CSV...")
        
        if not self.parsed_receipts:
            self.log('warning', "No parsed receipts to export")
            print("⚠ No parsed receipts to export")
            return None
        
        try:
            # Create output directory
            output_dir = os.path.join(os.path.dirname(__file__), "output")
            csv_path = export_receipts_to_csv(self.parsed_receipts, output_dir)
            
            if csv_path and os.path.exists(csv_path):
                self.log('info', f"CSV exported: {csv_path}", 
                        receipt_count=len(self.parsed_receipts),
                        file_size=os.path.getsize(csv_path))
                
                print(f"✓ CSV exported: {csv_path}")
                print(f"  • Contains {len(self.parsed_receipts)} receipt(s)")
                print(f"  • File size: {os.path.getsize(csv_path):,} bytes")
                
                # Export extracted text for debugging if available
                if self.extracted_texts:
                    try:
                        text_csv = export_extracted_texts_to_csv(self.extracted_texts, output_dir)
                        if text_csv:
                            self.log('info', f"Extracted text CSV: {text_csv}")
                            print(f"  • Extracted text CSV: {text_csv}")
                    except Exception as e:
                        self.log('warning', f"Failed to export extracted text CSV: {e}")
                
                return csv_path
            else:
                self.log('error', "CSV export failed or file not created")
                print("⚠ CSV export failed or file not created")
                return None
                
        except Exception as e:
            self.log('error', f"CSV export error: {e}", exc_info=True)
            print(f"✗ CSV export error: {e}")
            self.stats['errors'] += 1
            return None
    
    def print_summary(self):
        """Print execution summary."""
        elapsed = (datetime.now() - self.start_time).total_seconds()
        
        print("\n" + "=" * 60)
        print("Execution Summary")
        print("=" * 60)
        print(f"• Authenticated user: {self.user_email}")
        print(f"• Emails found: {self.stats['emails_found']}")
        print(f"• PDFs downloaded: {self.stats['pdfs_downloaded']}")
        print(f"• Texts extracted: {self.stats['texts_extracted']}")
        print(f"• Receipts parsed: {self.stats['receipts_parsed']}")
        print(f"• Errors encountered: {self.stats['errors']}")
        print(f"• Warnings: {self.stats['warnings']}")
        print(f"• Execution time: {elapsed:.1f} seconds")
        
        if self.use_enhancements:
            print(f"• Enhancement mode: Enabled")
            log_dir = os.path.join(os.path.dirname(__file__), "logs")
            if os.path.exists(log_dir):
                log_files = [f for f in os.listdir(log_dir) if f.endswith('.log')]
                if log_files:
                    latest_log = sorted(log_files)[-1]
                    print(f"• Log file: logs/{latest_log}")
        else:
            print(f"• Enhancement mode: Compatibility")
        
        # Show preview of parsed receipts if available
        if self.parsed_receipts:
            print("\n" + "-" * 60)
            print("Parsed Receipts Preview:")
            print("-" * 60)
            for i, receipt in enumerate(self.parsed_receipts[:3]):
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
        
        print("\n" + "=" * 60)
        print("Next steps:")
        if not self.parsed_receipts and self.extracted_texts:
            print("1. Configure OPENAI_API_KEY in .env for better LLM parsing")
        if self.parsed_receipts:
            print("1. Review exported CSV file")
        print("2. Check logs/ directory for detailed execution logs")
        print("=" * 60)
    
    def run(self, max_emails: int = 10):
        """Run the complete workflow."""
        self.log('info', "Starting Gmail Expense Parser", 
                enhancements=self.use_enhancements,
                max_emails=max_emails)
        
        print("=" * 60)
        print("Gmail Expense Parser - Enhanced")
        print("=" * 60)
        
        # Step 1: Validate configuration
        if not self.validate_configuration():
            return False
        
        # Step 2: Setup progress indicator
        if self.use_enhancements:
            from src.utils.progress import ProgressIndicator, ProgressStyle
            self.progress = ProgressIndicator(
                total=5,  # Authentication, Search, Download, Extract, Parse
                description="Processing",
                style=ProgressStyle.BAR,
                show_eta=True
            )
            self.progress.start()
        
        # Step 3: Authenticate
        if self.use_enhancements and self.progress:
            self.progress.update(description="Authenticating")
        
        if not self.authenticate():
            if self.use_enhancements and self.progress:
                self.progress.finish("Authentication failed")
            return False
        
        if self.use_enhancements and self.progress:
            self.progress.update(1, description="Searching emails")
        
        # Step 4: Search emails
        if not self.search_emails(max_results=max_emails):
            if self.use_enhancements and self.progress:
                self.progress.finish("No emails found")
            return True  # Not an error, just no emails
        
        if self.use_enhancements and self.progress:
            self.progress.update(1, description="Downloading PDFs")
        
        # Step 5: Download PDFs
        if not self.download_pdfs():
            if self.use_enhancements and self.progress:
                self.progress.finish("No PDFs downloaded")
            return True  # Not an error, just no PDFs
        
        if self.use_enhancements and self.progress:
            self.progress.update(1, description="Extracting text")
        
        # Step 6: Extract text from PDFs
        self.extract_text_from_pdfs()
        
        if self.use_enhancements and self.progress:
            self.progress.update(1, description="Parsing receipts")
        
        # Step 7: Parse receipts with LLM
        if self.extracted_texts:
            self.parse_receipts_with_llm()
        
        # Step 8: Export results
        if self.use_enhancements and self.progress:
            self.progress.update(1, description="Exporting results")
        
        csv_path = self.export_results()
        
        # Step 9: Finish progress and print summary
        if self.use_enhancements and self.progress:
            if csv_path:
                self.progress.finish(f"Completed successfully. CSV: {csv_path}")
            else:
                self.progress.finish("Completed")
        
        self.print_summary()
        
        self.log('info', "Gmail Expense Parser completed", 
                elapsed_seconds=(datetime.now() - self.start_time).total_seconds(),
                **self.stats)
        
        return True


def main():
    """Main entry point with backward compatibility."""
    parser = EnhancedGmailExpenseParser(use_enhancements=True)
    parser.run(max_emails=10)


if __name__ == "__main__":
    main()
