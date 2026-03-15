# Project Specification: Gmail Receipt & Invoice Extractor (MVP)

## 1. Overview
A single-run utility script designed to scan specified Gmail accounts, filter for specific receipt/invoice emails, extract PDF attachments, and parse the contents to retrieve structured billing information.

## 2. Core Requirements
### 2.1 Authentication & Input
- Support multiple Gmail accounts via provided API keys or OAuth credentials.
- Read from a predefined list of target email addresses/accounts.

### 2.2 Email Filtering
- **Sender:** Specific email addresses.
- **Keywords:** Defined keywords in subject or body.
- **Attachment:** Must contain PDF attachments.

### 2.3 Processing & Parsing
- Download PDF attachments from matching emails.
- Convert PDF content to text.
- **Parser Logic:** Primary parsing is handled by an LLM (e.g., OpenAI) to handle diverse formats with high accuracy. A heuristic/regex fallback is used when LLM is unavailable.
- **Large Document Handling:** Supports intelligent chunking and JSON repair for large transaction lists to overcome LLM output limits.
- **Fields:**
  - Date (日期)
  - Amount (金額)
  - Expense Name / Item (消費名目)
  - Type (類型)
  - Source (來源)
- **PDF Constraints:** Only text-based PDFs are supported for MVP. Scanned images/OCR are out of scope.

### 2.4 Output & Delivery
- **Format:** Export the structured data to a `CSV` file.
- **Delivery:** Send the resulting CSV to a designated group chat for review.

## 3. Developer Action (Ethan)
1. Setup the Gmail API/IMAP connection module.
2. Implement PDF text extraction (`pdfplumber` or similar).
3. Implement vendor-specific parsing configurations (No LLM usage).
4. Implement CSV generation and the group chat delivery mechanism.