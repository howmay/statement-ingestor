import imaplib
import email
from email.header import decode_header
import os
import re

class GmailClient:
    def __init__(self, username, password):
        self.username = username
        self.password = password
        self.mail = None

    def connect(self):
        try:
            self.mail = imaplib.IMAP4_SSL("imap.gmail.com")
            self.mail.login(self.username, self.password)
            print(f"[{self.username}] Successfully connected to Gmail.")
        except Exception as e:
            print(f"[{self.username}] Connection failed: {e}")
            self.mail = None

    def close(self):
        if self.mail:
            try:
                self.mail.logout()
            except:
                pass

    def search_emails(self, senders, keywords, since_date=None):
        if not self.mail:
            print("Not connected.")
            return []

        self.mail.select("inbox")
        message_ids = []

        # Simplified search: IMAP search is limited. We'll search by sender and then filter locally for keywords and PDFs to be precise.
        for sender in senders:
            search_query = f'(FROM "{sender}")'
            if since_date:
                # since_date format: "01-Jan-2024"
                search_query += f' (SINCE "{since_date}")'
            
            status, messages = self.mail.search(None, search_query)
            if status == "OK" and messages[0]:
                message_ids.extend(messages[0].split())
                
        # Deduplicate
        return list(set(message_ids))

    def fetch_and_extract_pdfs(self, message_id, download_dir, keywords):
        """Fetch email, check keywords, and download PDF attachments."""
        status, msg_data = self.mail.fetch(message_id, "(RFC822)")
        if status != "OK":
            return []
            
        for response_part in msg_data:
            if isinstance(response_part, tuple):
                msg = email.message_from_bytes(response_part[1])
                
                # Decode subject
                subject, encoding = decode_header(msg["Subject"])[0]
                if isinstance(subject, bytes):
                    subject = subject.decode(encoding if encoding else "utf-8")
                
                # We can check keywords in subject (or body if needed, MVP: check subject first)
                has_keyword = any(kw.lower() in subject.lower() for kw in keywords)
                
                if not has_keyword:
                    # Let's check body text loosely
                    body_text = ""
                    if msg.is_multipart():
                        for part in msg.walk():
                            content_type = part.get_content_type()
                            if content_type == "text/plain":
                                try:
                                    body_text += part.get_payload(decode=True).decode()
                                except:
                                    pass
                    else:
                        try:
                            body_text = msg.get_payload(decode=True).decode()
                        except:
                            pass
                            
                    has_keyword = any(kw.lower() in body_text.lower() for kw in keywords)

                if not has_keyword:
                    continue # Skip if no keywords match

                downloaded_files = []
                
                # Extract PDF attachments
                if msg.is_multipart():
                    for part in msg.walk():
                        if part.get_content_maintype() == 'multipart':
                            continue
                        if part.get('Content-Disposition') is None:
                            continue
                            
                        filename = part.get_filename()
                        if filename:
                            filename, encoding = decode_header(filename)[0]
                            if isinstance(filename, bytes):
                                filename = filename.decode(encoding if encoding else "utf-8")
                                
                            if filename.lower().endswith('.pdf'):
                                filepath = os.path.join(download_dir, filename)
                                # Basic deduplication of filename
                                base, ext = os.path.splitext(filepath)
                                counter = 1
                                while os.path.exists(filepath):
                                    filepath = f"{base}_{counter}{ext}"
                                    counter += 1
                                    
                                with open(filepath, "wb") as f:
                                    f.write(part.get_payload(decode=True))
                                downloaded_files.append(filepath)
                                print(f"[{self.username}] Downloaded: {filepath}")
                
                return downloaded_files
        return []
