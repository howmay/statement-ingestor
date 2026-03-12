#!/usr/bin/env python3
"""
Gmail Expense Parser - Application Core
Enhanced version with comprehensive error handling and logging.
"""
import os
import sys
import traceback
from datetime import datetime
from typing import List, Dict, Any, Optional
import logging

# Import enhanced utilities
try:
    from src.utils.logger import setup_logging, get_logger
    from src.utils.config_validator import validate_configuration as validate_config_util
    from src.utils.progress import ProgressIndicator, ProgressStyle, track_progress
    from src.utils.retry import retry_gmail, retry_openai
    ENHANCEMENTS_AVAILABLE = True
except ImportError:
    # Fallback to basic logging if enhancements not available
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


class GmailExpenseParserApp:
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
                # Use the enhanced validator
                from src.utils.config_validator import ConfigValidator
                validator = ConfigValidator()
                is_valid, errors = validator.validate_all()
                
                if not is_valid:
                    self.log('error', f"Configuration validation failed with {len(errors)} error(s):")
                    for err in errors:
                        self.log('error', f"  - {err}")
                    return False
                
                self.log('info', "✓ Configuration is valid.")
                return True
            except Exception as e:
                self.log('error', f"Error during configuration validation: {e}")
                return False
        else:
            # Basic validation
            if not TARGET_SENDERS:
                self.log('warning', "No target senders defined in config.")
            return True
            
    def authenticate(self) -> bool:
        """Step 1: Authenticate with Gmail API."""
        self.log('info', "Step 1: Authenticating with Gmail API...")
        try:
            self.service = get_gmail_service()
            profile = self.service.users().getProfile(userId='me').execute()
            self.user_email = profile.get('emailAddress')
            self.log('info', f"✓ Authenticated as: {self.user_email}")
            return True
        except Exception as e:
            self.log('error', f"✗ Authentication failed: {e}")
            self.stats['errors'] += 1
            return False
            
    def fetch_emails(self, max_results: int = 20) -> bool:
        """Step 2: Search for matching emails."""
        self.log('info', f"Step 2: Searching for emails (max {max_results})...")
        try:
            self.emails = search_emails(self.service, max_results=max_results)
            self.stats['emails_found'] = len(self.emails)
            self.log('info', f"✓ Found {len(self.emails)} matching email(s)")
            return True
        except Exception as e:
            self.log('error', f"✗ Email search failed: {e}")
            self.stats['errors'] += 1
            return False
            
    def download_attachments(self) -> bool:
        """Step 3: Download PDF attachments."""
        if not self.emails:
            self.log('info', "No emails to process.")
            return True
            
        self.log('info', "Step 3: Downloading PDF attachments...")
        try:
            from concurrent.futures import ThreadPoolExecutor, as_completed
            
            # Using ThreadPoolExecutor for concurrent downloads
            max_workers = min(os.cpu_count() or 4, 10)
            all_downloaded_files = []
            
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {executor.submit(batch_download_pdfs, self.service, [email]): email for email in self.emails}
                
                for future in as_completed(futures):
                    try:
                        downloaded_files = future.result()
                        all_downloaded_files.extend(downloaded_files)
                    except Exception as e:
                        email = futures[future]
                        self.log('error', f"✗ Failed to download attachments for email {email.get('id', 'unknown')}: {e}")
                        self.stats['errors'] += 1
            
            self.downloaded_files = all_downloaded_files
            self.stats['pdfs_downloaded'] = len(self.downloaded_files)
            self.log('info', f"✓ Downloaded {len(self.downloaded_files)} PDF(s) in total")
            return True
        except Exception as e:
            self.log('error', f"✗ Batch PDF download failed: {e}")
            self.stats['errors'] += 1
            return False
            
    def extract_texts(self) -> bool:
        """Step 4: Extract text from PDFs."""
        if not self.downloaded_files:
            self.log('info', "No PDFs to extract text from.")
            return True
            
        self.log('info', "Step 4: Extracting text from PDFs...")
        
        from concurrent.futures import ThreadPoolExecutor, as_completed
        
        # Determine if we should show progress
        files_to_process = self.downloaded_files
        
        # Extraction is CPU-heavy, but pdfplumber also waits for I/O.
        # ProcessPoolExecutor would be better for CPU, but ThreadPoolExecutor 
        # is safer with Gmail API objects if they were involved (they aren't here).
        # We'll use ThreadPoolExecutor for now to avoid pickling issues.
        max_workers = min(os.cpu_count() or 4, 10)
        
        def process_file(file_info):
            try:
                # Get password if needed (by bank name/sender tag)
                sender_tag = file_info.get('sender_tag', 'unknown')
                password = get_bank_password(sender_tag)
                
                text = extract_text_from_pdf(file_info['filepath'], password)
                if text:
                    return {
                        'text': text,
                        'file_info': file_info
                    }
                else:
                    return {'warning': f"No text extracted from {file_info['filepath']}"}
            except Exception as e:
                return {'error': f"Failed to extract text from {file_info['filepath']}: {e}"}

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(process_file, f) for f in files_to_process]
            
            for future in as_completed(futures):
                result = future.result()
                if 'text' in result:
                    self.extracted_texts.append(result)
                    self.stats['texts_extracted'] += 1
                elif 'warning' in result:
                    self.log('warning', result['warning'])
                    self.stats['warnings'] += 1
                elif 'error' in result:
                    self.log('error', result['error'])
                    self.stats['errors'] += 1
                
        self.log('info', f"✓ Extracted text from {len(self.extracted_texts)} file(s)")
        return True
        
    def parse_receipts(self) -> bool:
        """Step 5: Parse receipts using LLM."""
        if not self.extracted_texts:
            self.log('info', "No text to parse.")
            return True
            
        self.log('info', "Step 5: Parsing receipts using LLM...")
        
        # Group texts for batch processing if needed, or process individually
        for item in self.extracted_texts:
            text = item['text']
            file_info = item['file_info']
            
            try:
                # Use enhanced parsing if multiple receipts might be in one text
                # or if the text is very large
                receipts = parse_receipt_text(text)
                
                if receipts:
                    # Add metadata to each receipt
                    for r in receipts:
                        r['source_file'] = os.path.basename(file_info['filepath'])
                        r['sender'] = file_info['sender']
                        r['subject'] = file_info['subject']
                        self.parsed_receipts.append(r)
                        self.stats['receipts_parsed'] += 1
                else:
                    self.log('warning', f"No receipts parsed from {file_info['filepath']}")
                    self.stats['warnings'] += 1
                    
            except ReceiptParsingError as e:
                self.log('error', f"LLM parsing error for {file_info['filepath']}: {e}")
                self.stats['errors'] += 1
            except Exception as e:
                self.log('error', f"Unexpected error parsing {file_info['filepath']}: {e}")
                self.log('debug', traceback.format_exc())
                self.stats['errors'] += 1
                
        self.log('info', f"✓ Parsed {len(self.parsed_receipts)} receipt(s) in total")
        return True
        
    def export_results(self) -> bool:
        """Step 6: Export results to CSV."""
        if not self.parsed_receipts and not self.extracted_texts:
            self.log('info', "No results to export.")
            return True
            
        self.log('info', "Step 6: Exporting results...")
        
        try:
            # Export parsed receipts
            if self.parsed_receipts:
                csv_path = export_receipts_to_csv(self.parsed_receipts)
                self.log('info', f"✓ Parsed receipts exported to: {csv_path}")
            
            # Also export raw extracted texts for debugging/record
            if self.extracted_texts:
                raw_texts_path = export_extracted_texts_to_csv(self.extracted_texts)
                self.log('info', f"✓ Raw extracted texts exported to: {raw_texts_path}")
                
            return True
        except Exception as e:
            self.log('error', f"✗ Export failed: {e}")
            self.stats['errors'] += 1
            return False
            
    def run(self, max_results: int = 10) -> Dict[str, Any]:
        """Run the full pipeline."""
        self.log('info', "=" * 60)
        self.log('info', f"Gmail Expense Parser started at {self.start_time}")
        self.log('info', "=" * 60)
        
        success = False
        try:
            if not self.validate_configuration():
                return self.stats
                
            if not self.authenticate():
                return self.stats
                
            if not self.fetch_emails(max_results=max_results):
                return self.stats
                
            if not self.download_attachments():
                return self.stats
                
            if not self.extract_texts():
                return self.stats
                
            if not self.parse_receipts():
                return self.stats
                
            if not self.export_results():
                return self.stats
                
            success = True
        except KeyboardInterrupt:
            self.log('warning', "Operation cancelled by user.")
        except Exception as e:
            self.log('error', f"An unexpected error occurred: {e}")
            self.log('debug', traceback.format_exc())
        finally:
            end_time = datetime.now()
            duration = end_time - self.start_time
            
            self.log('info', "=" * 60)
            self.log('info', f"Run completed in {duration.total_seconds():.2f} seconds")
            self.log('info', f"Status: {'SUCCESS' if success else 'FAILED'}")
            self.log('info', f"Summary: {self.stats['emails_found']} emails, "
                             f"{self.stats['pdfs_downloaded']} PDFs, "
                             f"{self.stats['receipts_parsed']} receipts")
            self.log('info', f"Errors: {self.stats['errors']}, Warnings: {self.stats['warnings']}")
            self.log('info', "=" * 60)
            
        return self.stats


if __name__ == '__main__':
    # Simple CLI wrapper
    import argparse
    
    parser = argparse.ArgumentParser(description='Gmail Expense Parser')
    parser.add_argument('--limit', type=int, default=10, help='Max emails to process')
    parser.add_argument('--no-enhancements', action='store_true', help='Disable enhanced logging/ui')
    
    args = parser.parse_args()
    
    app = GmailExpenseParserApp(use_enhancements=not args.no_enhancements)
    app.run(max_results=args.limit)
