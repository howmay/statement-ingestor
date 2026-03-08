import os
import sys
from src.config import GMAIL_USER, GMAIL_APP_PASSWORD, TARGET_SENDERS, TARGET_KEYWORDS, DOWNLOAD_DIR
from src.gmail_client import GmailClient
from src.pdf_extractor import PDFExtractor
from src.parser_factory import get_parser
from src.csv_exporter import CSVExporter

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
        files_info = client.fetch_and_extract_pdfs(msg_id, DOWNLOAD_DIR, TARGET_KEYWORDS)
        
        for file_info in files_info:
            filepath = file_info["filepath"]
            sender = file_info["sender"]
            
            print(f"Extracting text from: {filepath}")
            extractor = PDFExtractor(filepath)
            raw_text = extractor.extract_text()
            
            print(f"Parsing content for sender: {sender}")
            parser = get_parser(sender, raw_text)
            parsed_info = parser.parse()
            
            # Attach source file info
            parsed_info["Source File"] = os.path.basename(filepath)
            extracted_data.append(parsed_info)

    if extracted_data:
        print(f"Extraction complete. Exporting {len(extracted_data)} record(s) to CSV...")
        exporter = CSVExporter(extracted_data, DOWNLOAD_DIR)
        csv_path = exporter.export()
        print(f"CSV generated at: {csv_path}")
        
        # Delivery mechanism (MVP group chat alert simulation)
        print("Review Alert: Please review the generated CSV file.")
    else:
        print("No valid data extracted. No CSV generated.")
        
    client.close()

if __name__ == "__main__":
    main()
