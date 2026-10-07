#!/usr/bin/env python3
"""Gmail Expense Parser - Application Core"""
# Orchestrates the supported end-to-end pipeline used by main.py.
import os
import sys
import traceback
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

# Import project modules
from src.support.cache import ResultCache
from src.support.config_validator import validate_configuration as config_is_valid
from src.core.config import TARGET_SENDERS, TARGET_KEYWORDS, DOWNLOAD_DIR, get_bank_password
from src.integrations.gmail.auth import get_gmail_service
from src.integrations.gmail.fetch import search_emails, list_attachments
from src.integrations.gmail.downloads import batch_download_pdfs
from src.parsing.pdf.pdf_to_text import extract_text_from_pdf
from src.parsing.csv.statement_csv import parse_csv_statement
from src.parsing.llm.parse_receipt import parse_receipt_text, ReceiptParsingError
from src.export.csv_writer import (
    export_receipts_to_csv,
    export_extracted_texts_to_csv,
    sort_exported_receipt_csvs,
)


_BANK_BY_PARSER = {
    'HsbcTwCardParser': ('HSBC', 'TW', '信用卡'), 'HsbcTwBankParser': ('HSBC', 'TW', '銀行帳戶'),
    'HsbcSgCardParser': ('HSBC', 'SG', '信用卡'), 'HsbcSgBankParser': ('HSBC', 'SG', '銀行帳戶'),
    'FubonCreditCardParser': ('Fubon', 'TW', '信用卡'), 'FubonBankParser': ('Fubon', 'TW', '銀行帳戶'),
    'EsunCardParser': ('E.SUN', 'TW', '信用卡'), 'EsunBankParser': ('E.SUN', 'TW', '銀行帳戶'),
    'DbsSgCardParser': ('DBS', 'SG', '信用卡'), 'DbsSgBankParser': ('DBS', 'SG', '銀行帳戶'),
    'SinopacCreditCardParser': ('SinoPac', 'TW', '信用卡'),
    'FirstBankCreditCardParser': ('FirstBank', 'TW', '信用卡'),
    'TaishinCreditCardParser': ('Taishin', 'TW', '信用卡'), 'TaishinBankParser': ('Taishin', 'TW', '銀行帳戶'),
}
_BANK_BY_FILENAME = (('玉山', 'E.SUN'), ('esun', 'E.SUN'), ('台新', 'Taishin'), ('taishin', 'Taishin'), ('富邦', 'Fubon'), ('fubon', 'Fubon'), ('星展', 'DBS'), ('dbs', 'DBS'), ('匯豐', 'HSBC'), ('hsbc', 'HSBC'), ('第一', 'FirstBank'), ('first', 'FirstBank'), ('永豐', 'SinoPac'), ('sinopac', 'SinoPac'), ('wise', 'Wise'))


class GmailExpenseParserApp:
    """Main application orchestrating the Gmail expense pipeline."""
    
    def __init__(self):
        """Initialize the application."""
        self.start_time = datetime.now()
        
        os.makedirs('logs', exist_ok=True)
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.StreamHandler(sys.stdout),
                logging.FileHandler(f"logs/gmail_expense_parser_{datetime.now():%Y%m%d_%H%M%S}.log", encoding='utf-8'),
            ],
            force=True,
        )
        self.logger = logging.getLogger(__name__)
        
        # Application state
        self.service = None
        self.user_email = None
        self.emails = []
        self.downloaded_files = []
        self.extracted_texts = []
        self.parsed_receipts = []
        
        # File processing reports
        self.processing_reports = []

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
        self.cache = ResultCache()
    
    def _get_bank_and_country(self, sender_tag, filename="", receipts=None):
        """Return (bank, country, account_type) from the parser name, else the filename."""
        parser = str((receipts or [{}])[0].get('parser_name') or '')
        if parser in _BANK_BY_PARSER:
            return _BANK_BY_PARSER[parser]
        f = (filename or '').lower()
        bank = next((b for k, b in _BANK_BY_FILENAME if k in f), 'Unknown')
        country = 'SG' if 'sg' in f or 'sg' in (sender_tag or '').lower() else ('Global' if bank == 'Wise' else 'TW')
        account_type = '信用卡' if any(k in f for k in ('信用卡', '簽帳', 'card')) else ('銀行帳戶' if any(k in f for k in ('對帳單', 'bank', 'statement', '帳戶')) else '未知')
        return bank, country, account_type

    def _add_file_report(self, filename: str, sender_tag: str, status: str, reason: str = "", receipts: Optional[List[Dict[str, Any]]] = None):
        """Record the processing status for a file."""
        bank, country, account_type = self._get_bank_and_country(sender_tag, filename, receipts)
        item_count = len(receipts) if receipts else 0
        self.processing_reports.append({
            'Bank': bank,
            'Country': country,
            'Type': account_type,
            'Filename': filename,
            'Status': status,
            'Count': item_count,
            'Reason': reason
        })

    def print_processing_report(self):
        """Print the final table report grouping by Bank/Country/Type/Filename/Status."""
        if not self.processing_reports:
            return

        import textwrap
        print("\n\n" + "=" * 110)
        print(" 處理結果報告 ".center(108 - 12))  # Adjust spacing for double-width chars roughly
        print("=" * 110)

        # Sort by Country, Bank, Type, Filename
        sorted_reports = sorted(
            self.processing_reports,
            key=lambda x: (x.get('Country', ''), x.get('Bank', ''), x.get('Type', ''), x.get('Filename', ''))
        )

        try:
            from tabulate import tabulate
            headers = ["銀行", "國家", "帳戶類型", "檔名", "狀態", "筆數", "原因"]
            table_data = []
            for r in sorted_reports:
                fname = "\n".join(textwrap.wrap(r.get('Filename', ''), width=35))
                reason = "\n".join(textwrap.wrap(r.get('Reason', ''), width=20))
                count_str = str(r.get('Count', 0)) if r.get('Status') == '成功' else '-'
                table_data.append([
                    r.get('Bank'), r.get('Country'), r.get('Type'), fname, r.get('Status'), count_str, reason
                ])
            print(tabulate(table_data, headers=headers, tablefmt="grid"))
        except ImportError:
            # Fallback formatting with multi-line wrapping
            header = f"| {'銀行':<10} | {'國家':<6} | {'類型':<10} | {'檔名':<35} | {'狀態':<6} | {'筆數':<4} | {'原因'}"
            print(header)
            print("-" * 110)
            for r in sorted_reports:
                bank = str(r.get('Bank'))[:10]
                country = str(r.get('Country'))[:6]
                acct_type = str(r.get('Type'))[:10]
                status = str(r.get('Status'))[:6]
                count_str = str(r.get('Count', 0)) if r.get('Status') == '成功' else '-'
                
                fname_lines = textwrap.wrap(str(r.get('Filename', '')), width=35)
                reason_lines = textwrap.wrap(str(r.get('Reason', '')), width=20)
                
                max_lines = max(1, len(fname_lines), len(reason_lines))
                for i in range(max_lines):
                    f_line = fname_lines[i] if i < len(fname_lines) else ""
                    r_line = reason_lines[i] if i < len(reason_lines) else ""
                    
                    if i == 0:
                        print(f"| {bank:<10} | {country:<6} | {acct_type:<10} | {f_line:<35} | {status:<6} | {count_str:<4} | {r_line}")
                    else:
                        print(f"| {'':<10} | {'':<6} | {'':<10} | {f_line:<35} | {'':<6} | {'':<4} | {r_line}")
                print("-" * 110)

        print("=" * 110 + "\n")
    
    def validate_configuration(self) -> bool:
        """Validate configuration before starting."""
        self.logger.info("Validating configuration...")
        try:
            if not config_is_valid():
                self.logger.error("Configuration validation failed.")
                self.stats['errors'] += 1
                return False
            self.logger.info("✓ Configuration is valid.")
            return True
        except Exception as e:
            self.logger.error(f"Error during configuration validation: {e}")
            self.stats['errors'] += 1
            return False

    def authenticate(self) -> bool:
        """Step 1: Authenticate with Gmail API."""
        self.logger.info("Step 1: Authenticating with Gmail API...")
        try:
            self.service = get_gmail_service()
            profile = self.service.users().getProfile(userId='me').execute()
            self.user_email = profile.get('emailAddress')
            self.logger.info(f"✓ Authenticated as: {self.user_email}")
            return True
        except Exception as e:
            self.logger.error(f"✗ Authentication failed: {e}")
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
        self.logger.info(f"Step 2: Searching for monthly statement emails (max {max_text}, range {date_from or '-'} ~ {date_to or '-'})...")
        try:
            self.emails = search_emails(
                self.service,
                max_results=max_results,
                date_from=date_from,
                date_to=date_to,
            )
            self.stats['emails_found'] = len(self.emails)
            self.logger.info(f"✓ Found {len(self.emails)} matching email(s)")
            return True
        except Exception as e:
            self.logger.error(f"✗ Email search failed: {e}")
            self.stats['errors'] += 1
            return False
            
    def download_attachments(self) -> bool:
        """Step 3: Download PDF attachments.

        Note: Gmail API service objects are not reliably thread-safe. We process
        emails sequentially here to avoid intermittent SSL / stream errors under
        parallel access.
        """
        if not self.emails:
            self.logger.info("No emails to process.")
            return True

        self.logger.info("Step 3: Downloading PDF attachments...")
        try:
            all_downloaded_files = []

            for email in self.emails:
                try:
                    downloaded_files = batch_download_pdfs(self.service, [email])
                    all_downloaded_files.extend(downloaded_files)
                except Exception as e:
                    self.logger.error(f"✗ Failed to download attachments for email {email.get('id', 'unknown')}: {e}")
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
            self.logger.info(f"✓ Downloaded {len(self.downloaded_files)} unique PDF(s)")
            return True
        except Exception as e:
            self.logger.error(f"✗ Batch PDF download failed: {e}")
            self.stats['errors'] += 1
            return False
            

    def _get_or_compute_file_md5(self, file_info: Dict[str, Any]) -> Optional[str]:
        """Compute file MD5 once per file_info and reuse it across pipeline steps."""
        cached_md5 = file_info.get('file_md5')
        if cached_md5:
            return cached_md5

        filepath = file_info.get('filepath', '')
        if not filepath:
            return None

        file_md5 = self.cache.get_file_md5(filepath)
        if file_md5:
            file_info['file_md5'] = file_md5
        return file_md5

    def _display_file_name(self, file_info: Dict[str, Any]) -> str:
        """Prefer downloaded local filename in logs, with original attachment name as context."""
        filepath = str(file_info.get('filepath') or '')
        local_name = os.path.basename(filepath) if filepath else ''
        original_name = str(file_info.get('filename') or '').strip()

        if local_name and original_name and local_name != original_name:
            return f"{local_name} (attachment: {original_name})"
        if local_name:
            return local_name
        if original_name:
            return original_name
        return 'unknown'

    def extract_texts(self, max_workers: Optional[int] = None) -> bool:
        """Step 4: Extract text from PDFs with parallelism and caching."""
        if not self.downloaded_files:
            self.logger.info("No PDFs downloaded.")
            return True
            
        self.logger.info("Step 4: Extracting text from PDFs...")
        
        files_to_process = self.downloaded_files
        
        if max_workers is None:
            max_workers = min(os.cpu_count() or 4, 10)
        
        def process_file(file_info):
            try:
                filepath = file_info.get('filepath', '')
                filename = os.path.basename(filepath)
                display_name = self._display_file_name(file_info)
                
                # Check cache for extracted text
                pdf_md5 = self._get_or_compute_file_md5(file_info)
                if pdf_md5:
                    # Use md5 + filename as key for extraction cache
                    cached_text = self.cache.get(f"extraction_{pdf_md5}", extra=filename)
                    if cached_text:
                        self.logger.info(f"Extraction cache hit for {filename}")
                        self.stats['cache_hits'] += 1
                        return {
                            'text': cached_text.get('text'),
                            'file_info': file_info,
                        }

                sender = file_info.get('sender', '')
                password_candidates = get_bank_password(sender) or [None]
                suffix = Path(filepath).suffix.lower()

                if suffix == '.csv':
                    with open(filepath, 'r', encoding='utf-8-sig', newline='') as csv_file:
                        csv_text = csv_file.read()
                    return {
                        'text': csv_text,
                        'file_info': file_info,
                    }

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
                    pdf_md5 = self._get_or_compute_file_md5(file_info)
                    if pdf_md5:
                        self.cache.set(f"extraction_{pdf_md5}", {'text': extracted_text}, extra=filename)
                    
                    file_info = dict(file_info)
                    file_info['pdf_password'] = password_used
                    return {
                        'text': extracted_text,
                        'file_info': file_info,
                    }

                if last_error:
                    error_msg = str(last_error).lower()
                    reason = "密碼不過" if "password" in error_msg or "encrypted" in error_msg else "解析pdf 異常"
                    return {
                        'error': f"Failed to extract text from {display_name}: {last_error}",
                        'file_info': file_info,
                        'report_status': '失敗',
                        'report_reason': reason
                    }

                return {
                    'warning': f"No text extracted from {display_name}",
                    'file_info': file_info,
                    'report_status': '失敗',
                    'report_reason': '無文字內容'
                }
            except Exception as e:
                return {
                    'error': f"Failed to extract text from {self._display_file_name(file_info)}: {e}",
                    'file_info': file_info,
                    'report_status': '失敗',
                    'report_reason': '例外錯誤'
                }

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(process_file, f) for f in files_to_process]
            
            for future in as_completed(futures):
                result = future.result()
                if 'text' in result:
                    self.extracted_texts.append(result)
                    self.stats['texts_extracted'] += 1
                else:
                    file_info = result.get('file_info', {})
                    filename = file_info.get('filename') or os.path.basename(file_info.get('filepath', 'unknown'))
                    sender_tag = file_info.get('sender_tag', 'unknown')
                    self._add_file_report(filename, sender_tag, result.get('report_status', '失敗'), result.get('report_reason', '未知錯誤'))

                if 'warning' in result:
                    self.logger.warning(result['warning'])
                    self.stats['warnings'] += 1
                elif 'error' in result:
                    self.logger.error(result['error'])
                    self.stats['errors'] += 1
                
        self.logger.info(f"✓ Extracted text from {len(self.extracted_texts)} file(s)")
        return True
        
    def parse_receipts(self, max_workers: int = 4) -> bool:
        """Step 5: Parse receipts using LLM with parallelism and caching."""
        if not self.extracted_texts:
            self.logger.info("No text to parse.")
            return True
            
        self.logger.info(f"Step 5: Parsing {len(self.extracted_texts)} receipt(s) using LLM (parallelism={max_workers})...")
        
        parsed_candidates: List[Dict[str, Any]] = []

        def process_item(item: Dict[str, Any]) -> List[Dict[str, Any]]:
            text = item['text']
            file_info = item['file_info']
            filepath = file_info.get('filepath', '')
            filename = file_info.get('filename') or os.path.basename(filepath)
            display_name = self._display_file_name(file_info)
            sender_tag = file_info.get('sender_tag', '')

            # Check cache first
            # Use PDF MD5 + sender_tag as cache key
            pdf_md5 = self._get_or_compute_file_md5(file_info)
            if pdf_md5:
                cached_result = self.cache.get(text, extra=f"{pdf_md5}_{sender_tag}")
                if cached_result:
                    self.logger.info(f"Cache hit for {filename}")
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
                if filename.lower().endswith('.csv'):
                    receipts = parse_csv_statement(text, source_info)
                else:
                    receipts = parse_receipt_text(text, source_info)
                
                # Store in cache if successful
                if receipts:
                    pdf_md5 = self._get_or_compute_file_md5(file_info)
                    if pdf_md5:
                        self.cache.set(text, receipts, extra=f"{pdf_md5}_{sender_tag}")
                
                return receipts
            except Exception as e:
                self.logger.error(f"Error parsing {display_name}: {e}")
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
                        self.logger.warning(f"No receipts parsed from {self._display_file_name(file_info)}")
                        self.stats['warnings'] += 1
                        self._add_file_report(filename, file_info.get('sender_tag', ''), "失敗", "解析內容異常/無交易紀錄", receipts)
                        continue

                    for r in receipts:
                        r['source_file'] = filename
                        parsed_candidates.append(r)
                        
                    self._add_file_report(filename, file_info.get('sender_tag', ''), "成功", "", receipts)
                except Exception as e:
                    self.logger.error(f"Unexpected error processing {self._display_file_name(file_info)}: {e}")
                    self.stats['errors'] += 1
                    self._add_file_report(filename, file_info.get('sender_tag', ''), "失敗", "未預期錯誤")

        self.parsed_receipts = parsed_candidates
        self.stats['receipts_parsed'] = len(self.parsed_receipts)
        self.logger.info(f"✓ Parsed {len(self.parsed_receipts)} receipt row(s) in total")
        return True
        
    def export_results(self) -> bool:
        """Step 6: Export results to CSV."""
        if not self.parsed_receipts and not self.extracted_texts:
            self.logger.info("No results to export.")
            return True
            
        self.logger.info("Step 6: Exporting results...")
        
        try:
            # Export parsed receipts
            if self.parsed_receipts:
                csv_path = export_receipts_to_csv(self.parsed_receipts)
                receipt_csv_paths = [path for path in csv_path.split(',') if path]
                if receipt_csv_paths:
                    sort_exported_receipt_csvs(receipt_csv_paths)
                self.logger.info(f"✓ Parsed receipts exported to: {csv_path}")
            
            # Also export raw extracted texts for debugging/record
            if self.extracted_texts:
                raw_texts_path = export_extracted_texts_to_csv(self.extracted_texts)
                self.logger.info(f"✓ Raw extracted texts exported to: {raw_texts_path}")
                
            return True
        except Exception as e:
            self.logger.error(f"✗ Export failed: {e}")
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
        self.logger.info("=" * 60)
        self.logger.info(f"Gmail Expense Parser started at {self.start_time}")
        self.logger.info("=" * 60)
        
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
            self.logger.warning("Operation cancelled by user.")
        except Exception as e:
            self.logger.error(f"An unexpected error occurred: {e}")
            self.logger.debug(traceback.format_exc())
        finally:
            end_time = datetime.now()
            duration = end_time - self.start_time
            
            self.logger.info("=" * 60)
            self.logger.info(f"Run completed in {duration.total_seconds():.2f} seconds")
            self.logger.info(f"Status: {'SUCCESS' if success else 'FAILED'}")
            self.logger.info(f"Summary: {self.stats['emails_found']} emails, "
                              f"{self.stats['pdfs_downloaded']} PDFs, "
                              f"{self.stats['receipts_parsed']} receipts")
            self.logger.info(f"Errors: {self.stats['errors']}, Warnings: {self.stats['warnings']}")
            self.logger.info("=" * 60)
            
            # Print the formatted table report
            self.print_processing_report()
            
        return self.stats
