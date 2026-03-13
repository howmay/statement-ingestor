#!/usr/bin/env python3
"""
Gmail Expense Parser - Application Core
Enhanced version with comprehensive error handling and logging.
"""
# Orchestrates the supported end-to-end pipeline used by main.py.
import os
import sys
import traceback
from datetime import datetime
from typing import List, Dict, Any, Optional
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

# Import enhanced utilities
try:
    from src.support.logger import setup_logging, get_logger
    from src.support.config_validator import validate_configuration as validate_config_util
    from src.support.progress import ProgressIndicator, ProgressStyle, track_progress
    from src.support.retry import retry_gmail, retry_openai
    from src.support.cache import ResultCache
    ENHANCEMENTS_AVAILABLE = True
except ImportError:
    # Fallback to basic logging if enhancements not available
    ENHANCEMENTS_AVAILABLE = False
    print("⚠ Enhancement modules not found. Running in compatibility mode.")

# Import project modules
from src.core.config import TARGET_SENDERS, TARGET_KEYWORDS, DOWNLOAD_DIR, get_bank_password
from src.integrations.gmail.auth import get_gmail_service
from src.integrations.gmail.fetch import search_emails, list_attachments
from src.integrations.gmail.downloads import batch_download_pdfs
from src.parsing.pdf.pdf_to_text import extract_text_from_pdf
from src.parsing.llm.parse_receipt import parse_receipt_text, parse_multiple_receipts, ReceiptParsingError
from src.export.csv_writer import export_receipts_to_csv, export_extracted_texts_to_csv


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
            'warnings': 0,
            'cache_hits': 0
        }
        
        # Initialize cache
        self.cache = ResultCache() if self.use_enhancements else None
        
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
                from src.support.config_validator import ConfigValidator
                validator = ConfigValidator()
                validation_result = validator.validate_all()

                # Backward compatibility:
                # - current validator returns bool
                # - older variant may return (is_valid, errors)
                if isinstance(validation_result, tuple):
                    is_valid = bool(validation_result[0])
                    errors = validation_result[1] if len(validation_result) > 1 else []
                else:
                    is_valid = bool(validation_result)
                    errors = []

                if not is_valid:
                    if errors:
                        self.log('error', f"Configuration validation failed with {len(errors)} error(s):")
                        for err in errors:
                            self.log('error', f"  - {err}")
                    else:
                        self.log('error', "Configuration validation failed.")
                    self.stats['errors'] += 1
                    return False

                self.log('info', "✓ Configuration is valid.")
                return True
            except Exception as e:
                self.log('error', f"Error during configuration validation: {e}")
                self.stats['errors'] += 1
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
            
    def fetch_emails(
        self,
        max_results: Optional[int] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> bool:
        """Step 2: Search for matching emails (supports date range)."""
        max_text = max_results if max_results is not None else 'ALL'
        self.log(
            'info',
            f"Step 2: Searching for emails (max {max_text}, range {date_from or '-'} ~ {date_to or '-'})..."
        )
        try:
            self.emails = search_emails(
                self.service,
                max_results=max_results,
                date_from=date_from,
                date_to=date_to,
            )
            self.stats['emails_found'] = len(self.emails)
            self.log('info', f"✓ Found {len(self.emails)} matching email(s)")
            return True
        except Exception as e:
            self.log('error', f"✗ Email search failed: {e}")
            self.stats['errors'] += 1
            return False
            
    def download_attachments(self) -> bool:
        """Step 3: Download PDF attachments.

        Note: Gmail API service objects are not reliably thread-safe. We process
        emails sequentially here to avoid intermittent SSL / stream errors under
        parallel access.
        """
        if not self.emails:
            self.log('info', "No emails to process.")
            return True

        self.log('info', "Step 3: Downloading PDF attachments...")
        try:
            all_downloaded_files = []

            for email in self.emails:
                try:
                    downloaded_files = batch_download_pdfs(self.service, [email])
                    all_downloaded_files.extend(downloaded_files)
                except Exception as e:
                    self.log('error', f"✗ Failed to download attachments for email {email.get('id', 'unknown')}: {e}")
                    self.stats['errors'] += 1

            # De-duplicate by physical file path (same attachment may appear in multiple emails)
            deduped = []
            seen_paths = set()
            for item in all_downloaded_files:
                path = item.get('filepath')
                if not path or path in seen_paths:
                    continue
                seen_paths.add(path)
                deduped.append(item)

            self.downloaded_files = deduped
            self.stats['pdfs_downloaded'] = len(self.downloaded_files)
            self.log('info', f"✓ Downloaded {len(self.downloaded_files)} unique PDF(s)")
            return True
        except Exception as e:
            self.log('error', f"✗ Batch PDF download failed: {e}")
            self.stats['errors'] += 1
            return False
            
    def extract_texts(self, max_workers: Optional[int] = None) -> bool:
        """Step 4: Extract text from PDFs with parallelism and caching."""
        if not self.downloaded_files:
            self.log('info', "No PDFs downloaded.")
            return True
            
        self.log('info', "Step 4: Extracting text from PDFs...")
        
        files_to_process = self.downloaded_files
        
        if max_workers is None:
            max_workers = min(os.cpu_count() or 4, 10)
        
        def process_file(file_info):
            try:
                filepath = file_info.get('filepath', '')
                filename = os.path.basename(filepath)
                
                # Check cache for extracted text
                if self.cache:
                    pdf_md5 = self.cache.get_file_md5(filepath)
                    if pdf_md5:
                        # Use md5 + filename as key for extraction cache
                        cached_text = self.cache.get(f"extraction_{pdf_md5}", extra=filename)
                        if cached_text:
                            self.log('info', f"Extraction cache hit for {filename}")
                            self.stats['cache_hits'] += 1
                            return {
                                'text': cached_text.get('text'),
                                'file_info': file_info,
                            }

                sender = file_info.get('sender', '')
                password_candidates = get_bank_password(sender) or [None]

                extracted_text = None
                password_used = None
                last_error = None

                # Try all passwords, then fallback to no-password
                tried = list(password_candidates)
                if None not in tried:
                    tried.append(None)

                for pw in tried:
                    try:
                        extracted_text = extract_text_from_pdf(filepath, pw)
                        if extracted_text:
                            password_used = pw
                            break
                    except Exception as e:
                        last_error = e
                        continue

                if extracted_text:
                    # Save to cache
                    if self.cache:
                        pdf_md5 = self.cache.get_file_md5(filepath)
                        self.cache.set(f"extraction_{pdf_md5}", {'text': extracted_text}, extra=filename)
                    
                    file_info = dict(file_info)
                    file_info['pdf_password'] = password_used
                    return {
                        'text': extracted_text,
                        'file_info': file_info,
                    }

                if last_error:
                    return {'error': f"Failed to extract text from {filename}: {last_error}"}

                return {'warning': f"No text extracted from {filename}"}
            except Exception as e:
                return {'error': f"Failed to extract text from {file_info.get('filepath', 'unknown')}: {e}"}

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
        
    def parse_receipts(self, max_workers: int = 4) -> bool:
        """Step 5: Parse receipts using LLM with parallelism and caching."""
        if not self.extracted_texts:
            self.log('info', "No text to parse.")
            return True
            
        self.log('info', f"Step 5: Parsing {len(self.extracted_texts)} receipt(s) using LLM (parallelism={max_workers})...")
        
        parsed_candidates: List[Dict[str, Any]] = []

        def process_item(item: Dict[str, Any]) -> List[Dict[str, Any]]:
            text = item['text']
            file_info = item['file_info']
            filepath = file_info.get('filepath', '')
            filename = file_info.get('filename') or os.path.basename(filepath)
            sender_tag = file_info.get('sender_tag', '')

            # Check cache first
            if self.cache:
                # Use PDF MD5 + sender_tag as cache key
                pdf_md5 = self.cache.get_file_md5(filepath)
                if pdf_md5:
                    cached_result = self.cache.get(text, extra=f"{pdf_md5}_{sender_tag}")
                    if cached_result:
                        self.log('info', f"Cache hit for {filename}")
                        self.stats['cache_hits'] += 1
                        return cached_result

            source_info = {
                'sender': file_info.get('sender', ''),
                'sender_tag': sender_tag,
                'filename': filename,
                'filepath': filepath,
                'subject': file_info.get('subject', ''),
                'pdf_password': file_info.get('pdf_password'),
            }

            try:
                receipts = parse_receipt_text(text, source_info)
                
                # Store in cache if successful
                if receipts and self.cache:
                    pdf_md5 = self.cache.get_file_md5(filepath)
                    self.cache.set(text, receipts, extra=f"{pdf_md5}_{sender_tag}")
                
                return receipts
            except Exception as e:
                self.log('error', f"Error parsing {filename}: {e}")
                return []

        # Use ThreadPoolExecutor for parallel LLM calls
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_item = {executor.submit(process_item, item): item for item in self.extracted_texts}
            
            for future in as_completed(future_to_item):
                item = future_to_item[future]
                file_info = item['file_info']
                filename = file_info.get('filename') or os.path.basename(file_info.get('filepath', ''))
                
                try:
                    receipts = future.result()
                    if not receipts:
                        self.log('warning', f"No receipts parsed from {filename}")
                        self.stats['warnings'] += 1
                        continue

                    for r in receipts:
                        r['source_file'] = filename
                        parsed_candidates.append(r)
                except Exception as e:
                    self.log('error', f"Unexpected error processing {filename}: {e}")
                    self.stats['errors'] += 1

        # De-duplicate parsed transactions to avoid repeated detail rows across reruns/files
        deduped_receipts: List[Dict[str, Any]] = []
        seen = set()
        for r in parsed_candidates:
            key = (
                str(r.get('date') or ''),
                f"{float(r.get('amount', 0)):.2f}" if r.get('amount') is not None else '',
                str(r.get('currency') or ''),
                str(r.get('expense_name') or '').strip(),
                str(r.get('source_file') or ''),
            )
            if key in seen:
                continue
            seen.add(key)
            deduped_receipts.append(r)

        self.parsed_receipts = deduped_receipts
        self.stats['receipts_parsed'] = len(self.parsed_receipts)
        self.log('info', f"✓ Parsed {len(self.parsed_receipts)} unique receipt row(s) in total")
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
            
    def run(
        self,
        max_results: Optional[int] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        max_workers: int = 4
    ) -> Dict[str, Any]:
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
                
            if not self.fetch_emails(max_results=max_results, date_from=date_from, date_to=date_to):
                return self.stats
                
            if not self.download_attachments():
                return self.stats
                
            if not self.extract_texts(max_workers=max_workers):
                return self.stats
                
            if not self.parse_receipts(max_workers=max_workers):
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
    parser.add_argument('--no-enhancements', action='store_true', help='Disable enhanced logging/ui')
    parser.add_argument('--date-from', type=str, default=None, help='Email start date (inclusive), YYYY-MM-DD')
    parser.add_argument('--date-to', type=str, default=None, help='Email end date (inclusive), YYYY-MM-DD')
    parser.add_argument('--workers', type=int, default=4, help='Max parallel workers')

    args = parser.parse_args()

    app = GmailExpenseParserApp(use_enhancements=not args.no_enhancements)
    app.run(date_from=args.date_from, date_to=args.date_to, max_workers=args.workers)
